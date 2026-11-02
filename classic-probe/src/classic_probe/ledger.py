"""The campaign's durable ledger: one SQLite file shared by every invocation for both retailers.

A request exists in the ledger before it exists anywhere else. :meth:`Ledger.reserve` takes the database's
write lock (``BEGIN IMMEDIATE``), checks every limit against what is already recorded, and records the
dispatch with the upper bound of its charge, in one transaction. So concurrent invocations are serialized, a
crash after a reservation leaves the reservation in place, and a restart continues the same counters. A row is
never deleted and its reserved amount never changes (triggers refuse both). The amount committed against the
limit falls only when an operator records a confirmed charge with its basis (:meth:`confirm_charge`): an
unanswered request, or one the documentation says is not billed, keeps its reservation until then.

What keeps a second execution from granting itself a fresh budget:

* :meth:`open` never creates a ledger. A missing file, another campaign's file, or a ledger with another
  ``genesis_id`` is refused;
* the genesis id is random per :meth:`create`, and the owner's approval names it (gates.py), so a second
ledger
  made for the same campaign is not the approved one;
* the ledger is bound to its host, and a path on a network share is refused, because SQLite's locks are only
  reliable on a local disk. Both retailers' invocations therefore run on one host against one file.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from classic_probe.money import usd
from classic_probe.stops import RETAILER_ONLY, Stop

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


# Billing knowledge of a dispatch: what is known, kept apart.
UNKNOWN = "unknown"  # no answer: the remote outcome and the charge are unknown
BILLABLE = "documented_billable"  # the documentation says this status is billed; no reading of the charge yet
NOT_BILLED = (
    "documented_not_billed"  # the documentation says it is not billed; the reservation stays until read
)
CONFIRMED = "confirmed"  # an operator recorded the charge with its basis

# Where a dispatch is. "reserved" and "sent" rows of a process that ended stay counted, as unknown.
RESERVED, SENT, ANSWERED, IN_FLIGHT_UNKNOWN = "reserved", "sent", "answered", "in_flight_unknown"


@dataclass(frozen=True)
class Limits:
    """The proposed ceilings of a future approved campaign. These are ceilings: an approved campaign may lower
    them, never raise them."""

    per_retailer_requests: int = 10
    total_requests: int = 20
    campaign_minutes: int = 30
    total_usd: Decimal = Decimal("5.00")
    billing_headroom_usd: Decimal = Decimal("0.50")  # kept unspent, for delayed or uncertain charges
    export_reserve_seconds: int = 180  # the end of the campaign kept for evidence export and cleanup
    retailers: tuple[str, ...] = ("walmart", "marianos")

    def __post_init__(self) -> None:
        if self.per_retailer_requests > 10 or self.total_requests > 20:
            raise ValueError("the proposal allows at most 10 requests per retailer and 20 in total")
        if self.campaign_minutes > 30:
            raise ValueError("the proposal allows at most 30 minutes for the combined campaign")
        if self.total_usd > Decimal("5.00"):
            raise ValueError("the proposal allows at most USD 5 of combined provider charges")
        if self.billing_headroom_usd >= self.total_usd:
            raise ValueError("the billing headroom leaves nothing to spend")
        if self.export_reserve_seconds >= self.campaign_minutes * 60:
            raise ValueError("the export reserve leaves no time to collect")

    def retailer_share_usd(self) -> Decimal:
        """Each retailer's share of the spendable money: an equal split, to the cent below, so one retailer
        can never spend what the other needs."""
        spendable = self.total_usd - self.billing_headroom_usd
        return (spendable / len(self.retailers)).quantize(Decimal("0.01"), rounding="ROUND_DOWN")

    def as_json(self) -> str:
        data = asdict(self)
        data["total_usd"] = str(self.total_usd)
        data["billing_headroom_usd"] = str(self.billing_headroom_usd)
        data["retailers"] = list(self.retailers)
        return json.dumps(data, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Limits:
        data = json.loads(text)
        data["total_usd"] = usd(data["total_usd"])
        data["billing_headroom_usd"] = usd(data["billing_headroom_usd"])
        data["retailers"] = tuple(data["retailers"])
        return cls(**data)


class LedgerRefused(RuntimeError):
    """This execution is not connected to the campaign's ledger."""


