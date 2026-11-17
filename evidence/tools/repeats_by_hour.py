"""The site serving page 1 again for a page 2 or later, by hour and run, from the runs' own listing-page rows. No network.

    python -I repeats_by_hour.py OUT.csv EVIDENCE_DIR [EVIDENCE_DIR ...]

EVIDENCE_DIR is a stage's evidence folder (db_listing_pages.csv), named after its stage. A row is one answer of the site to one request
(a first ask or a re-ask); rows are counted once by their id across folders (the slices of one run each hold every
row of the run so far). Only answers to a page 2 or later judged "new" (a page of products not seen before in the
listing) or "repeated" (exactly the products of an earlier page) are counted; an answer judged otherwise (malformed,
failed, partial overlap, another context) is left out. For each repeated answer, the earlier page it repeats is
named (in every run of 2026-11-16, page 1). Prints the table and writes it to OUT.csv.
"""

from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

csv.field_size_limit(10**9)


def main() -> int:
    out, dirs = Path(sys.argv[1]), [Path(a) for a in sys.argv[2:]]
    seen: set[str] = set()
    rows = []
    stages: dict[str, list[str]] = collections.defaultdict(list)  # run -> the evidence folders that hold it, in order
    for d in dirs:
        for r in csv.DictReader((d / "db_listing_pages.csv").open(encoding="utf-8", newline="")):
            if d.name not in stages[r["run_id"]]:
                stages[r["run_id"]].append(d.name)
            if r["id"] not in seen:
                seen.add(r["id"])
                rows.append(r)
    rows.sort(key=lambda r: r["observed_at"])
    first_pages: dict[tuple, dict[int, tuple]] = collections.defaultdict(dict)
    agg: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    repeats_of: dict[tuple[str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    for r in rows:
        key = (r["run_id"], r["csv_row_index"], r["taxonomy_id"], r["partition_key"], r["requested_filter"])
        page = int(r["requested_page"] or 0)
        ids = tuple(json.loads(r["identities"] or "[]"))
        hour = r["observed_at"][:13].replace(" ", "T") + "Z"
        if page >= 2 and r["verdict"] in ("new", "repeated"):
            agg[(hour, r["run_id"])][r["verdict"]] += 1
            if r["verdict"] == "repeated":
                match = sorted(p for p, v in first_pages[key].items() if v == ids)
                repeats_of[(hour, r["run_id"])][",".join(map(str, match)) or "none found"] += 1
        if r["verdict"] in ("new", "completed") and ids:
            first_pages[key].setdefault(page, ids)
    table = []
    for (hour, run), c in sorted(agg.items()):
        n = c["new"] + c["repeated"]
        table.append({"hour_utc": hour, "run_id": run, "stages": "+".join(stages[run]), "answers_page2_or_later": n, "new": c["new"],
                      "repeated": c["repeated"], "repeated_share": f"{c['repeated'] / n:.2f}",
                      "repeated_answers_repeat_page": "; ".join(f"{k}: {v}" for k, v in
                                                                sorted(repeats_of[(hour, run)].items()))})
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(table)
    for t in table:
        print(f"{t['hour_utc']}  {t['stages']:<16} answers {t['answers_page2_or_later']:4}  new {t['new']:4}  "
              f"repeated {t['repeated']:4}  share {float(t['repeated_share']):4.0%}  repeat of page {t['repeated_answers_repeat_page']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
