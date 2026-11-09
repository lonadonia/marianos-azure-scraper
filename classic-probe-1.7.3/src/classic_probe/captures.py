"""Each answer kept on disk, durably, before the next paid step (1.7.0, finding C4).

A capture is written in three moves: the kept copy and its metadata to ``.part`` files (flushed and synced),
each renamed into place (an atomic rename on the same disk), then indexed in the ledger's ``capture`` table.
A crash leaves at worst ``.part`` files (removed on recovery: never indexed, never evidence) or a complete
pair not yet indexed (indexed on recovery once its hash checks out). The evidence export reads this index and
these files only, never the memory of a process, so it can be rebuilt after any crash.

The copy kept is sanitized: values under credential-like keys are replaced, and each raw page goes through the
retailer collector's own sanitizer. Its SHA-256 (public: anyone can check it against the file) is kept beside
the SHA-256 of the response as received (private), so the two are matched without publishing the original.

1.7.1 (the client's review of 1.7.0, finding C4):

- the response as received is kept too, privately: the request worker writes it under the dispatch's own
  number in ``private/raw/`` (``dispatch_NNN.body`` with ``dispatch_NNN.status.json``; owner-only on Linux and
  macOS), synced and renamed durably, and nothing deletes it. It is never exported or published;
- a crash after the answer arrived and before its kept copy was indexed loses nothing:
  :meth:`CaptureStore.recover` keeps the copy from those files, once the body matches the hash in its status,
  without a paid refetch. A body cut short (``dispatch_NNN.partial``) is recorded once in the ledger as a
  ``PARTIAL_RESPONSE`` event (length, SHA-256, never complete) and never indexed as an answer;
- every file is renamed into place durably (durable.py: a synced directory, or a write-through rename on
  Windows), and the recovery stops when the session's time runs out, saying what it did not reach.

1.7.2 (the client's review of 1.7.1, finding C4):

- a raw answer is kept only when its status carries the identity of the ledger's own dispatch of that
  number (campaign, ledger genesis, number, step, attempt, payload hash). Files of another campaign, or of
  another dispatch, left in the same folder are refused and left as they are; a status without an identity
  (written before 1.7.2) is refused too;
- a body whose status calls it whole although it is shorter than the length its answer declared (as the
  1.7.1 worker wrote a body cut short) is recorded as a ``PARTIAL_RESPONSE``, with the length declared, and
  never indexed as an answer; the file stays as it was found;
- a partial body's record names, when its status survived, the HTTP status, the error and the length
  declared.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import urllib.parse
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from classic_probe import durable
from classic_probe.transport import ProviderResponse, declared_shortfall

if TYPE_CHECKING:
    from classic_probe.ledger import Ledger

_SECRET_KEYS = re.compile(r"(?i)authori[sz]ation|cookie|password|token|secret|session")
IDENTITY_KEYS = ("campaign_id", "ledger_genesis_id", "seq", "step", "attempt", "payload_sha256")


def identity_problem(
    status: Mapping[str, Any], ledger: Ledger, row: Mapping[str, Any], seq: int
) -> str | None:
    """None when a worker's status names this ledger's dispatch ``seq``; else why not (1.7.2, C4)."""
    ident = status.get("identity")
    if not isinstance(ident, Mapping):
        return "its status carries no dispatch identity (written before 1.7.2, or not by a request worker)"
    expected = {
        "campaign_id": ledger.campaign_id,
        "ledger_genesis_id": ledger.genesis_id,
        "seq": seq,
        "step": row["step"],
        "attempt": row["attempt"],
        "payload_sha256": row["payload_sha256"],
    }
    wrong = [k for k in IDENTITY_KEYS if ident.get(k) != expected[k]]
    if wrong:
        return "its identity is not this dispatch's (" + ", ".join(wrong) + " differ)"
    return None


def sanitize(value: Any) -> Any:
    """A response as it may be kept: values under credential-like keys are replaced."""
    if isinstance(value, Mapping):
        return {k: "[REMOVED]" if _SECRET_KEYS.search(str(k)) else sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def kept_response(original: bytes, retailer: str = "walmart") -> tuple[bytes, list[dict[str, Any]]]:
    """A response as it may be kept as evidence: values under credential-like keys replaced, and each raw page
    passed through the retailer collector's sanitizer (vendor/walmart_sanitize.py: session and trace
    identifiers, tokens, other scripts and inlined data removed; product, price, store and fulfillment data
    untouched; vendor/marianos_sanitize.py for Mariano's). A body that is not JSON is kept only as its hash
    and length: it was not the documented structure."""
    from classic_probe.vendor import marianos_sanitize, walmart_sanitize

    try:
        body = json.loads(original)
    except ValueError:
        note = {"not_json": True, "bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()}
        return json.dumps(note, sort_keys=True).encode("utf-8"), []
    pages: list[dict[str, Any]] = []
    if isinstance(body, Mapping) and isinstance(body.get("results"), list):
        for i, result in enumerate(body["results"]):
            if isinstance(result, dict) and isinstance(result.get("content"), str) and retailer == "marianos":
                # 1.6.0: a Mariano's page through the Mariano's collector's own sanitizer (scripts other than
                # the page state removed, styles emptied, inlined data URIs replaced).
                kept_page, mreport = marianos_sanitize.sanitize_html(result["content"])
                result["content"] = kept_page
                pages.append(
                    {
                        "result": i,
                        "state_script_kept": mreport.state_script_kept,
                        "scripts_removed": mreport.scripts_removed,
                        "styles_emptied": mreport.styles_emptied,
                        "data_uris_replaced": mreport.data_uris_replaced,
                        "input_sha256": mreport.input_sha256,
                        "output_sha256": mreport.output_sha256,
                    }
                )
            elif isinstance(result, dict) and isinstance(result.get("content"), str):
                clean, report = walmart_sanitize.sanitize_html(result["content"])
                result["content"] = clean
                pages.append(
                    {
                        "result": i,
                        "page_data_kept": report.page_data_kept,
                        "page_data_values_redacted": report.page_data_values_redacted,
                        "other_values_redacted": report.other_values_redacted,
                        "scripts_removed": report.scripts_removed,
                        "input_sha256": report.input_sha256,
                        "output_sha256": report.output_sha256,
                    }
                )
    return json.dumps(sanitize(body), sort_keys=True).encode("utf-8"), pages


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    """``path`` holds ``data`` whole or not at all: a ``.part`` file, flushed, synced and renamed into place
    durably (1.7.1: a write-through rename on Windows, durable.py)."""
    durable.write(path, data)


def _never(_: Any = None) -> float:
    return float("inf")


def _location(value: str | None) -> str | None:
    """A redirect's target as it may be kept: scheme, host and path only (a query could carry a token)."""
    if not value:
        return None
    u = urllib.parse.urlsplit(value)
    return urllib.parse.urlunsplit((u.scheme, u.netloc.rpartition("@")[2], u.path, "", ""))


