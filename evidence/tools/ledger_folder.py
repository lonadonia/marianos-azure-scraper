"""PRIVATE (workstation): the ledger folder of the final delivery, read from the shared trial ledger (SQLite) after it
came back to the workstation, read-only, no network.

    python -I ledger_folder.py LEDGER.sqlite3 STAGE_DEFS.json OUT_DIR

Writes OUT_DIR/STAGES_OF_THIS_DELIVERY.csv (each stage of this delivery: when it was opened and closed, its ceiling,
its revision, its outcome as recorded at the close, and its reservations by state with the settled USD and the
unknown outcomes held), OUT_DIR/ENVELOPES.csv (the envelopes, append-only), OUT_DIR/EVENTS_OF_THE_DAY_SUMMARY.csv
(events of 2026-11-16 counted by kind) and OUT_DIR/NOTES_20261116.txt (the ledger's note events of that day, verbatim).
Prints the totals.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

db, defs, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
stage_ids = {v["stage_id"]: k for k, v in json.loads(defs.read_text(encoding="utf-8"))["stages"].items()}
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
out.mkdir(parents=True, exist_ok=True)
rows_out = []
tot = Counter()
usd = Decimal(0)
for st in con.execute("SELECT * FROM stages WHERE opened_at >= '2026-11-16' ORDER BY opened_at"):
    if st["stage_id"] not in stage_ids:
        continue
    by = Counter()
    settled_usd = Decimal(0)
    for r in con.execute("SELECT state, settled_usd FROM reservations WHERE stage_id = ?", (st["stage_id"],)):
        by[r["state"]] += 1
        if r["state"] == "settled":
            settled_usd += Decimal(r["settled_usd"] or "0")
    held = by["unknown"] + by["dispatched"] + by["reserved"]
    tot.update(by)
    usd += settled_usd + Decimal(held) * Decimal("0.0015")
    rows_out.append({
        "key": stage_ids[st["stage_id"]], "stage_id": st["stage_id"], "opened_at": st["opened_at"],
        "closed_at": st["closed_at"] or "", "source_revision": st["source_revision"],
        "max_requests": st["max_requests"], "max_usd": st["max_usd"], "command": st["command"],
        "reservations": sum(by.values()), "settled": by["settled"], "unknown_held": held,
        "released_unsent": by["released_unsent"], "settled_usd": f"{settled_usd:.6f}",
        "unknown_charged_usd": f"{Decimal(held) * Decimal('0.0015'):.6f}", "outcome": st["outcome"] or "",
    })
with (out / "STAGES_OF_THIS_DELIVERY.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows_out[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows_out)
with (out / "ENVELOPES.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["id", "at", "project", "envelope_usd", "reason", "actor"])
    for e in con.execute("SELECT id, at, project, envelope_usd, reason, actor FROM envelopes ORDER BY id"):
        w.writerow(list(e))
kinds = Counter(r["kind"] for r in con.execute("SELECT kind FROM events WHERE at >= '2026-11-16'"))
with (out / "EVENTS_OF_THE_DAY_SUMMARY.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["kind", "events_on_2026-11-16"])
    for k, n in sorted(kinds.items()):
        w.writerow([k, n])
notes = [f"seq {r['seq']} at {r['at']} kind {r['kind']} ref {r['ref']}\n  {r['detail']}"
         for r in con.execute("SELECT * FROM events WHERE at >= '2026-11-16' AND kind LIKE '%note%' ORDER BY seq")]
(out / "NOTES_20261116.txt").write_bytes(("\n".join(notes) + "\n").encode("utf-8"))
last = con.execute("SELECT max(seq) FROM events").fetchone()[0]
print(json.dumps({"stages": len(rows_out), "reservations_by_state": dict(tot), "usd_with_unknown_charged": f"{usd:.4f}",
                  "events_total": last, "notes_of_the_day": len(notes)}, indent=1))