class LimitReached(RuntimeError):
    """The request was not reserved, and so cannot be dispatched."""

    def __init__(self, stop: Stop, detail: str) -> None:
        super().__init__(detail)
        self.stop = stop
        self.detail = detail


@dataclass(frozen=True)
class Totals:
    dispatched_total: int
    dispatched_by_retailer: dict[str, int]
    committed_usd: Decimal  # confirmed charges plus the reservations no charge has replaced
    reserved_unconfirmed_usd: Decimal  # upper bounds with no confirmed charge
    confirmed_usd: Decimal
    estimated_usd: Decimal  # from documented rules and confirmed rates: never an invoice
    unknown_billing: int  # dispatches whose remote outcome is unknown
    other_units: dict[str, str]  # confirmed charges in another unit: never added to dollars

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        for key in ("committed_usd", "reserved_unconfirmed_usd", "confirmed_usd", "estimated_usd"):
            out[key] = str(out[key])
        return out


_SCHEMA = """
CREATE TABLE campaign (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    campaign_id TEXT NOT NULL,
    genesis_id TEXT NOT NULL,
    host TEXT NOT NULL,
    offline INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    limits TEXT NOT NULL,
    stop_code TEXT,
    stop_detail TEXT,
    stopped_at TEXT
);
CREATE TABLE dispatch (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer TEXT NOT NULL,
    step TEXT NOT NULL,
    purpose TEXT NOT NULL,
    request_class TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    payload_sha256 TEXT NOT NULL,
    reserved_at TEXT NOT NULL,
    reserved_usd TEXT NOT NULL,
    state TEXT NOT NULL,
    billing TEXT NOT NULL,
    estimated_usd TEXT,
    confirmed_value TEXT,
    confirmed_unit TEXT,
    confirmed_basis TEXT,
    provider_status INTEGER,
    retailer_status INTEGER,
    parser_status INTEGER,
    job_id TEXT,
    finished_at TEXT,
    note TEXT
);
CREATE TABLE retailer_stop (
    retailer TEXT PRIMARY KEY,
    stop_code TEXT NOT NULL,
    stop_detail TEXT NOT NULL,
    stopped_at TEXT NOT NULL
);
CREATE TABLE event (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE TRIGGER dispatch_never_deleted BEFORE DELETE ON dispatch
BEGIN SELECT RAISE(ABORT, 'a dispatch is spend history and is never deleted'); END;
CREATE TRIGGER reservation_never_changed BEFORE UPDATE OF reserved_usd, retailer, reserved_at ON dispatch
BEGIN SELECT RAISE(ABORT, 'a reservation is never changed'); END;
CREATE TRIGGER campaign_never_deleted BEFORE DELETE ON campaign
BEGIN SELECT RAISE(ABORT, 'the campaign row is never deleted'); END;
CREATE TRIGGER campaign_start_never_reset BEFORE UPDATE OF started_at ON campaign
WHEN OLD.started_at IS NOT NULL AND NEW.started_at IS NOT OLD.started_at
BEGIN SELECT RAISE(ABORT, 'the start of the campaign is never reset'); END;
"""


def host_id() -> str:
    """This machine, as a hash (the ledger and its exports do not name the machine)."""
    return hashlib.sha256(platform.node().encode("utf-8")).hexdigest()[:16]


def _refuse_network_path(path: Path) -> None:
    text = str(path)
    if text.startswith(("\\\\", "//")):
        raise LedgerRefused(f"the ledger must be on a local disk, not a network share: {text}")


