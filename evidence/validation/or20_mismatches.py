"""OR-20: every record of a run whose stored product data differs from its exported value, investigated one by one.

    python -I or20_mismatches.py EXPORT_DIR VALIDATE_JSON OUT_CSV [STORED_DOM_DIR]

EXPORT_DIR      the run's export folder (provenance.json or provenance.json.gz, products.json)
VALIDATE_JSON   the output of `marianos-collector validate-export --run RUN` (one JSON line)
OUT_CSV         one row per record whose source check found a difference
STORED_DOM_DIR  optional: the run's stored pages (live/dom/*.html.gz, private); when given, each row also carries
                the price text of the product's own card as the stored page displays it

A difference is either recorded by the collector before export (the record's status and flag say so; the record is
not counted as a valid record) or not recorded (a silent mismatch). validate-export reports the two apart
(source_check.summary: recorded_conflict, recorded_store_not_stated, mismatch). This script lists every record behind
those counts, checks that each one is recorded and excluded from the valid records, and checks that its counts are
validate-export's counts. Exit 0 when they all agree, 1 otherwise. Reads only; writes OUT_CSV.
"""

from __future__ import annotations

import collections
import csv
import gzip
import html
import json
import re
import sys
from decimal import Decimal
from pathlib import Path


def load_json(p: Path):
    if p.exists():
        return json.loads(p.read_bytes().decode("utf-8"))
    gz = p.with_name(p.name + ".gz")
    return json.loads(gzip.decompress(gz.read_bytes()).decode("utf-8"))


def card_price_text(dom_dir: Path | None, fetch_id: str, upc: str, cache: dict) -> str:
    if dom_dir is None:
        return ""
    if fetch_id not in cache:
        f = dom_dir / f"{fetch_id}.html.gz"
        cache.clear()  # one page in memory at a time
        cache[fetch_id] = gzip.decompress(f.read_bytes()).decode("utf-8", "replace") if f.exists() else ""
    h = cache[fetch_id]
    i = h.find(f"/{upc}")
    if i < 0:
        i = h.find(upc)
    if i < 0:
        return "(product not found on the stored page)"
    k = h.find('data-testid="product-price"', i)
    if k < 0:
        return "(no price element after the product's link)"
    end = h.find('data-testid="product-price-equivalized-unit-price"', k)
    seg = h[k:end if 0 < end - k < 4000 else k + 1500]
    body = seg.split(">", 1)[1] if ">" in seg else seg
    body = re.sub(r"<[^>]*$", "", body)  # a tag cut by the segment's end
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
    return html.unescape(txt)[:160]


def cents(a: str, b: str) -> str:
    try:
        return str(int((Decimal(a) - Decimal(b)) * 100))
    except Exception:
        return ""


def main() -> int:
    exp, vj, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    dom = Path(sys.argv[4]) if len(sys.argv) > 4 else None
    prov = load_json(exp / "provenance.json")["records"]
    exported = {r["upc"]: r for r in load_json(exp / "products.json")}
    vline = [ln for ln in vj.read_bytes().decode("utf-8").splitlines() if ln.strip()][-1]
    v = json.loads(vline)["result"]["source_check"]
    rows, cache = [], {}
    for upc, r in sorted(prov.items()):
        fl = r.get("flags") or []
        kinds = [k for k in ("PRICE_DOM_JSON_MISMATCH", "PRICE_STORE_NOT_STATED") if k in fl]
        if not kinds:
            continue
        sc = r.get("source_check") or {}
        e = exported.get(upc, {})
        cap = r["capture"]
        field = "regular_price" if kinds[0] == "PRICE_DOM_JSON_MISMATCH" else "store"
        if field == "regular_price":
            finding = ("the card displays a regular price that differs from the product data's regular price for "
                       "the same store; the export keeps the displayed value and marks the record price_conflict")
        else:
            finding = ("the product data states no price location and no fulfillment for the store (stock: "
                       f"{sc.get('stock_level') or 'not stated'}); the export keeps the card's values and marks "
                       "the record exported_not_valid")
        rows.append({
            "upc": upc, "status": r["status"], "flag": kinds[0], "field": field,
            "exported_regular_price": e.get("regular_price", ""), "product_data_regular_price": sc.get("regular_price", ""),
            "difference_cents": cents(e.get("regular_price", ""), sc.get("regular_price", "")) if field == "regular_price" else "",
            "exported_sale_price": e.get("sale_price", ""), "product_data_promo_price": sc.get("promo_price", ""),
            "product_data_price_location": sc.get("price_location") or "", "product_data_stock": sc.get("stock_level") or "",
            "product_data_fulfillment": " ".join(sc.get("fulfillment") or []),
            "card_price_text": card_price_text(dom, cap["page_fetch_id"], upc, cache),
            "valid_record": "yes" if r["status"] == "valid" else "no",
            "page_url": cap["url"], "page_fetch_id": cap["page_fetch_id"], "page_sha256": cap["dom_sha256"],
            "product_data_sha256": (sc.get("response") or {}).get("sha256", ""), "finding": finding})
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    by = collections.Counter((x["field"], x["status"]) for x in rows)
    diffs = collections.Counter(x["difference_cents"] for x in rows if x["field"] == "regular_price")
    sale_agree = sum(1 for x in rows if x["field"] == "regular_price"
                     and x["exported_sale_price"] == x["product_data_promo_price"])
    card_agrees = sum(1 for x in rows if x["field"] == "regular_price" and x["card_price_text"]
                      and f"${x['exported_regular_price']}" in x["card_price_text"])
    summary = v["summary"]
    checks = {
        "every listed record is excluded from the valid records": all(x["valid_record"] == "no" for x in rows),
        "regular_price rows == validate-export recorded_conflict": by[("regular_price", "price_conflict")] == summary["recorded_conflict"] == sum(n for (f, _), n in by.items() if f == "regular_price"),
        "store rows == validate-export recorded_store_not_stated": sum(n for (f, _), n in by.items() if f == "store") == summary["recorded_store_not_stated"],
        "validate-export silent mismatches == 0": summary["mismatch"] == 0,
        "mismatched_fields agree": v.get("mismatched_fields") == {"store": sum(n for (f, _), n in by.items() if f == "store"), "regular_price": sum(n for (f, _), n in by.items() if f == "regular_price")},
    }
    print(json.dumps({"rows": len(rows), "by_field_and_status": {f"{a}/{b}": n for (a, b), n in sorted(by.items())},
                      "regular_price_difference_cents": dict(sorted(diffs.items(), key=lambda kv: int(kv[0] or 0))),
                      "regular_price_rows_whose_sale_price_agrees": sale_agree,
                      "regular_price_rows_whose_card_shows_the_exported_value": card_agrees if dom else "not read",
                      "validate_export_summary": summary, "checks": checks}, indent=1))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
