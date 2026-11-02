"""Full-scope estimate from the department census (TEST_PLAN_180 Amendments 8-9). Offline: reads the census pages'
records (C:/m6/ev/census/census.jsonl), probe L15 (Breakfast, 05:15Z), the client's category CSV snapshot (menu nodes
per row) and Q2's measured rates. Writes:

    OUT/FULL_SCOPE_CENSUS.csv     one row per category of each measured department (count at 53100502 PICKUP)
    OUT/FULL_SCOPE_BY_CSV_ROW.csv one row per CSV row: categories named by its menu nodes, products, pages
    OUT/FULL_SCOPE_ESTIMATE.json  totals and the assumptions (scenario A: as implemented; B: brand partitions)

    python -I census_estimate180.py OUT_DIR
"""

import csv
import gzip
import json
import math
import sys
from pathlib import Path

CENSUS = Path(r"C:\m6\ev\census\census.jsonl")
L15 = Path(r"C:\m6\ev\probes\20261102T051523Z_L15.html.gz")
L15_JSON = Path(r"C:\m6\ev\probes\20261102T051523Z_L15.json")
SEED = Path(r"C:\m5\wt\headless\marianos-azure-headless\config\taxonomy_seed.snapshot_2026-10-17.json")
WINDOW, PAGE = 250, 24
# Q2 (1.8.0rc4, 2026-11-02) measured: 78 listing submissions for 60 listing answers that count (58 pages + 2 empty);
# its segments ran 57.7 min in all for those 60 answers (and 7 robots/Coupons submissions).
SUBMISSIONS_PER_PAGE = 78 / 60
SECONDS_PER_PAGE = 57.7 * 60 / 60
RESERVE_USD = 0.0015
RUNS_PER_MONTH = 52 * 2 / 12
# brand partitions measured on stored pages (L11 cold cereal 277: 68 vs 12 pages; L2 03001: 81 vs 17; L15: 180 vs 40)
BRAND_FACTOR = (4.5, 5.7)
FIXED_PER_RUN = 3  # robots.txt about once per segment (2) + the Coupons page (1)


def departments_of(html: str) -> list[dict]:
    i = html.find('"departments":[')
    if i < 0:
        return []
    val, _ = json.JSONDecoder().raw_decode(html, i + len('"departments":'))
    return val


