"""PRIVATE (workstation): the coverage of ONE run against the 1.9 baseline queue (302 product listings and the
Coupons route), listing by listing. No network.

    python -I coverage_vs_queue.py QUEUE_190.csv COVERAGE_RECONCILIATION.csv RUN_LABEL OUT.csv

QUEUE_190.csv is evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv of review-1.10.0rc3-20261112 (the baseline: 42 of 302
complete, 40 with products and 2 empty; 38 stopped on repeats; 222 not collected). COVERAGE_RECONCILIATION.csv is the
run's own export. A queue listing is matched to the run's top-level listing of the same CSV row and taxonomy ID
(no parent); the run's status is copied as the collector wrote it (DONE, EMPTY, INCOMPLETE, NOT_COLLECTED, ...),
nothing is inferred. Prints the counts; writes one row per queue listing.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

queue_path, cov_path, label, out_path = sys.argv[1:]
queue = list(csv.DictReader(Path(queue_path).open(encoding="utf-8", newline="")))
cov = list(csv.DictReader(Path(cov_path).open(encoding="utf-8", newline="")))
top = {}
for r in cov:
    if (r.get("parent_listing") or "") == "" and r.get("listing_id"):
        key = (r["csv_row"], r["listing_id"])
        if key in top:
            raise SystemExit(f"REFUSED: two top-level rows for {key}")
        top[key] = r
rows, counts, base = [], Counter(), Counter()
for q in queue:
    if q["row_kind"] == "coupon_catalogue":
        continue
    key = (q["csv_row"], q["taxonomy_id"])
    r = top.get(key)
    state = r["status"] if r else "NOT_IN_THE_RUN"
    counts[state] += 1
    base[q["latest_1_9_state"]] += 1
    rows.append([q["csv_row"], q["row_category"], q["taxonomy_id"], q["listing"], q["latest_1_9_state"],
                 q["stated_total"], q["products_read"], state,
                 r["reported_total"] if r else "", r["unique_identities"] if r else "",
                 (r["completion_reason"] if r else "")[:300]])
with Path(out_path).open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["csv_row", "row_category", "taxonomy_id", "listing", "state_1.9_baseline", "stated_total_1.9",
                "products_read_1.9", f"status_{label}", f"reported_total_{label}", f"unique_identities_{label}",
                f"completion_reason_{label}"])
    w.writerows(rows)
print(f"{len(rows)} product listings of the 1.9 queue; baseline: {dict(base)}")
print(f"{label}: {dict(counts)}")
done = counts.get("DONE", 0) + counts.get("EMPTY", 0)
print(f"{label}: {done} of {len(rows)} complete (DONE {counts.get('DONE', 0)}, EMPTY {counts.get('EMPTY', 0)})")
