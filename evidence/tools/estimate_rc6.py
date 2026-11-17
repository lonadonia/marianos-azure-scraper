"""The full-run estimate for 1.10.0rc6 from stored traces (offline): the pages a full run reads, per CSV row,
bottom-up where an earlier run saw the listing's own total (F2 for rows 1-15, L1/L2/S6 for rows 22-27; a listing
above the 250-result window counted as its page 1 plus its subdivisions' pages, each subdivision rounded up to
whole pages), from the census of 2026-11-02 where none did; submissions at F2's measured rate per completed page.

    python -I estimate_rc6.py F2_DIR TOTALS_JSON CENSUS_CSV OUT_JSON OUT_CSV
"""
import csv, json, math, sys
from collections import defaultdict
csv.field_size_limit(1 << 30)
F2, TOTALS, CENSUS, OUT, OUTCSV = sys.argv[1:6]
PER_PAGE, WINDOW, RATE, ENVELOPE = 24, 250, 0.0015, 4.90
BRAND = (4.5, 5.7)  # brand readings per plain page of a listing above the window (rc3 report, stored pages)
SUBS_PER_PAGE = 595 / 416  # F2: every ledger row (unknown outcomes included) per completed listing page
runs = list(csv.DictReader(open(f"{F2}/db_runs.csv", encoding="utf-8", newline="")))
nodes = json.loads(runs[0]["config_snapshot"])["plan"]["nodes"]
seen = json.load(open(TOTALS, encoding="utf-8"))  # taxonomy -> [run, total, status, [[child, count]], row]
census = {int(r["csv_row"]): r for r in csv.DictReader(open(CENSUS, encoding="utf-8", newline=""))}
planned = {n["taxonomy_id"] for n in nodes}
per_row = defaultdict(lambda: defaultdict(int))
dups, first = [], {}
for n in nodes:
    r = per_row[n["row_index"]]
    r["listings"] += 1
    t = n["taxonomy_id"]
    if t in first:
        r["listings_planned_twice"] += 1
        dups.append({"listing": t, "rows": [first[t], n["row_index"]], "kind": "a listing planned under two CSV rows"})
    first.setdefault(t, n["row_index"])
    s = seen.get(t)
    if not s:
        r["listings_without_total"] += 1
        continue
    run, total, status, kids, _ = s
    r["listings_with_total"] += 1
    if kids:
        r["above_window"] += 1
        sub = sum(math.ceil(c / PER_PAGE) for _, c in kids if c and c <= WINDOW)
        # A child listing itself above the window names no child of its own on the site: the collector reads it
        # through the retailer's brand filter, one reading per brand (1.8.0rc1). Measured on stored pages (rc3
        # report): brand readings take 4.5 to 5.7 times a listing's plain pages (cold cereal 68 against 12).
        leaves = [c for _, c in kids if c and c > WINDOW]
        r["leaves_above_window"] += len(leaves)
        r["leaf_plain_pages"] += sum(math.ceil(c / PER_PAGE) for c in leaves)
        r["subdivision_pages"] += sub
        r["pages_bottom_up"] += 1 + sub + len(leaves)  # each leaf's page 1, before its brand readings
        for child, c in kids:
            if child in planned:
                dups.append({"listing": child, "parent": t, "row": n["row_index"], "count": c,
                             "kind": "a subdivision that is also a listing of the plan"})
    else:
        r["pages_bottom_up"] += max(1, math.ceil(min(total, WINDOW) / PER_PAGE))
        if total > WINDOW:
            r["above_window_without_subdivisions"] += 1
both = [(per_row[k]["pages_bottom_up"], int(census[k]["census_pages_all_products"])) for k in per_row
        if per_row[k]["listings_without_total"] == 0 and k in census and int(census[k].get("census_pages_all_products") or 0)]
