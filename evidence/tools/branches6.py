"""Listings above the site's window and their subdivisions, checked page by page and reconciled as a union.

    python -I branches6.py EVIDENCE_DIR OUT_CSV OUT_PAGES_CSV

EVIDENCE_DIR is a stage's evidence folder (db_listing_pages.csv and export/coverage_reconciliation.csv).

For each listing whose reported total is above the window the source lets a reader reach (source_window), and each
of its subdivisions (child listings the page names, or the retailer's brand filter values), every page answer the
run counted is checked for:
  store        location 53100502, fulfillment PICKUP, the collector's store check PASS
  page         the page answered is the page asked, of the listing asked (returned taxonomy == asked)
  filter       the filter asked is the filter the page states as requested (brand partitions: brandName)
The union of the distinct products that the parent and all its subdivisions hold in the run's memberships (organic and
sponsored placements of the listing, as the collector counts them: it must equal the collector's own
unique_identities; the organic part is shown apart) is compared with the parent's reported total. Nothing is inferred: a subdivision not read stays NOT_COLLECTED, a parent whose union
does not reach its total stays a gap, with its size.
"""

from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

STORE, FULFILLMENT = "53100502", "PICKUP"
csv.field_size_limit(10**9)


def main() -> int:
    ev, out, out_pages = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    cov = list(csv.DictReader((ev / "export" / "coverage_reconciliation.csv").open(encoding="utf-8", newline="")))
    pages = list(csv.DictReader((ev / "db_listing_pages.csv").open(encoding="utf-8", newline="")))
    members: dict[tuple[str, str], dict[str, set[str]]] = collections.defaultdict(lambda: {"organic": set(), "all": set()})
    for m in json.loads((ev / "export" / "memberships.json").read_bytes().decode("utf-8")):
        k = (str(m["csv_row"]), str(m["listing"]))
        members[k]["all"].add(m["key"])
        if m["via"] == "organic":
            members[k]["organic"].add(m["key"])
    counted = [p for p in pages if p["verdict"] in ("new", "completed") and p["state"] == "completed"]
    by_listing: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for p in counted:
        by_listing[(p["csv_row_index"], p["taxonomy_id"] if not p["partition_key"] else p["partition_key"])].append(p)
    kids: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in cov:
        if r["parent_listing"]:
            kids[(r["csv_row"], r["parent_listing"])].append(r)
    page_rows, out_rows = [], []

    def check(p: dict) -> dict:
        b = json.loads(p["binding"] or "{}")
        req = json.loads(p["requested_filter"] or "{}")
        store_ok = p["location_id"] == STORE and p["modality"] == FULFILLMENT and p["store_check"] == "PASS"
        page_ok = (p["returned_taxonomy_id"] in ("", p["taxonomy_id"])
                   and (p["returned_page"] in ("", p["requested_page"])))
        filter_ok = (b.get("requested") or {}) == req
        row = {"csv_row": p["csv_row_index"], "parent": p["parent_taxonomy_id"], "listing": p["taxonomy_id"],
               "partition": p["partition_key"], "requested_filter": json.dumps(req, ensure_ascii=False),
               "stated_filter": json.dumps(b.get("requested") or {}, ensure_ascii=False),
               "page": p["requested_page"], "returned_page": p["returned_page"],
               "returned_listing": p["returned_taxonomy_id"], "location": p["location_id"],
               "fulfillment": p["modality"], "store_check": p["store_check"], "total": p["total"],
               "available": p["available"], "verdict": p["verdict"], "page_fetch_id": p["page_fetch_id"],
               "response_sha256": p["response_sha256"],
               "store_ok": store_ok, "page_ok": page_ok, "filter_ok": filter_ok}
        page_rows.append(row)
        return row

    for r in cov:
        if r["parent_listing"] or not r["reported_total"] or not r["source_window"]:
            continue
        if int(r["reported_total"]) <= int(r["source_window"]):
            continue
        key = (r["csv_row"], r["listing_id"])
        subs = kids.get(key, [])
        union: set[str] = set()
        union_all: set[str] = set(members[key]["all"])
        organic: set[str] = set(members[key]["organic"])
        checks = []
        for p in by_listing.get(key, []):
            checks.append(check(p))
            union.update(json.loads(p["identities"] or "[]"))
        sub_status = collections.Counter()
        for s in subs:
            sub_status[s["status"]] += 1
            union_all |= members[(s["csv_row"], s["listing_id"])]["all"]
            organic |= members[(s["csv_row"], s["listing_id"])]["organic"]
            skey = (s["csv_row"], s["partition_identity"] or s["listing_id"])
            for p in by_listing.get(skey, []) + [x for x in by_listing.get((s["csv_row"], s["listing_id"]), [])
                                                 if x["parent_taxonomy_id"] == r["listing_id"] and skey[1] != s["listing_id"]]:
                checks.append(check(p))
                union.update(json.loads(p["identities"] or "[]"))
        total = int(r["reported_total"])
        kinds = collections.Counter("brand" if s["partition_identity"] else "child listing" for s in subs)
        out_rows.append({
            "csv_row": r["csv_row"], "listing": r["listing_id"], "category": r["category"],
            "sub_category": r["sub_category"], "reported_total": total, "window": r["source_window"],
            "subdivisions": len(subs), "subdivision_kinds": "; ".join(f"{k} {n}" for k, n in sorted(kinds.items())),
            "subdivisions_by_status": "; ".join(f"{k} {n}" for k, n in sorted(sub_status.items())),
            "pages_checked": len(checks),
            "pages_store_ok": sum(c["store_ok"] for c in checks),
            "pages_page_ok": sum(c["page_ok"] for c in checks),
            "pages_filter_ok": sum(c["filter_ok"] for c in checks),
            "organic_distinct_products": len(organic), "with_sponsored_distinct_products": len(union_all),
            "page_identities_distinct": len(union), "gap": max(total - len(union_all), 0),
            "collector_status": r["status"], "collector_unique_identities": r["unique_identities"],
            "union_matches_collector": str(len(union_all) == int(r["unique_identities"] or 0)).lower(),
            "reconciled": str(len(union_all) >= total and r["status"] == "DONE").lower(),
            "completion_reason": r["completion_reason"][:400]})
    for path, rows in ((out, out_rows), (out_pages, page_rows)):
        with path.open("w", newline="", encoding="utf-8") as fh:
            if rows:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
    s = {"listings_above_the_window": len(out_rows),
         "reconciled": sum(r["reconciled"] == "true" for r in out_rows),
         "by_collector_status": dict(collections.Counter(r["collector_status"] for r in out_rows)),
         "subdivisions": sum(r["subdivisions"] for r in out_rows),
         "pages_checked": len(page_rows),
         "pages_failing_a_check": sum(not (c["store_ok"] and c["page_ok"] and c["filter_ok"]) for c in page_rows),
         "union_disagrees_with_collector": [r["listing"] for r in out_rows if r["union_matches_collector"] != "true"],
         "gap_products": sum(r["gap"] for r in out_rows)}
    print(json.dumps(s, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
