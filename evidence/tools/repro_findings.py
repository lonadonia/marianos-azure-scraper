"""Reproduce the client's findings from the saved 1.7.0rc2 evidence. Offline. Writes C:/m6/ev/repro/*.json."""
from __future__ import annotations

import csv
import glob
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless\src")
from marianos_headless.sites.marianos.initial_state import parse_initial_state  # noqa: E402
from marianos_headless.sites.marianos.search_state import state_products  # noqa: E402
from marianos_headless.collection.live import grid_cards  # noqa: E402
from marianos_headless.sites.marianos.serialize import card_to_dict  # noqa: E402

csv.field_size_limit(10**9)
DL = Path(r"<projects>\marianos\20261030_marianos_1.7.0rc2\20261030_marianos_1.7.0rc2")
RUNS = {"R1": "01M650QGTRZCPNYSYWFTWGX2SB", "R2": "01M653ZMXCS1WYBXYJWETEVXTA"}
UPCS = {"0081675102373": "Buy 1 Save $1", "0086001079386": "Buy 1 Save $2", "0073679800140": "size conflict"}
OUT = Path(r"C:\m6\ev\repro")
OUT.mkdir(parents=True, exist_ok=True)

fresh = json.loads((DL / "products_fresh.json").read_text("utf-8"))
print("fresh type", type(fresh).__name__, len(fresh))
rows = fresh if isinstance(fresh, list) else fresh.get("records") or fresh.get("products")
for u in UPCS:
    hit = [r for r in rows if r.get("upc") == u]
    print(u, UPCS[u], "in products_fresh:", len(hit))
    for r in hit:
        print("  ", json.dumps({k: r[k] for k in ("product_title", "weight", "regular_price", "sale_price", "volume_deals_description", "volume_deals_price", "digital_deals_description", "ppm", "category", "sub_category", "crawl_date")}, ensure_ascii=False))

result = {}
for name, rid in RUNS.items():
    base = Path(rf"C:\m5\p170\{rid}\data\{rid}\live\dom")
    for f in sorted(base.glob("*.html.gz")):
        html = gzip.decompress(f.read_bytes()).decode("utf-8", "replace")
        if not any(u in html for u in UPCS):
            continue
        st = parse_initial_state(html)
        prods = {str(p.get("upc") or p.get("id")): p for p in state_products(st)}
        grid, cards, _, _ = grid_cards(html)
        for c in cards:
            if c.upc in UPCS:
                p = prods.get(c.upc) or {}
                item = p.get("item") or {}
                entry = {"run": name, "file": f.name, "card": card_to_dict(c)}
                entry["state"] = {
                    "description": item.get("description"), "customerFacingSize": item.get("customerFacingSize"),
                    "pidSizeQuantity": {k: v for k, v in item.items() if "ize" in k or "Quantity" in k or "weight" in k.lower() or "measure" in k.lower()},
                    "item_keys": sorted(item)[:80],
                    "price": p.get("price"),
                }
                result.setdefault(c.upc, []).append(entry)
for u, ev in result.items():
    print("=" * 10, u, len(ev), "cards in saved pages")
    e = ev[0]
    print(json.dumps({k: v for k, v in e["card"].items() if k in ("title", "size_text", "ppm_text", "zone", "price", "url")}, ensure_ascii=False, default=str)[:900])
    print(json.dumps(e["state"]["pidSizeQuantity"], ensure_ascii=False)[:800])
    print("customerFacingSize", e["state"]["customerFacingSize"], "| keys", e["state"]["item_keys"])
    print("price", json.dumps(e["state"]["price"], ensure_ascii=False)[:900])
    (OUT / f"finding_{u}.json").write_text(json.dumps(ev, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