RATIO_HI = round(sum(b for b, _ in both) / sum(c for _, c in both), 3)
leaf_products = sum(c for t_, s in seen.items() for _, c in (s[3] or []) if c and c > WINDOW and s[4] <= 14)
row_products = sum(int(s[1]) for t_, s in seen.items() if s[4] <= 14 and not any(t_ == k for k, _ in []))
LEAF_SHARE = round(leaf_products / row_products, 3)
out_rows, lo_sum, hi_sum = [], 0.0, 0.0
for row in sorted(per_row):
    r = per_row[row]
    cen = census.get(row, {})
    cpages = int(cen.get("census_pages_all_products") or 0)
    share = r["listings_without_total"] / r["listings"]
    brand_lo, brand_hi = BRAND[0] * r["leaf_plain_pages"], BRAND[1] * r["leaf_plain_pages"]
    if r["listings_without_total"] == 0:
        lo, hi = r["pages_bottom_up"] + brand_lo, r["pages_bottom_up"] + brand_hi
        basis = "bottom-up from the listings' own totals; leaves above the window through brand readings"
    elif cpages:
        # The listings no run reached: the census's pages, times the ratio of bottom-up to census pages measured
        # on the rows that have both (low 1.0, high RATIO_HI), and the brand readings of leaves above the window at
        # the share of products measured in such leaves on rows 1-14 (LEAF_SHARE).
        un = cpages * share
        lo = r["pages_bottom_up"] + brand_lo + un * (1 + LEAF_SHARE * (BRAND[0] - 1))
        hi = r["pages_bottom_up"] + brand_hi + un * RATIO_HI * (1 + LEAF_SHARE * (BRAND[1] - 1)) + r["listings_without_total"]
        basis = "census pages for the listings no run reached, with the measured overheads (see method)"
    else:
        lo, hi = 6.0 * r["listings_without_total"], 18.0 * r["listings_without_total"]
        basis = "no census and no run: 6 to 18 pages per listing (the range of rows 1-15's listings)"
    out_rows.append({"csv_row": row, "category": cen.get("category", ""), "listings": r["listings"],
                     "listings_with_a_total": r["listings_with_total"], "listings_without_a_total": r["listings_without_total"],
                     "above_window": r["above_window"], "subdivision_pages": r["subdivision_pages"],
                     "leaves_above_window": r["leaves_above_window"], "leaf_plain_pages": r["leaf_plain_pages"],
                     "pages_bottom_up": r["pages_bottom_up"], "census_pages": cpages,
                     "pages_low": round(lo), "pages_high": round(hi), "basis": basis})
    lo_sum += lo; hi_sum += hi
dup_pages = sum(math.ceil(d["count"] / PER_PAGE) for d in dups if "count" in d)
extra = {"robots": 3, "coupons_page_at_most": 4, "named_product_pages": 4}
subs = {"low": round(lo_sum * SUBS_PER_PAGE + sum(extra.values())), "high": round(hi_sum * SUBS_PER_PAGE + sum(extra.values()))}
est = {
  "method": __doc__.strip().splitlines()[0],
  "inputs": {"ratio_bottom_up_to_census_pages": RATIO_HI, "leaf_share_of_products": LEAF_SHARE,
             "brand_pages_per_plain_page": BRAND, "f2_submissions": 595, "f2_completed_pages": 416, "submissions_per_completed_page": round(SUBS_PER_PAGE, 3),
             "page_size": PER_PAGE, "result_window": WINDOW, "rate_usd_per_submission": RATE,
             "envelope_usd": ENVELOPE, "extra_submissions": extra},
  "pages": {"low": round(lo_sum), "high": round(hi_sum)},
  "submissions": subs,
  "usd": {k: round(v * RATE, 2) for k, v in subs.items()},
  "hours_two_lanes_at_f2_rate": {k: round(v * 6.02 / 3600, 1) for k, v in {"low": lo_sum, "high": hi_sum}.items()},
  "avoidable_duplicates": {"items": dups, "pages_read_twice_in_a_full_run": dup_pages + 3,
                           "corrected_in_rc6": False,
                           "why_not": "reading such a listing once for two rows (or once as a row's listing and a parent's subdivision) changes how the coverage file reconciles each row with its own pages; about 1.5% of a full run"},
  "rows": out_rows,
}
est["shortfall_usd_against_the_envelope"] = {k: round(max(0.0, v - ENVELOPE), 2) for k, v in est["usd"].items()}
json.dump(est, open(OUT, "w", encoding="utf-8"), indent=1)
with open(OUTCSV, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()), lineterminator="\n")
    w.writeheader(); w.writerows(out_rows)
print(json.dumps({k: est[k] for k in ("pages", "submissions", "usd", "hours_two_lanes_at_f2_rate", "shortfall_usd_against_the_envelope")}))
print("duplicate pages in a full run:", est["avoidable_duplicates"]["pages_read_twice_in_a_full_run"])
for r in out_rows:
    print(str(r["csv_row"]).rjust(2), r["category"][:16].ljust(16), r["listings"], r["listings_with_a_total"], r["above_window"], r["pages_bottom_up"], r["census_pages"], r["pages_low"], r["pages_high"])
