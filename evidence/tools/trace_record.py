"""Trace exported records to the stored listing page they were read from (no network; run with the release's Python,
which has selectolax).

    python -I trace_record.py EXPORT_DIR STORE_ROOT UPC [UPC ...]

EXPORT_DIR holds the run's products.json and provenance.json; STORE_ROOT is the data folder the provenance's
``dom_key`` is relative to. For each UPC: the exported record's fields, the page it was read from (URL, time,
fetch id, stored page and its SHA-256, checked), and what that stored page itself shows in the product's tile, read
here independently of the collector's parser (the tile whose product link ends with the UPC: its description, its
price element's text, its price-per-measure element's text). Exit 1 when a stored page's hash does not match.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

TILE = '[data-testid^="horizontal-product-card-"], [data-testid^="default-product-card-"]'


def text(node: object) -> str:
    return " ".join(node.text(deep=True).split()) if node is not None else ""  # type: ignore[attr-defined]


def main() -> int:
    exp, root = Path(sys.argv[1]), Path(sys.argv[2])
    products = json.loads((exp / "products.json").read_text(encoding="utf-8"))
    records = products if isinstance(products, list) else products.get("products", [])
    by_upc = {r["upc"]: r for r in records}
    prov = json.loads((exp / "provenance.json").read_text(encoding="utf-8"))["records"]
    bad = 0
    for upc in sys.argv[3:]:
        print(f"=== UPC {upc}")
        rec = by_upc.get(upc)
        if rec is None:
            print("    not in this export")
            continue
        for k in ("product_title", "weight", "regular_price", "sale_price", "ppm", "category", "sub_category",
                  "url", "crawl_date"):
            print(f"    export   {k:<14} {rec.get(k, '')!r}")
        p = prov.get(upc) or {}
        cap, obs = p.get("capture") or {}, p.get("observation") or {}
        print(f"    page     {cap.get('url')}  fetched {cap.get('fetched_at')}  fetch {cap.get('page_fetch_id')}")
        print(f"    tile     position {obs.get('position')} of listing {obs.get('node')}; status {p.get('status')};"
              f" flags {','.join(p.get('flags') or []) or '-'}")
        key = cap.get("dom_key")
        if not key:
            print("    no stored page named")
            continue
        path = root / key
        raw = path.read_bytes()
        html = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
        want = cap.get("dom_sha256")
        got_gz, got_html = hashlib.sha256(raw).hexdigest(), hashlib.sha256(html).hexdigest()
        ok = want in (got_gz, got_html)
        bad += 0 if ok else 1
        print(f"    stored   {key}  sha256 {'MATCHES' if ok else 'DIFFERS'} ({want})")
        tree = LexborHTMLParser(html.decode("utf-8", "replace"))
        hit = None
        for tile in tree.css(TILE):
            for a in tile.css('a[href*="/p/"]'):
                if (a.attributes.get("href") or "").rstrip("/").split("?")[0].endswith("/" + upc):
                    hit = tile
                    break
            if hit is not None:
                break
        if hit is None:
            print("    source   no tile of the stored page links to this UPC")
            continue
        print(f"    source   description    {text(hit.css_first('[data-testid=\"product-description\"]'))!r}")
        print(f"    source   price element  {text(hit.css_first('[data-testid=\"product-price\"]'))!r}")
        print(f"    source   per measure    "
              f"{text(hit.css_first('[data-testid=\"product-price-equivalized-unit-price\"]'))!r}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
