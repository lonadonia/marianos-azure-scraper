"""Price conflicts from the actual files: every one of the 120 fresh R1 conflicts re-read from its own stored page,
and the Honey Smacks trace from its saved capture, stage by stage through the current collector code.

usage: conflict_trace.py OUT_DIR. Offline; no request."""
import csv
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless\src")
from marianos_headless.collection.live import grid_cards  # noqa: E402
from marianos_headless.sites.marianos.initial_state import parse_initial_state  # noqa: E402
from marianos_headless.sites.marianos.search_state import price_location, state_products  # noqa: E402

csv.field_size_limit(10**9)
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
D = Path(r"<projects>\marianos\20261030_marianos_1.7.0rc2\20261030_marianos_1.7.0rc2")
RUN = "01M650QGTRZCPNYSYWFTWGX2SB"
DOM = Path(rf"C:\m5\p170\{RUN}\data\{RUN}\live\dom")

rows = list(csv.DictReader(open(D / "PRICE_CONFLICTS.csv", encoding="utf-8", newline="")))
fresh = {r["upc"]: r for r in json.loads((D / "products_fresh.json").read_text(encoding="utf-8"))}
retained = {r["upc"]: r for r in json.loads((D / "products_retained.json").read_text(encoding="utf-8"))}
print("rows", len(rows), "unique", len({(r["upc"], r["field"]) for r in rows}), "fresh", len(fresh), "retained", len(retained))
cached: dict[str, tuple] = {}
out = []
for r in rows:
    fetch = r["page_fetch_id"]
    if fetch not in cached:
        path = DOM / f"{fetch}.html.gz"
        if not path.exists():
            cached[fetch] = (None, {}, {}, None)
        else:
            stored = path.read_bytes()
            html = gzip.decompress(stored).decode("utf-8")
            cards = {c.upc: c for c in grid_cards(html)[1]}
            prods = {str(p.get("upc") or p.get("id")): p for p in state_products(parse_initial_state(html))}
            cached[fetch] = (hashlib.sha256(stored).hexdigest(), cards, prods, html)
    sha, cards, prods, _ = cached[fetch]
    card = cards.get(r["upc"])
    prod = prods.get(r["upc"]) or {}
    store_prices = (prod.get("price") or {}).get("storePrices") or {}
    regular = (store_prices.get("regular") or {}).get("price") or ""
    promo = (store_prices.get("promo") or {}).get("price") or ""
    stated = regular.replace("USD ", "").strip()
    shown = getattr(getattr(card, "price", None), "original_text", "") if card else ""
    rec = retained.get(r["upc"])
    pred = ""
    if stated:
        pred = str(Decimal(math.floor(float(Decimal(stated)) * 100)) / 100)
    out.append(
        {
            "upc": r["upc"],
            "product_title": r["product_title"],
            "field": r["field"],
            "observed_at": r["observed_at"],
            "page_fetch_id": fetch,
            "store": r["store"],
            "fulfillment": r["fulfillment"],
            "page_sha256_recomputed": sha or "PAGE NOT FOUND",
            "page_sha256_matches_report": sha == r["page_dom_sha256"],
            "card_original_text_in_page": shown,
            "state_regular_in_page": regular,
            "state_promo_in_page": promo,
            "state_price_location": price_location(prod) if prod else "",
            "displayed_value_reported": r["displayed_value"],
            "structured_value_reported": r["product_data_value"],
            "difference": str(Decimal(stated) - Decimal(r["displayed_value"])) if stated else "",
            "floor_x100_of_structured": pred,
            "pattern_holds": pred == r["displayed_value"].rstrip("0").rstrip(".") or (pred and Decimal(pred) == Decimal(r["displayed_value"])),
            "in_products_fresh_valid": r["upc"] in fresh,
            "in_products_retained": rec is not None,
            "exported_value": (rec or {}).get(r["field"], ""),
            "exported_equals_displayed": bool(rec) and Decimal(rec[r["field"]]) == Decimal(r["displayed_value"]),
        }
    )
fields = list(out[0])
with open(OUT / "PRICE_CONFLICT_RECONCILIATION.csv", "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\r\n")
    w.writeheader()
    w.writerows(out)
summary = {
    "source_file": "PRICE_CONFLICTS.csv of 20261030_marianos_1.7.0rc2",
    "run": RUN,
    "conflicts": len(out),
    "unique_upc_field": len({(x["upc"], x["field"]) for x in out}),
    "fields": Counter(x["field"] for x in out),
    "pages_read": len(cached),
    "page_hash_matches": sum(1 for x in out if x["page_sha256_matches_report"]),
    "pages_missing": sum(1 for x in out if x["page_sha256_recomputed"] == "PAGE NOT FOUND"),
    "structured_in_page_equals_report": sum(
        1 for x in out if x["state_regular_in_page"] and Decimal(x["state_regular_in_page"].replace("USD ", "")) == Decimal(x["structured_value_reported"])
    ),
    "counted_as_valid": sum(1 for x in out if x["in_products_fresh_valid"]),
    "in_products_retained": sum(1 for x in out if x["in_products_retained"]),
    "exported_equals_displayed": sum(1 for x in out if x["exported_equals_displayed"]),
    "differences": Counter(x["difference"] for x in out),
    "floor_pattern_holds": sum(1 for x in out if x["pattern_holds"]),
    "stores": Counter(f'{x["store"]} {x["fulfillment"]}' for x in out),
    "price_locations": Counter(x["state_price_location"] for x in out),
}
print(json.dumps(summary, indent=1, default=dict))
(OUT / "PRICE_CONFLICT_RECONCILIATION.json").write_text(json.dumps(summary, indent=1, default=dict), encoding="utf-8")