def run(pages: float) -> dict:
    subs = pages * SUBMISSIONS_PER_PAGE + FIXED_PER_RUN
    return {
        "listing_pages": round(pages),
        "submissions": round(subs),
        "usd_reserve_rate": round(subs * RESERVE_USD, 2),
        "hours_serial": round(pages * SECONDS_PER_PAGE / 3600, 1),
        "usd_month_twice_weekly": round(subs * RESERVE_USD * RUNS_PER_MONTH, 2),
    }


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    measured: dict[str, dict] = {}
    for line in CENSUS.read_text("utf-8").splitlines():
        r = json.loads(line)
        if r.get("status") == 200 and r.get("total") is not None and not r.get("departments"):
            measured[r["department"]] = {
                "name": f"department {r['department']}", "slug": r["slug"], "total": r["total"],
                "available": r.get("available"), "at": r["at"], "request_id": r.get("request_id"),
                "sha256": r.get("body_sha256"), "source": f"census {r['id']} (total only: no category list)",
                "categories": {},
            }
        if r.get("status") == 200 and r.get("total") is not None and r.get("departments"):
            d = r["departments"][0]
            measured[r["department"]] = {
                "name": d["name"], "slug": d["slug"], "total": r["total"], "available": r.get("available"),
                "at": r["at"], "request_id": r.get("request_id"), "sha256": r.get("body_sha256"),
                "source": f"census {r['id']}",
                "categories": {c["id"]: (c["name"], c["count"]) for c in d["categories"]},
            }
    h = gzip.decompress(L15.read_bytes()).decode("utf-8", "replace")
    d = departments_of(h)[0]
    l15 = json.loads(L15_JSON.read_text("utf-8"))
    measured["03"] = {
        "name": d["name"], "slug": d["slug"], "total": d["count"], "available": 250, "at": l15["at"],
        "request_id": l15.get("request_id"), "sha256": l15.get("body_sha256"), "source": "probe L15",
        "categories": {c["id"]: (c["name"], c["count"]) for c in d["categories"]},
    }
    seed = json.loads(SEED.read_text("utf-8"))
    rows = [r for r in seed["rows"] if r["kind"] == "department_landing"]
    with (out / "FULL_SCOPE_CENSUS.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["department", "department_name", "department_total", "category_id", "category_name", "count",
                    "above_window", "pages_to_window", "named_by_csv_rows", "measured_at", "source",
                    "provider_request_id", "page_sha256"])
        for dep in sorted(measured):
            m = measured[dep]
            for cid, (name, n) in sorted(m["categories"].items()):
                named = sorted({str(r["row_index"]) for r in rows for nd in r["menu_nodes"]
                                if (nd.get("taxonomy_id") or "")[:5] == cid}, key=int)
                w.writerow([dep, m["name"], m["total"], cid, name, n, n > WINDOW, math.ceil(min(n, WINDOW) / PAGE),
                            ";".join(named), m["at"], m["source"], m["request_id"], m["sha256"]])
    per_row = []
    union: dict[str, int] = {}
    unmeasured_rows = []
    for r in rows:
        cats: dict[str, int] = {}
        missing: set[str] = set()
        sub_nodes = 0
        for nd in r["menu_nodes"]:
            tid = nd.get("taxonomy_id") or ""
            cid, dep = tid[:5], tid[:2]
            if len(tid) > 5:
                sub_nodes += 1
            if dep not in measured:
                missing.add(f"department {dep}")
                continue
            if not measured[dep]["categories"]:
                # only the department's total is known: the row is counted at that total once (an approximation)
                cats[f"dept{dep}"] = measured[dep]["total"]
                union[f"dept{dep}"] = measured[dep]["total"]
                missing.add(f"department {dep} categories (its total used)")
                continue
            n = measured[dep]["categories"].get(cid, (None, None))[1]
            if n is None:
                missing.add(f"category {cid}")
                continue
            cats[cid] = n
            union[cid] = n
        above = {c: n for c, n in cats.items() if n > WINDOW}
        per_row.append({
            "csv_row": r["row_index"], "category": r["category"], "menu_nodes": len(r["menu_nodes"]),
            "subcategory_nodes": sub_nodes, "categories_measured": len(cats),
            "not_measured": ";".join(sorted(missing)), "products_listed": sum(cats.values()),
            "categories_above_window": len(above), "products_above_window": sum(above.values()),
            "pages_all_products": sum(math.ceil(n / PAGE) for n in cats.values()),
        })
        if missing:
            unmeasured_rows.append(r["row_index"])
    with (out / "FULL_SCOPE_BY_CSV_ROW.csv").open("w", encoding="utf-8", newline="") as f:
        w2 = csv.DictWriter(f, fieldnames=list(per_row[0]), lineterminator="\n")
        w2.writeheader()
        w2.writerows(per_row)
    pages_union = sum(math.ceil(n / PAGE) for n in union.values())
    above_pages = sum(math.ceil(n / PAGE) for n in union.values() if n > WINDOW)
    est = {
        "store": "53100502 PICKUP", "window": WINDOW, "page_size": PAGE,
        "departments_measured": sorted(measured),
        "csv_rows_with_something_not_measured": unmeasured_rows,
        "categories_named_by_rows_measured": len(union),
        "products_listed_in_those_categories": sum(union.values()),
        "categories_above_window": sum(1 for n in union.values() if n > WINDOW),
        "products_in_categories_above_window": sum(n for n in union.values() if n > WINDOW),
        "pages_per_row_sum": sum(r["pages_all_products"] for r in per_row),
        "pages_union": pages_union,
        "pages_in_categories_above_window": above_pages,
        "scenario_A_as_implemented": run(pages_union),
        "scenario_B_brand_partitions_low": run(pages_union - above_pages + above_pages * BRAND_FACTOR[0]),
        "scenario_B_brand_partitions_high": run(pages_union - above_pages + above_pages * BRAND_FACTOR[1]),
        "assumptions": {
            "submissions_per_page": round(SUBMISSIONS_PER_PAGE, 3), "seconds_per_page": round(SECONDS_PER_PAGE, 1),
            "reserve_usd_per_submission": RESERVE_USD, "runs_per_month": round(RUNS_PER_MONTH, 2),
            "brand_factor": BRAND_FACTOR, "fixed_submissions_per_run": FIXED_PER_RUN,
            "note": ("A: every category the rows name read to its end, pages = products/24 (categories above the "
                     "window read through child listings, which must account for the total). B: categories above the "
                     "window divided by brand (not implemented), their pages multiplied by the measured factor. "
                     "A product can be in several categories; each category is a listing read in full."),
        },
    }
    (out / "FULL_SCOPE_ESTIMATE.json").write_text(json.dumps(est, indent=1), "utf-8")
    print(json.dumps(est, indent=1))
    for r in per_row:
        print(r)


if __name__ == "__main__":
    main()