class CaptureStore:
    """The kept answers of one retailer's part of a campaign, in ``directory``."""

    def __init__(self, directory: Path, retailer: str) -> None:
        self.directory = directory
        self.retailer = retailer

    def data_name(self, seq: int) -> str:
        return f"response_{seq:03d}.json.gz"

    def meta_name(self, seq: int) -> str:
        return f"response_{seq:03d}.meta.json"

    @property
    def raw_dir(self) -> Path:
        """The responses as received (1.7.1, C4): private, never exported."""
        return self.directory / "private" / "raw"

    def raw_stem(self, seq: int) -> Path:
        """Where the request worker writes dispatch ``seq``'s answer: its stable name."""
        return self.raw_dir / f"dispatch_{seq:03d}"

    def persist(self, seq: int, step: str, response: ProviderResponse) -> dict[str, Any]:
        """Write one answer's kept copy and metadata durably; returns the record to index."""
        if not self.directory.is_dir():
            self.directory.mkdir(parents=True, exist_ok=True)
            durable.sync_dir(self.directory.parent)
        kept, pages = kept_response(response.body, self.retailer)
        data = gzip.compress(kept, mtime=0)
        record: dict[str, Any] = {
            "seq": seq,
            "file": self.data_name(seq),
            "http_status": response.http_status,
            "body_bytes": len(response.body),
            "truncated": response.truncated,
            "original_sha256": sha256(response.body),
            "kept_sha256": sha256(kept),
            "sanitized": kept != response.body,
            "detail": {
                "step": step,
                "file_sha256": sha256(data),
                "raw_pages": pages,
                "headers": sanitize(dict(response.headers)),
                "redirect_location": _location(response.redirect_location),
                "elapsed_s": response.elapsed_s,
            },
        }
        atomic_write(self.directory / self.data_name(seq), data)
        atomic_write(
            self.directory / self.meta_name(seq),
            (json.dumps(record, sort_keys=True, indent=1) + "\n").encode("utf-8"),
        )
        return record

    def recover(
        self,
        ledger: Ledger,
        *,
        time_left: Callable[[], float] = _never,
        min_left_s: float = 0.0,
        lock_refused: str | None = None,
    ) -> dict[str, Any]:
        """After a crash, in this order and while ``time_left()`` stays above ``min_left_s`` (1.7.1, C2):

        1. ``.part`` files of kept copies are removed (never indexed, never evidence);
        2. a complete kept copy the index lacks is indexed when its file matches its recorded hash;
        3. an answer the worker wrote whole (``private/raw/dispatch_NNN.body`` and its status) that has no
           kept copy gets one, and is indexed: an answer that reached the disk is never lost or fetched again;
        4. a partial body is recorded once as a ``PARTIAL_RESPONSE`` event, never indexed.

        What the time did not allow, or the ledger's lock refused, is listed (``not_reached``) and left as it
        is for the next recovery: nothing is assumed. ``lock_refused`` (why) says the lock was already refused
        in this session's time: no write waits for it again."""
        from classic_probe.ledger import LockNotObtained

        out: dict[str, Any] = {
            "part_files_removed": [],
            "indexed_on_recovery": [],
            "kept_from_raw": [],
            "partial_recorded": [],
            "refused": [],
            "not_reached": [],
        }
        if not self.directory.is_dir():
            return out

        def time_up(what: str) -> bool:
            if time_left() > min_left_s:
                return False
            out["not_reached"].append({"what": what, "why": "the session's time ran out"})
            return True

        for part in sorted(self.directory.glob("response_*.part")):
            part.unlink()
            out["part_files_removed"].append(part.name)
        indexed = {int(c["seq"]) for c in ledger.captures()}
        rows = {int(r["seq"]): r for r in ledger.rows()}
        locked = lock_refused is not None

        def index(seq: int, record: dict[str, Any], what: str) -> bool:
            nonlocal locked
            if locked or time_up(what):
                if locked:
                    why = (
                        f"the ledger's write lock: {lock_refused}"
                        if lock_refused
                        else "the ledger's write lock"
                    )
                    out["not_reached"].append({"what": what, "why": why + " (not waited for again)"})
                return False
            try:
                ledger.record_capture(seq, record)
            except LockNotObtained as exc:
                locked = True
                out["not_reached"].append({"what": what, "why": f"the ledger's write lock: {exc}"})
                return False
            indexed.add(seq)
            return True

        for meta in sorted(self.directory.glob("response_*.meta.json")):
            record = json.loads(meta.read_text(encoding="utf-8"))
            seq = int(record["seq"])
            if seq in indexed:
                continue
            path = self.directory / str(record["file"])
            if seq not in rows:
                out["refused"].append({"file": meta.name, "why": "no dispatch of this number in the ledger"})
            elif not path.is_file() or sha256(path.read_bytes()) != record["detail"]["file_sha256"]:
                out["refused"].append(
                    {"file": meta.name, "why": "its data file is missing or does not match"}
                )
            elif index(seq, record, meta.name):
                out["indexed_on_recovery"].append(seq)

        raw = self.raw_dir
        if raw.is_dir():
            statuses: dict[int, dict[str, Any]] = {}
            foreign: set[int] = set()  # 1.7.2: files that are not this ledger's dispatch's
            short: dict[int, tuple[Path, int]] = {}  # 1.7.2: "whole" bodies shorter than declared
            for status_file in sorted(raw.glob("dispatch_*.status.json")):
                seq = int(status_file.name.split("_", 1)[1].split(".", 1)[0])
                try:
                    status = json.loads(status_file.read_text(encoding="utf-8"))
                except ValueError:
                    status = None
                if not isinstance(status, dict):
                    out["refused"].append({"file": status_file.name, "why": "its status cannot be read"})
                    foreign.add(seq)
                    continue
                if seq in indexed:
                    continue
                if seq not in rows:
                    out["refused"].append({"file": status_file.name, "why": "no dispatch of this number"})
                    foreign.add(seq)
                    continue
                problem = identity_problem(status, ledger, rows[seq], seq)
                if problem:
                    out["refused"].append({"file": status_file.name, "why": problem})
                    foreign.add(seq)
                    continue
                statuses[seq] = status
                if not status.get("ok"):
                    continue  # its partial body, if any, is recorded below
                stem = self.raw_stem(seq)
                body_path = stem.with_name(stem.name + ".body")
                part = stem.with_name(stem.name + ".body.part")
                if not body_path.is_file() and part.is_file():
                    body_path = part  # the crash came between the status and the body's final rename
                if not body_path.is_file():
                    out["refused"].append({"file": status_file.name, "why": "its body is missing"})
                    continue
                if time_up(body_path.name):
                    break
                body = body_path.read_bytes()
                if sha256(body) != status.get("sha256"):
                    out["refused"].append(
                        {"file": body_path.name, "why": "its body does not match its status"}
                    )
                    continue
                missing = declared_shortfall(status)
                if missing:  # 1.7.2 (C4): called whole, but shorter than its answer declared
                    short[seq] = (body_path, missing)
                    continue
                if body_path == part:
                    durable.replace(part, stem.with_name(stem.name + ".body"))
                response = ProviderResponse(
                    int(status["status"]),
                    body,
                    {str(k): str(v) for k, v in status.get("headers") or []},
                    truncated=bool(status.get("truncated")),
                    redirect_location=status.get("redirect_location"),
                    elapsed_s=float(status.get("elapsed_s") or 0.0),
                )
                record = self.persist(seq, str(rows[seq]["step"]), response)
                if index(seq, record, body_path.name):
                    out["indexed_on_recovery"].append(seq)
                    out["kept_from_raw"].append(seq)

            recorded = set()
            for e in ledger.events():
                if e["kind"] == "PARTIAL_RESPONSE":
                    try:
                        recorded.add(int(json.loads(e["detail"])["seq"]))
                    except (ValueError, KeyError, TypeError):
                        continue
            found: dict[int, tuple[Path, int]] = {}
            for partial in sorted(raw.glob("dispatch_*.partial")):
                found[int(partial.name.split("_", 1)[1].split(".", 1)[0])] = (partial, 0)
            found.update(short)
            for seq in sorted(found):
                path, missing = found[seq]
                if seq in recorded or seq in indexed or seq in foreign:
                    continue
                if seq not in rows:
                    out["refused"].append({"file": path.name, "why": "no dispatch of this number"})
                    continue
                if locked:
                    out["not_reached"].append(
                        {"what": path.name, "why": "the ledger's write lock (not waited for again)"}
                    )
                    continue
                if time_up(path.name):
                    break
                data = path.read_bytes()
                detail: dict[str, Any] = {
                    "seq": seq,
                    "bytes": len(data),
                    "sha256": sha256(data),
                    "file": path.name,
                    "complete": False,
                    "found": "at a recovery",
                }
                status = statuses.get(seq)
                if status is None:
                    # the worker was killed between keeping the body and writing its status: nothing names
                    # the dispatch but the file's own name
                    detail["identity_checked"] = False
                else:
                    detail["identity_checked"] = True
                    for key in ("http_status", "error"):
                        if status.get(key) is not None:
                            detail[key] = status[key]
                    if status.get("status") is not None:
                        detail["http_status"] = status["status"]
                    if status.get("declared_bytes") is not None:
                        detail["declared_bytes"] = int(status["declared_bytes"])
                if missing:
                    detail["declared_bytes"] = len(data) + missing
                    detail["why"] = (
                        f"its status called it whole, but {missing} of the {len(data) + missing} bytes its "
                        "answer declared never came"
                    )
                try:
                    ledger.event("PARTIAL_RESPONSE", json.dumps(detail, sort_keys=True))
                except LockNotObtained as exc:
                    locked = True
                    out["not_reached"].append({"what": path.name, "why": f"the ledger's write lock: {exc}"})
                    break
                out["partial_recorded"].append(seq)
        return out

    def verify(
        self, ledger: Ledger, *, time_left: Callable[[], float], min_left_s: float
    ) -> tuple[list[dict[str, Any]], bool]:
        """Each indexed capture against its file, while time is left. Returns the entries and whether every
        capture was checked; one not checked in time is listed as unverified, never as good."""
        entries: list[dict[str, Any]] = []
        complete = True
        for c in ledger.captures():
            entry = {
                "seq": c["seq"],
                "file": c["file"],
                "step": c["detail"].get("step"),
                "http_status": c["http_status"],
                "body_bytes": c["body_bytes"],
                "truncated": bool(c["truncated"]),
                "original_sha256": c["original_sha256"],
                "kept_sha256": c["kept_sha256"],
                "sanitized": bool(c["sanitized"]),
                "raw_pages": c["detail"].get("raw_pages", []),
                "headers": c["detail"].get("headers", {}),
                "redirect_location": c["detail"].get("redirect_location"),
            }
            if time_left() < min_left_s:
                entry["verified"] = None
                entry["why"] = "not checked: the session's time ran out"
                complete = False
            else:
                path = self.directory / str(c["file"])
                try:
                    ok = sha256(gzip.decompress(path.read_bytes())) == c["kept_sha256"]
                except (OSError, EOFError, gzip.BadGzipFile):
                    ok = False
                entry["verified"] = ok
                if not ok:
                    complete = False
            entries.append(entry)
        return entries, complete
