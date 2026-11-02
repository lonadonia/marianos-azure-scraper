"""Offline census of size evidence in the saved pages of R1 (2026-10-29, 53100503 In Store, development evidence)."""
from __future__ import annotations

import collections
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless\src")
from marianos_headless.sites.marianos.initial_state import parse_initial_state  # noqa: E402
from marianos_headless.sites.marianos.search_state import state_products  # noqa: E402

rid = "01M650QGTRZCPNYSYWFTWGX2SB"
base = Path(rf"C:\m5\p170\{rid}\data\{rid}\live\dom")
prods: dict[str, dict] = {}
for f in sorted(base.glob("*.html.gz")):
    html = gzip.decompress(f.read_bytes()).decode("utf-8", "replace")
    try:
        st = parse_initial_state(html)
    except Exception:  # noqa: BLE001
        continue
    for p in state_products(st):
        u = str(p.get("upc") or p.get("id"))
        prods.setdefault(u, p)
print("products", len(prods))
units = collections.Counter()
slots = collections.Counter()
rows = []
for u, p in prods.items():
    it = p.get("item") or {}
    cfs = (it.get("customerFacingSize") or "").strip()
    q, un = it.get("pidSizeQuantity"), it.get("pidSizeUnitOfMeasureName")
    units[str(un)] += 1
    w = re.sub(r"[\d./]+", "#", cfs.lower())
    slots[w] += 1
    pr = p.get("price") or {}
    reg = ((pr.get("storePrices") or {}).get("regular") or {})
    eq = reg.get("equivalizedUnitPrice") or {}
    rows.append({"upc": u, "cfs": cfs, "q": q, "un": un, "weight": it.get("weight"), "title": it.get("description"), "sell": pr.get("sellBy"), "order": pr.get("orderBy"), "price": str(reg.get("price") or "").replace("USD ", ""), "amount": eq.get("amount"), "per": eq.get("unit"), "den": eq.get("denomination")})
print("pid units", units.most_common(40))
print("slot shapes", slots.most_common(80))
Path(r"C:\m6\ev\repro").mkdir(parents=True, exist_ok=True)
Path(r"C:\m6\ev\repro\size_census_rows.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
