"""PRIVATE OPS (owner VM, as the ledger's owner, read-only): the ledger folder of the 1.10.0rc6 delivery, from the
campaign oxylabs-marianos-20261116 (the new credential's own ledger: every stage in it belongs to this delivery).

    python3.12 -I ledger_folder6.py LEDGER.sqlite3 OUT_DIR

Writes, in OUT_DIR (which must not exist), with its SHA256SUMS: STAGES.csv (each stage: opened, closed, ceiling, revision, command,
outcome, its reservations by state, settled USD, unknown outcomes charged at the reservation rate), RESERVATIONS.csv
(every reservation: what was reserved, for which stage and purpose, dispatched, settled or held unknown),
ENVELOPES.csv, LEASES.csv (without the lease token), META.csv (the campaign's own record: authority, cap, headroom,
rate and its source, what was not carried over) and EVENTS.csv (the whole hash-chained event log: seq, at, kind, ref,
detail, prev_hash, hash). Prints the totals. Opens the database read-only; sends nothing anywhere.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

RATE = Decimal("0.0015")


def main() -> int:
    db, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True)  # refuses an existing folder
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=15)
    con.row_factory = sqlite3.Row

    def dump(name: str, sql: str, cols: list[str]) -> int:
        n = 0
        with (out / name).open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(cols)
            for r in con.execute(sql):
                w.writerow([r[c] if r[c] is not None else "" for c in cols])
                n += 1
        return n

    stages = []
    tot: Counter = Counter()
    usd = Decimal(0)
    for st in con.execute("SELECT * FROM stages ORDER BY opened_at"):
        by: Counter = Counter()
        settled = Decimal(0)
        for r in con.execute("SELECT state, settled_usd FROM reservations WHERE stage_id = ?", (st["stage_id"],)):
            by[r["state"]] += 1
            if r["state"] == "settled":
                settled += Decimal(r["settled_usd"] or "0")
        held = by["unknown"] + by["dispatched"] + by["reserved"]
        tot.update(by)
        usd += settled + held * RATE
        stages.append({
            "stage_id": st["stage_id"], "opened_at": st["opened_at"], "closed_at": st["closed_at"] or "",
            "source_revision": st["source_revision"], "max_requests": st["max_requests"], "max_usd": st["max_usd"],
            "deadline_utc": st["deadline_utc"], "command": st["command"], "reservations": sum(by.values()),
            "settled": by["settled"], "unknown_or_in_flight_charged": held, "released_unsent": by["released_unsent"],
            "settled_usd": f"{settled:.6f}", "unknown_charged_usd": f"{held * RATE:.6f}",
            "outcome": st["outcome"] or "",
        })
    with (out / "STAGES.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(stages[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(stages)
    res_cols = ["id", "created_at", "project", "stage_id", "lease_id", "dispatch_key", "purpose", "endpoint", "target",
                "worst_results", "worst_usd", "state", "dispatched_at", "provider_job_id", "http_status",
                "result_status", "settled_results", "settled_usd", "settlement_kind", "settlement_basis",
                "capture_sha256", "updated_at"]
    n_res = dump("RESERVATIONS.csv", "SELECT * FROM reservations ORDER BY id", res_cols)
    dump("ENVELOPES.csv", "SELECT * FROM envelopes ORDER BY id", ["id", "at", "project", "envelope_usd", "reason", "actor"])
    dump("LEASES.csv", "SELECT * FROM leases ORDER BY id",  # the token, a bearer secret of the lease, is left out
         ["id", "project", "holder", "host", "pid", "acquired_at", "expires_at", "released_at", "release_reason"])
    dump("META.csv", "SELECT key, value FROM meta ORDER BY key", ["key", "value"])
    n_ev = dump("EVENTS.csv", "SELECT * FROM events ORDER BY seq",
                ["seq", "at", "kind", "ref", "detail", "prev_hash", "hash"])
    kinds = Counter(r["kind"] for r in con.execute("SELECT kind FROM events"))
    sums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in sorted(out.iterdir()) if p.is_file()]
    (out / "SHA256SUMS").write_bytes(("\n".join(sums) + "\n").encode("utf-8"))
    print(json.dumps({"stages": len(stages), "reservations": n_res, "reservations_by_state": dict(tot),
                      "usd_settled_plus_unknown_charged": f"{usd:.6f}", "events": n_ev,
                      "events_by_kind": dict(sorted(kinds.items()))}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
