"""PRIVATE (workstation): the displayed and the embedded price per measure of named UPCs, side by side, from one run's
stored captures (the listing page's HTML and the product data the page loaded), no network.

    python -I ppm_embedded.py RUN_STORED_LIVE_DIR EXPORT_DIR OUT.txt UPC [UPC ...]

RUN_STORED_LIVE_DIR is <data>/runs/<store>/<run>/live (dom/*.html.gz and raw/*.products_v2.json.gz). For each UPC: the
record's page (from the export's provenance), the tile's displayed per-measure text (data-testid
product-price-equivalized-unit-price), and from the product data the page loaded (raw/<fetch>.*.products_v2.json.gz,
the same fetch) the product's regular and promo prices with their equivalized unit price, its customerFacingSize and
its sourceLocationId, each capture named by its SHA-256. Nothing is computed: the values are copied as the source
states them.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

live, exp, out, *upcs = sys.argv[1:]
LIVE, EXP = Path(live), Path(exp)
prov = json.loads((EXP / "provenance.json").read_text(encoding="utf-8"))["records"]
prov_by = {r["upc"]: r for r in prov} if isinstance(prov, list) else prov
products = json.loads((EXP / "products.json").read_text(encoding="utf-8"))
records = {r["upc"]: r for r in (products if isinstance(products, list) else products.get("products", []))}


class PerMeasure(HTMLParser):
    def __init__(self, upc: str) -> None:
        super().__init__(convert_charrefs=True)
        self.upc, self.depth, self.in_tile, self.grab, self.text = upc, 0, False, 0, []
        self.tile_depth = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("br", "img", "input", "meta", "link", "hr", "source", "wbr"):
            return
        self.depth += 1
        tid = a.get("data-testid") or ""
        if self.tile_depth is None and (tid.startswith("horizontal-product-card-") or tid.startswith("default-product-card-")):
            self.tile_depth, self.cur = self.depth, []
            self.found = False
        if self.tile_depth is not None and tag == "a" and (a.get("href") or "").rstrip("/").endswith(self.upc):
            self.found = True
        if self.tile_depth is not None and tid == "product-price-equivalized-unit-price":
            self.grab = self.depth

    def handle_endtag(self, tag):
        if tag in ("br", "img", "input", "meta", "link", "hr", "source", "wbr"):
            return
        if self.grab and self.depth == self.grab:
            self.grab = 0
        if self.tile_depth is not None and self.depth == self.tile_depth:
            if self.found and not self.in_tile:
                self.text, self.in_tile = list(self.cur), True
            self.tile_depth = None
        self.depth -= 1

    def handle_data(self, data):
        if self.grab and self.tile_depth is not None:
            self.cur.append(data)


def find(x, upc):
    if isinstance(x, dict):
        if any(str(v) == upc for v in x.values()) and "price" in x:
            return x
        for v in x.values():
            r = find(v, upc)
            if r is not None:
                return r
    elif isinstance(x, list):
        for v in x:
            r = find(v, upc)
            if r is not None:
                return r
    return None


L = []
for upc in upcs:
    p = prov_by.get(upc)
    rec = records.get(upc, {})
    L.append(f"=== {upc}  {rec.get('product_title', '')!r}")
    if not p:
        L.append("    not in this run's export")
        continue
    cap = p.get("capture") or {}
    fetch = cap.get("page_fetch_id")
    dom = LIVE / "dom" / f"{fetch}.html.gz"
    raw = sorted((LIVE / "raw").glob(f"{fetch}.*.products_v2.json.gz"))
    L.append(f"    page      {cap.get('url')}  fetched {cap.get('fetched_at')}  fetch {fetch}")
    L.append(f"    provenance dom_sha256 {cap.get('dom_sha256')} (the stored .html.gz as kept)")
    if dom.exists():
        b = dom.read_bytes()
        html = gzip.decompress(b).decode("utf-8", errors="replace")
        pm = PerMeasure(upc)
        pm.feed(html)
        L.append(f"    html      stored file sha256 {hashlib.sha256(b).hexdigest()}"
                 f" ({'MATCHES' if hashlib.sha256(b).hexdigest() == cap.get('dom_sha256') else 'DIFFERS FROM'} the provenance)")
        L.append(f"    displayed per-measure element: {''.join(pm.text).strip()!r}")
    L.append(f"    exported  ppm {rec.get('ppm')!r}  regular_price {rec.get('regular_price')!r}  sale_price "
             f"{rec.get('sale_price')!r}  weight {rec.get('weight')!r}")
    for r in raw:
        b = gzip.decompress(r.read_bytes())
        prod = find(json.loads(b), upc)
        L.append(f"    product data {r.name}: sha256 {hashlib.sha256(b).hexdigest()} (uncompressed)")
        if prod is None:
            L.append("      the product is not in it")
            continue
        txt = json.dumps(prod)
        size = re.search(r'"customerFacingSize": "([^"]*)"', txt)
        loc = re.search(r'"sourceLocationId": "([^"]*)"', txt)
        L.append(f"      customerFacingSize {size.group(1) if size else '-'!r}; sourceLocationId {loc.group(1) if loc else '-'}")
        sp = (prod.get("price") or {}).get("storePrices") or {}
        for kind in ("regular", "promo"):
            v = sp.get(kind)
            if v:
                L.append(f"      {kind}: {v.get('defaultDescription')!r}, equivalized "
                         f"{json.dumps(v.get('equivalizedUnitPrice'))}, string {v.get('equivalizedUnitPriceString')!r}, "
                         f"expires {(v.get('expirationDate') or {}).get('value')}")
    L.append(f"    flags     {rec.get('flags') or p.get('flags') or ''}")
Path(out).write_bytes(("\n".join(L) + "\n").encode("utf-8"))
print("\n".join(L))
