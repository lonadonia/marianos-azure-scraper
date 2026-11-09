"""Tabulate the new listing tiles (horizontal-product-card-N, seen from 2026-11-06) of one saved page beside the page
state's own facts for the same product. Read only; for building the 1.9.0rc2 tile parser.

usage: tiles190.py FILE [FILE...]     FILE: an observe190 capture (*.raw.gz, the provider's JSON answer) or a saved
                                      DOM (*.html.gz)
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.search_state import search_summary, state_products


def html_of(path: Path) -> tuple[str, dict[str, Any]]:
    raw = gzip.decompress(path.read_bytes())
    if path.name.endswith(".raw.gz"):
        doc = json.loads(raw)
        res = (doc.get("results") or [{}])[0]
        return str(res.get("html") or res.get("content") or ""), dict(res.get("metadata") or {})
    return raw.decode("utf-8"), {}


def tx(n: Any) -> str:
    return re.sub(r"\s+", " ", n.text(deep=True)).strip() if n is not None else ""


def state_facts(p: dict[str, Any]) -> dict[str, Any]:
    item = p.get("item") or {}
    price = p.get("price") or {}
    inv = (p.get("inventory") or {}).get("locations") or []
    sp = price.get("storePrices") or {}
    return {
        "size": item.get("customerFacingSize"),
        "sold_by": item.get("soldBy") or (item.get("weight") or {}).get("soldBy") if isinstance(item.get("weight"), dict) else item.get("soldBy"),
        "regular": (sp.get("regular") or {}).get("price"),
        "promo": (sp.get("promo") or {}).get("price"),
        "template": (sp.get("regular") or {}).get("displayTemplate"),
        "promo_template": (sp.get("promo") or {}).get("displayTemplate"),
        "stock": [x.get("stockLevel") for x in inv],
    }


def main() -> None:
    for name in sys.argv[1:]:
        path = Path(name)
        html, meta = html_of(path)
        tree = LexborHTMLParser(html)
        tiles = tree.css('[data-testid^="horizontal-product-card-"], [data-testid^="default-product-card-"]')
        old = tree.css('[data-testid^="mini-product-card-"], [data-testid^="product-card-"]')
        try:
            state = parse_initial_state(html)
            summ = search_summary(state)
            products = {str(p.get("id")): p for p in state_products(state)}
        except Exception as exc:  # recorded, not guessed
            summ, products = None, {}
            print("  state:", type(exc).__name__, str(exc)[:120])
        print(f"== {path.name} run_js={meta.get('run_js')} tiles={len(tiles)} old_tiles={len(old)} "
              f"grid={len(tree.css('[data-testid=paginate-items]'))} state_products={len(products)} "
              f"total={getattr(summ, 'total', None)} page={getattr(summ, 'page', None)}")
        for t in tiles:
            a = t.css_first('a[href*="/p/"]')
            upc = (a.attributes.get("href") or "").rsplit("/", 1)[-1] if a else ""
            price = t.css_first('[data-testid="product-price"]')
            row = {
                "i": (t.attributes.get("data-testid") or "").rsplit("-", 1)[-1],
                "upc": upc,
                "title": tx(t.css_first('[data-testid="product-description"]'))[:48],
                "eyebrow": tx(t.css_first('[data-testid="eyebrow-text"]')),
                "cur": tx(t.css_first(".citrus-Price--current-price")),
                "orig": tx(t.css_first(".citrus-Price--original-price-value")),
                "sr": tx(t.css_first(".citrus-Price--sr-description")),
                "ppm": tx(t.css_first('[data-testid="product-price-equivalized-unit-price"]')),
                "headline": tx(t.css_first(".CardTemplate-Horizontal-headline")) if price is None else "",
                "tags": [tx(x) for x in t.css('[data-testid="description-tags-container"] li')],
                "secondary": tx(t.css_first(".CardTemplate-Horizontal-secondaryTags")),
                "savings": tx(t.css_first(".CardTemplate-Horizontal-savingsCTA")),
                "aisle": tx(t.css_first('[data-testid="aisle-location"]')),
                "pla": tx(t.css_first('[data-testid="pla-compliance-tag"]')),
                "kind": (t.attributes.get("data-testid") or "").rsplit("-product-card-", 1)[0],
                "state": state_facts(products.get(upc, {})),
            }
            print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