class Ledger:
    def __init__(self, path: Path, conn: sqlite3.Connection, clock: Clock) -> None:
        self.path = path
        self.conn = conn
        self.clock = clock

    # -- creating and opening --------------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        path: Path,
        campaign_id: str,
        limits: Limits,
        *,
        offline: bool,
        clock: Clock = utc_now,
    ) -> Ledger:
        _refuse_network_path(path)
        if path.exists():
            raise LedgerRefused(f"{path} already exists: a ledger is never replaced")
        if not campaign_id.strip():
            raise LedgerRefused("a campaign needs an id")
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = cls._connect(path)
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO campaign (singleton, campaign_id, genesis_id, host, offline, created_at, limits) "
            "VALUES (1, ?, ?, ?, ?, ?, ?)",
            (campaign_id, uuid.uuid4().hex, host_id(), int(offline), clock().isoformat(), limits.as_json()),
        )
        return cls(path, conn, clock)

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        campaign_id: str,
        genesis_id: str,
        clock: Clock = utc_now,
    ) -> Ledger:
        """Connect to the campaign's ledger. It is never created here: see the module docstring."""
        _refuse_network_path(path)
        if not path.is_file():
            raise LedgerRefused(
                f"no ledger at {path}: this execution is not connected to the campaign's ledger"
            )
        ledger = cls(path, cls._connect(path), clock)
        try:
            row = ledger.conn.execute("SELECT campaign_id, genesis_id, host FROM campaign").fetchone()
        except sqlite3.DatabaseError:
            row = None
        problem = ""
        if row is None or row[0] != campaign_id:
            problem = f"{path} is not the ledger of campaign {campaign_id}"
        elif row[1] != genesis_id:
            problem = f"{path} has another genesis id: it is not the ledger the manifest names"
        elif row[2] != host_id():
            problem = f"{path} belongs to another host: a copied ledger would spend the budget twice"
        if problem:
            ledger.close()  # nothing was written; the file is left as it was
            raise LedgerRefused(problem)
        return ledger

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def _write(self) -> Iterator[None]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    # -- reading ---------------------------------------------------------------------------------------

    def _campaign(self, *fields: str) -> tuple[Any, ...]:
        row = self.conn.execute(f"SELECT {', '.join(fields)} FROM campaign").fetchone()
        assert row is not None
        return tuple(row)

    @property
    def campaign_id(self) -> str:
        return str(self._campaign("campaign_id")[0])

    @property
    def genesis_id(self) -> str:
        return str(self._campaign("genesis_id")[0])

    @property
    def offline(self) -> bool:
        return bool(self._campaign("offline")[0])

    @property
    def limits(self) -> Limits:
        return Limits.from_json(str(self._campaign("limits")[0]))

    def stopped(self) -> tuple[str, str] | None:
        code, detail = self._campaign("stop_code", "stop_detail")
        return (str(code), str(detail)) if code else None

    def retailer_stopped(self, retailer: str) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT stop_code, stop_detail FROM retailer_stop WHERE retailer = ?", (retailer,)
        ).fetchone()
        return (str(row[0]), str(row[1])) if row else None

    def deadlines(self) -> tuple[datetime, datetime] | None:
        """When the campaign ends and when its last dispatch must have ended (before the export's reserve)."""
        started = self._campaign("started_at")[0]
        if not started:
            return None
        limits = self.limits
        end = datetime.fromisoformat(str(started)) + timedelta(minutes=limits.campaign_minutes)
        return end, end - timedelta(seconds=limits.export_reserve_seconds)

    def rows(self) -> list[dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM dispatch ORDER BY seq")
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]

    def events(self) -> list[dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM event ORDER BY seq")
        names = [d[0] for d in cur.description]
        return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]

    def totals(self) -> Totals:
        rows = self.rows()
        by_retailer: dict[str, int] = {}
        reserved = confirmed = estimated = Decimal(0)
        other: dict[str, Decimal] = {}
        unknown = 0
        for r in rows:
            by_retailer[r["retailer"]] = by_retailer.get(r["retailer"], 0) + 1
            if r["confirmed_unit"] == "usd":
                confirmed += usd(r["confirmed_value"])
            else:
                reserved += usd(r["reserved_usd"])
                if r["confirmed_unit"]:
                    other[r["confirmed_unit"]] = other.get(r["confirmed_unit"], Decimal(0)) + usd(
                        r["confirmed_value"]
                    )
            if r["estimated_usd"] is not None:
                estimated += usd(r["estimated_usd"])
            if r["billing"] == UNKNOWN and r["state"] != ANSWERED:
                unknown += 1
        return Totals(
            dispatched_total=len(rows),
            dispatched_by_retailer=by_retailer,
            committed_usd=reserved + confirmed,
            reserved_unconfirmed_usd=reserved,
            confirmed_usd=confirmed,
            estimated_usd=estimated,
            unknown_billing=unknown,
            other_units={k: str(v) for k, v in other.items()},
        )

    def _committed_by(self, retailer: str) -> Decimal:
        total = Decimal(0)
        for r in self.rows():
            if r["retailer"] != retailer:
                continue
            total += usd(r["confirmed_value"]) if r["confirmed_unit"] == "usd" else usd(r["reserved_usd"])
        return total

    # -- reserving -------------------------------------------------------------------------------------

    def reserve(
        self,
        *,
        retailer: str,
        step: str,
        purpose: str,
        request_class: str,
        attempt: int,
        payload_sha256: str,
        amount_usd: Decimal,
        request_timeout_s: float,
    ) -> int:
        """Count the request and reserve its upper bound, or raise :class:`LimitReached`. Whatever is sent
        later has a row here first: setup, authentication, qualification and every retry alike."""
        now = self.clock()
        with self._write():
            campaign_stop = self.stopped()
            if campaign_stop:
                raise LimitReached(Stop(campaign_stop[0]), f"the campaign has stopped: {campaign_stop[1]}")
            own_stop = self.retailer_stopped(retailer)
            if own_stop:
                raise LimitReached(Stop(own_stop[0]), f"{retailer} has stopped: {own_stop[1]}")
            limits = self.limits
            if retailer not in limits.retailers:
                raise LedgerRefused(f"{retailer} is not a retailer of this campaign")
            total = int(self.conn.execute("SELECT COUNT(*) FROM dispatch").fetchone()[0])
            if total >= limits.total_requests:
                raise LimitReached(
                    Stop.TOTAL_REQUESTS, f"{total} of {limits.total_requests} requests dispatched"
                )
            own = int(
                self.conn.execute("SELECT COUNT(*) FROM dispatch WHERE retailer = ?", (retailer,)).fetchone()[
                    0
                ]
            )
            if own >= limits.per_retailer_requests:
                raise LimitReached(
                    Stop.RETAILER_QUOTA,
                    f"{retailer}: {own} of {limits.per_retailer_requests} requests dispatched; the other "
                    "retailer's share is not borrowed",
                )
            totals = self.totals()
            committed = totals.committed_usd
            own_committed = self._committed_by(retailer)
            share = limits.retailer_share_usd()
            if own_committed + amount_usd > share:
                raise LimitReached(
                    Stop.RETAILER_FUNDS,
                    f"{retailer}: {own_committed} committed + {amount_usd} is above its share {share}; the "
                    "other retailer's share is not borrowed",
                )
            spendable = limits.total_usd - limits.billing_headroom_usd
            if committed + amount_usd > spendable:
                raise LimitReached(
                    Stop.FUNDS,
                    f"{committed} committed + {amount_usd} for this request is above {spendable} "
                    f"(USD {limits.total_usd} less {limits.billing_headroom_usd} of headroom)",
                )
            started = self._campaign("started_at")[0]
            start = datetime.fromisoformat(str(started)) if started else now
            end = start + timedelta(minutes=limits.campaign_minutes)
            last = end - timedelta(seconds=limits.export_reserve_seconds)
            if now + timedelta(seconds=request_timeout_s) > last:
                raise LimitReached(
                    Stop.DEADLINE,
                    f"a request of up to {request_timeout_s} s would end after {last.isoformat()}, the time "
                    "kept for evidence export and cleanup",
                )
            if not started:
                self.conn.execute("UPDATE campaign SET started_at = ?", (now.isoformat(),))
            cur = self.conn.execute(
                "INSERT INTO dispatch (retailer, step, purpose, request_class, attempt, payload_sha256, "
                "reserved_at, reserved_usd, state, billing) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    retailer,
                    step,
                    purpose,
                    request_class,
                    attempt,
                    payload_sha256,
                    now.isoformat(),
                    str(amount_usd),
                    RESERVED,
                    UNKNOWN,
                ),
            )
            seq = cur.lastrowid
        assert seq is not None
        return int(seq)

    # -- after the reservation -------------------------------------------------------------------------

    def mark_sent(self, seq: int) -> None:
        with self._write():
            self.conn.execute("UPDATE dispatch SET state = ? WHERE seq = ?", (SENT, seq))

    def settle(
        self,
        seq: int,
        *,
        billing: str,
        estimated_usd: Decimal | None,
        provider_status: int | None,
        retailer_status: int | None,
        parser_status: int | None,
        job_id: str | None,
        note: str,
    ) -> None:
        """The answer of a dispatch. The reservation stays: only a confirmed charge replaces it."""
        with self._write():
            self.conn.execute(
                "UPDATE dispatch SET state = ?, billing = ?, estimated_usd = ?, provider_status = ?, "
                "retailer_status = ?, parser_status = ?, job_id = ?, finished_at = ?, note = ? WHERE seq = ?",
                (
                    ANSWERED,
                    billing,
                    None if estimated_usd is None else str(estimated_usd),
                    provider_status,
                    retailer_status,
                    parser_status,
                    job_id,
                    self.clock().isoformat(),
                    note,
                    seq,
                ),
            )

    def mark_unknown(self, seq: int, note: str) -> None:
        """No answer. The request may have reached the provider, so its reservation stays and nothing is
        claimed about whether it was cancelled or charged."""
        with self._write():
            self.conn.execute(
                "UPDATE dispatch SET state = ?, billing = ?, finished_at = ?, note = ? WHERE seq = ?",
                (IN_FLIGHT_UNKNOWN, UNKNOWN, self.clock().isoformat(), note, seq),
            )

    def recover(self) -> int:
        """After a restart: rows a process left reserved or sent stay counted, as unknown. Run only when no
        other invocation of the campaign is active (the CLI runs it before an invocation starts)."""
        with self._write():
            cur = self.conn.execute(
                "UPDATE dispatch SET state = ?, note = COALESCE(note, ?) WHERE state IN (?, ?)",
                (
                    IN_FLIGHT_UNKNOWN,
                    "found unfinished at a restart: the remote outcome is unknown",
                    RESERVED,
                    SENT,
                ),
            )
        return int(cur.rowcount)

    def confirm_charge(self, seq: int, value: Any, unit: str, basis: str) -> None:
        """An operator's reading of what a dispatch actually cost, with where it was read. Dollars replace the
        reservation; another unit is kept beside it, because it is not interchangeable with dollars."""
        amount = usd(value)
        if not basis.strip():
            raise ValueError("a confirmed charge needs its basis")
        unit = unit.strip().lower()
        with self._write():
            cur = self.conn.execute(
                "UPDATE dispatch SET billing = ?, confirmed_value = ?, confirmed_unit = ?, confirmed_basis = "
                "? WHERE seq = ?",
                (CONFIRMED, str(amount), unit, basis, seq),
            )
            if cur.rowcount != 1:
                raise ValueError(f"no dispatch {seq}")

    def stop(self, code: Stop, detail: str, *, retailer: str | None = None) -> None:
        """Record why work stopped. The first stop stays the campaign's reason; nothing clears it."""
        at = self.clock().isoformat()
        with self._write():
            if code in RETAILER_ONLY and retailer:
                self.conn.execute(
                    "INSERT OR IGNORE INTO retailer_stop (retailer, stop_code, stop_detail, stopped_at) "
                    "VALUES (?, ?, ?, ?)",
                    (retailer, code.value, detail, at),
                )
            else:
                self.conn.execute(
                    "UPDATE campaign SET stop_code = ?, stop_detail = ?, stopped_at = ? WHERE stop_code IS "
                    "NULL",
                    (code.value, detail, at),
                )
            self.conn.execute(
                "INSERT INTO event (at, kind, detail) VALUES (?, ?, ?)",
                (at, code.value, f"{retailer}: {detail}"),
            )

    def event(self, kind: str, detail: str) -> None:
        with self._write():
            self.conn.execute(
                "INSERT INTO event (at, kind, detail) VALUES (?, ?, ?)",
                (self.clock().isoformat(), kind, detail),
            )


def write_manifest(path: Path, ledger: Ledger) -> None:
    if path.exists():
        raise LedgerRefused(f"{path} already exists")
    data = {
        "campaign_id": ledger.campaign_id,
        "ledger_path": os.fspath(ledger.path),
        "ledger_genesis_id": ledger.genesis_id,
        "offline": ledger.offline,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def open_from_manifest(path: Path, clock: Clock = utc_now) -> Ledger:
    if not path.is_file():
        raise LedgerRefused(f"no campaign manifest at {path}: run campaign-init once for the whole campaign")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Ledger.open(
        Path(data["ledger_path"]),
        campaign_id=str(data["campaign_id"]),
        genesis_id=str(data["ledger_genesis_id"]),
        clock=clock,
    )
