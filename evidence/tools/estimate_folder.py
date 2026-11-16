"""PRIVATE (workstation): the updated full-cycle estimate from the full run F2's own measures, no network.

    python -I estimate_folder.py EV_ROOT CENSUS_CSV LEDGER_END_JSON OUT_DIR

EV_ROOT holds F2a..F2d (each: ledger_reservations.csv, harness_runs.jsonl, db_collection_segments.csv), F2d's
listing-page log of the whole run (db_listing_pages.csv) and F2d's export (coverage_reconciliation.csv,
coverage_by_csv_row.csv). A completed page is a completed answer of the listing-page log; the coverage file's own
per-listing counts are recorded beside it (they count a listing that is both a listing and a parent's partition
once for each, so their sum is larger). CENSUS_CSV is FULL_SCOPE_BY_CSV_ROW.csv of tag
review-1.10.0rc3-20261112 (2026-11-02). Writes OUT_DIR/ESTIMATE_1.10.0rc5.json (every input, formula and result) and
OUT_DIR/ROWS_F2_VS_CENSUS.csv (per CSV row: the census of 2026-11-02 against what F2 read). Prints the summary.

Kept from the historical estimate (review/COST_AND_RUNTIME_REPORT.md at that tag, scenario B, all rows): the range of
listing pages a full run reads (3,019 to 4,826; the unmeasured rows 7, 9, 11, 13 and 17 included as a range), the 3
submissions per run outside listing pages, the twice-weekly cadence (8.67 runs a month) and the reservation rate (USD
0.0015 a submission, a list price, not an invoice). Replaced by F2's measures: the submissions per completed listing
page (1.3 before) and the time per completed page (57.7 s rendered and one lane in 1.8; F2 is unrendered, two lanes).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

csv.field_size_limit(1 << 30)
EV, CENSUS, LEDGER_END, OUT = map(Path, sys.argv[1:5])
SLICES = ["F2a", "F2b", "F2c", "F2d"]
RATE = 0.0015
PAGES_LO, PAGES_HI, PER_RUN = 3019, 4826, 3
RUNS_A_MONTH = 8.67


def rows(p: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(p.open(encoding="utf-8", newline="")))


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))


subs = settled = unknown = 0
seg_seconds = 0.0
exec_seconds = 0.0
for k in SLICES:
    led = rows(EV / k / "ledger_reservations.csv")
    subs += len(led)
    settled += sum(r["state"] == "settled" for r in led)
    unknown += sum(r["state"] in ("unknown", "dispatched") for r in led)
    for h in (json.loads(x) for x in (EV / k / "harness_runs.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()):
        if str(h.get("kind", "")).startswith("refused-start"):
            continue
        exec_seconds += float(h.get("seconds") or 0)
segs = {}
for k in SLICES:
    for r in rows(EV / k / "db_collection_segments.csv"):
        segs[r["id"]] = r
for r in segs.values():
    if r.get("started_at") and r.get("ended_at"):
        seg_seconds += (ts(r["ended_at"]) - ts(r["started_at"])).total_seconds()
exp = EV / "F2d" / "export"
cov = rows(exp / "coverage_reconciliation.csv")
by_row = {r["csv_row"]: r for r in rows(exp / "coverage_by_csv_row.csv")}
top = [r for r in cov if not r["parent_listing"]]
log = rows(EV / "F2d" / "db_listing_pages.csv")
done = [r for r in log if r["state"] == "completed"]
pages_completed = len(done)  # completed answers of the run's listing-page log
pages_distinct = len({(r["taxonomy_id"], r["partition_key"], r["route"], r["requested_page"], r["requested_filter"])
                      for r in done})
coverage_sum = sum(int(r["pages_completed"] or 0) for r in cov)
listing_ids = [r["listing_id"] for r in cov]
counted_twice = sorted({x for x in listing_ids if listing_ids.count(x) > 1})
reported = defaultdict(int)
for r in top:
    if r["reported_total"]:
        reported[r["csv_row"]] += int(r["reported_total"])
census = {r["csv_row"]: r for r in rows(CENSUS)}
led_end = json.loads(LEDGER_END.read_text(encoding="utf-8"))
spend_usd = float(led_end["projects"]["marianos"]["spendable_in_envelope_usd"])

ratio = subs / pages_completed
sec_exec = exec_seconds / pages_completed
sec_seg = seg_seconds / pages_completed


def run_subs(pages: int) -> int:
    return round(pages * ratio + PER_RUN)


lo, hi = run_subs(PAGES_LO), run_subs(PAGES_HI)
rem_lo, rem_hi = max(0, lo - subs), max(0, hi - subs)
res = {
    "inputs": {
        "f2_slices": SLICES, "f2_submissions": subs, "f2_settled": settled, "f2_unknown_charged": unknown,
        "f2_listing_pages_completed": pages_completed, "f2_listing_pages_completed_distinct": pages_distinct,
        "f2_listing_page_answers": len(log),
        "coverage_file_sum_of_pages_completed": coverage_sum,
        "coverage_file_listings_counted_twice": counted_twice,
        "f2_execution_seconds": round(exec_seconds, 1),
        "f2_collection_segment_seconds": round(seg_seconds, 1), "lanes": 2,
        "historical_pages_per_run": [PAGES_LO, PAGES_HI], "historical_submissions_per_run": [3928, 6277],
        "historical_usd_per_run": [5.89, 9.41], "historical_hours_one_worker": [48.4, 77.3],
        "historical_usd_a_month": [51.1, 81.6], "submissions_outside_listing_pages_per_run": PER_RUN,
        "runs_a_month_twice_weekly": RUNS_A_MONTH, "rate_usd_per_submission": RATE,
        "marianos_spendable_usd_at_the_end": spend_usd,
    },
    "measured": {
        "submissions_per_completed_page": round(ratio, 3),
        "execution_seconds_per_completed_page": round(sec_exec, 2),
        "segment_seconds_per_completed_page": round(sec_seg, 2),
    },
    "estimate": {
        "submissions_per_run": [lo, hi],
        "usd_per_run": [round(lo * RATE, 2), round(hi * RATE, 2)],
        "hours_per_run_two_lanes": [round(PAGES_LO * sec_exec / 3600, 1), round(PAGES_HI * sec_exec / 3600, 1)],
        "usd_a_month_twice_weekly": [round(lo * RATE * RUNS_A_MONTH, 1), round(hi * RATE * RUNS_A_MONTH, 1)],
        "remaining_submissions_to_complete_one_run": [rem_lo, rem_hi],
        "remaining_usd_to_complete_one_run": [round(rem_lo * RATE, 2), round(rem_hi * RATE, 2)],
        "shortfall_usd_against_marianos_spendable": [round(rem_lo * RATE - spend_usd, 2), round(rem_hi * RATE - spend_usd, 2)],
    },
    "formulas": {
        "submissions_per_completed_page": "F2's ledger rows (all four slices, unknown outcomes included) / completed answers of F2's "
                                          "listing-page log (a page completed twice counts twice)",
        "submissions_per_run": "historical listing pages x submissions_per_completed_page + 3",
        "hours_per_run_two_lanes": "historical listing pages x execution_seconds_per_completed_page / 3600",
        "remaining": "submissions_per_run - F2's submissions (F2's completed pages are part of a full run's pages)",
    },
    "caveats": [
        "F2 read the rows in order and was stopped by the collector while it read row 15: its ratio of repeated, "
        "malformed and re-asked answers is that of rows 1 to 15, applied to every row.",
        "The coverage file sums to more completed pages than the listing-page log holds: it counts a listing that is "
        "both a listing of its own and a partition of a parent once for each, and a listing of two CSV rows once per "
        "row. The estimate uses the log.",
        "The historical page range is the census of 2026-11-02 (rows 7, 9, 11, 13 and 17 unmeasured then, as a range); "
        "ROWS_F2_VS_CENSUS.csv compares it with what F2 read.",
        "USD at the reservation rate (a list price read 2026-11-03), not an invoice.",
    ],
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "ESTIMATE_1.10.0rc5.json").write_bytes((json.dumps(res, indent=1) + "\n").encode("utf-8"))
with (OUT / "ROWS_F2_VS_CENSUS.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["csv_row", "category", "census_products_listed_20261102", "census_pages_all_products",
                "census_not_measured", "f2_status", "f2_listings_planned", "f2_listings_complete",
                "f2_listings_incomplete", "f2_listings_not_read", "f2_reported_total_of_its_listings",
                "f2_pages_completed", "f2_distinct_products"])
    for row in sorted(set(census) | set(by_row), key=int):
        c, b = census.get(row, {}), by_row.get(row, {})
        w.writerow([row, b.get("category") or c.get("category", ""), c.get("products_listed", ""),
                    c.get("pages_all_products", ""), c.get("not_measured", ""), b.get("status", ""),
                    b.get("listings_planned", ""), b.get("listings_complete", ""), b.get("listings_incomplete", ""),
                    b.get("listings_not_read", ""), reported.get(row, ""), b.get("pages_completed", ""),
                    b.get("unique_identities", "")])
print(json.dumps({"measured": res["measured"], "estimate": res["estimate"]}, indent=1))
