"""Shared parts of the provider probes (TEST_PLAN.md phases P1 to P3).

* Secrets are read from dotenv files as data (``NAME=value`` or ``NAME: value`` lines; nothing is executed),
  travel only in request headers or bodies, and are removed from every saved answer.
* Every answer is saved as sanitized evidence: no Authorization, cookie or key header, e-mail addresses
  masked, each secret value replaced.
* The ledger (SQLite) reserves a request's cost before the request is sent, inside one ``BEGIN IMMEDIATE``
  transaction, against the phase's cap; the answer settles it. A request that would cross the cap is not sent.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
SENSITIVE_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key", "x-oxylabs-api-token"}
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LINE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(.*)$")


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_dotenv(path: Path) -> dict[str, str]:
    """``NAME=value`` / ``NAME: value`` lines as data; quotes around a value are removed."""
    out: dict[str, str] = {}
    for raw in path.read_bytes().decode("utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        value = m.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[m.group(1)] = value
    return out


def revision() -> dict[str, Any]:
    """The code revision the probe runs from (commit, and whether the probe files differ from it)."""

    def git(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], cwd=PROJECT, capture_output=True, text=True, timeout=30, check=False
            ).stdout.strip()
        except OSError:
            return ""

    return {
        "commit": git("rev-parse", "HEAD"),
        "uncommitted_changes": bool(git("status", "--porcelain", "--", ".")),
    }


def scrub(text: str, secrets: Iterable[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "[REDACTED]")
    return _EMAIL.sub("[email masked]", text)


def safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in SENSITIVE_HEADERS}


class Evidence:
    """A folder of sanitized answers, one numbered JSON file each, and an index of them."""

    def __init__(self, folder: Path, secrets: Iterable[str]):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.secrets = [s for s in secrets if s]
        self.n = len(list(self.folder.glob("*.json")))

    def add_secret(self, value: str) -> None:
        if value:
            self.secrets.append(value)

    def save(self, name: str, record: Mapping[str, Any]) -> Path:
        self.n += 1
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:80]
        path = self.folder / f"{self.n:04d}_{stamp}_{safe}.json"
        text = json.dumps(record, indent=1, ensure_ascii=False, default=str)
        path.write_bytes(scrub(text, self.secrets).encode("utf-8"))
        return path

    def save_text(self, name: str, text: str) -> Path:
        self.n += 1
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:80]
        path = self.folder / f"{self.n:04d}_{stamp}_{safe}"
        path.write_bytes(scrub(text, self.secrets).encode("utf-8"))
        return path


class CapReached(RuntimeError):
    pass


@dataclass(frozen=True)
class Reservation:
    row_id: int
    units: float


class Ledger:
    """Reservations and settlements of provider usage; counters survive restarts (one SQLite file)."""

    def __init__(self, path: Path, caps: Mapping[tuple[str, str], float]):
        self.path = path
        self.caps = dict(caps)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS usage (id INTEGER PRIMARY KEY, provider TEXT, phase TEXT, "
                "purpose TEXT,"
                " reserved_at TEXT, reserved REAL, settled_at TEXT, actual REAL, state TEXT, outcome TEXT,"
                " revision TEXT)"
            )

    def _con(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=60, isolation_level=None)

    def used(self, provider: str, phase: str | None = None) -> float:
        q = (
            "SELECT COALESCE(SUM(CASE WHEN state = 'settled' THEN actual ELSE reserved END), 0) FROM usage"
            " WHERE provider = ?" + (" AND phase = ?" if phase else "")
        )
        con = self._con()
        try:
            return float(con.execute(q, (provider, phase) if phase else (provider,)).fetchone()[0])
        finally:
            con.close()

    def reserve(self, provider: str, phase: str, units: float, purpose: str, rev: str) -> Reservation:
        cap = self.caps.get((provider, phase))
        if cap is None:
            raise CapReached(f"no cap set for {provider}/{phase}: nothing is sent")
        con = self._con()
        try:
            con.execute("BEGIN IMMEDIATE")
            used = con.execute(
                "SELECT COALESCE(SUM(CASE WHEN state = 'settled' THEN actual ELSE reserved END), 0) "
                "FROM usage"
                " WHERE provider = ? AND phase = ?",
                (provider, phase),
            ).fetchone()[0]
            if used + units > cap:
                con.execute("ROLLBACK")
                raise CapReached(f"{provider}/{phase}: {used:g} used + {units:g} would cross the cap {cap:g}")
            cur = con.execute(
                "INSERT INTO usage (provider, phase, purpose, reserved_at, reserved, state, revision)"
                " VALUES (?, ?, ?, ?, ?, 'reserved', ?)",
                (provider, phase, purpose, utc_now(), units, rev),
            )
            con.execute("COMMIT")
            return Reservation(int(cur.lastrowid or 0), units)
        finally:
            con.close()

    def settle(self, r: Reservation, actual: float, outcome: str) -> None:
        con = self._con()
        try:
            con.execute(
                "UPDATE usage SET settled_at = ?, actual = ?, state = 'settled', outcome = ? WHERE id = ?",
                (utc_now(), actual, outcome, r.row_id),
            )
        finally:
            con.close()

    def rows(self, provider: str) -> list[dict[str, Any]]:
        con = self._con()
        con.row_factory = sqlite3.Row
        try:
            return [
                dict(r)
                for r in con.execute("SELECT * FROM usage WHERE provider = ? ORDER BY id", (provider,))
            ]
        finally:
            con.close()


def out_dir() -> Path:
    return Path(os.environ.get("MARIANOS_PROBE_OUT") or (PROJECT / "probe_out"))


def secrets_dir() -> Path:
    value = os.environ.get("MARIANOS_PROBE_SECRETS")
    if not value:
        raise SystemExit("MARIANOS_PROBE_SECRETS must name the folder holding the provider .env files")
    return Path(value)


# TEST_PLAN.md section 3 (units: Kroger calls, Oxylabs submissions, Scrapfly credits).
CAPS: dict[tuple[str, str], float] = {
    ("kroger", "P1"): 180,
    ("oxylabs", "P3"): 40,
    ("scrapfly", "P2"): 150,
    # TEST_PLAN_140.md section 2 (the task after release 1.3.5)
    ("kroger", "Q0"): 60,
}
