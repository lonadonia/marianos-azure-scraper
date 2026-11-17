"""PRIVATE (workstation): requests in flight at once, per stage, from the stage's ledger rows (ledger_reservations.csv),
no network.

    python -I peak_in_flight.py OUT.txt EVIDENCE_DIR [EVIDENCE_DIR ...]

A row is in flight from its dispatched_at to its updated_at (the moment it was settled, or marked unknown when the
process that sent it had stopped; for those the true end is unknown, so their interval is an upper bound). Prints, per
stage and lease: rows, peak in flight and when, and the rows still in flight at each process end. The gate of the trial
ledger lets at most as many requests fly as the stage has lanes (2 for F2).
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

out, *evs = sys.argv[1:]
L = ["Requests in flight at once, from each stage's ledger rows (dispatched_at -> updated_at). Rows marked unknown were",
     "in flight when their process stopped; their interval ends when the ledger marked them unknown (an upper bound).", ""]
overall = 0
for ev in map(Path, evs):
    rows = list(csv.DictReader((ev / "ledger_reservations.csv").open(encoding="utf-8", newline="")))
    by_lease: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_lease[r["lease_id"]].append(r)
    L.append(f"== {ev.name}: {len(rows)} rows, states {dict(Counter(r['state'] for r in rows))}")
    for lease, rs in sorted(by_lease.items()):
        ev_points = []
        for r in rs:
            if not r["dispatched_at"]:
                continue
            ev_points.append((r["dispatched_at"], 1, r["id"]))
            ev_points.append((r["updated_at"], -1, r["id"]))
        ev_points.sort(key=lambda x: (x[0], x[1]))
        cur = peak = 0
        at = ""
        for t, d, _ in ev_points:
            cur += d
            if cur > peak:
                peak, at = cur, t
        overall = max(overall, peak)
        unk = [r for r in rs if r["state"] in ("unknown", "dispatched")]
        L.append(f"   lease {lease}: {len(rs)} rows, peak in flight {peak} (first reached {at}); unknown at the end "
                 f"{len(unk)}" + (": " + ", ".join(f"{r['purpose']} dispatched {r['dispatched_at'][11:23]}" for r in unk)
                                  if unk else ""))
    L.append("")
L.append(f"highest peak over all stages: {overall}")
Path(out).write_bytes(("\n".join(L) + "\n").encode("utf-8"))
print("\n".join(L))
