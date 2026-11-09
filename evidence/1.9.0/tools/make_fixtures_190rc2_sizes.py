"""Add the release 1.9.0rc2 size fixtures to tests/fixtures/oxylabs_2026-11-06: the grid cards and page-state
data of the two products whose weight run Q2 exported as a text stating no quantity ("N/A": 0002310032784;
"Count": 0019283330664), as Q2 (01M6E5V6CASQ8F00VC8PE9TFYW) saved them. Each card's outer HTML is unchanged.
Method of make_fixtures_190_m6.py.

usage: make_fixtures_190rc2_sizes.py OUT_DIR
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

from marianos_headless.collection.live import CARD_CSS, GRID_CSS, grid_cards

OUT = Path(sys.argv[1])
Q2 = Path("C:/m6/q180/data")
RUN = "01M6E5V6CASQ8F00VC8PE9TFYW"
RUNDIR = Q2 / "runs" / "marianos-53100502-pickup" / RUN
UPCS = ["0002310032784", "0019283330664"]

prov = json.loads((RUNDIR / "exports" / "provenance.json").read_text(encoding="utf-8"))["records"]
cards_html: list[str] = []
sources: dict[str, dict] = {}
products: dict[str, dict] = {}
for upc in UPCS:
    cap = prov[upc]["capture"]
    raw = (Q2 / cap["dom_key"]).read_bytes()
    tree = LexborHTMLParser(gzip.decompress(raw).decode("utf-8"))
    found = None
    for n in tree.css_first(GRID_CSS).css(CARD_CSS):
        if upc in (n.html or ""):
            _, parsed, _, _ = grid_cards(f'<div data-testid="paginate-items">{n.html}</div>')
            if parsed and parsed[0].upc == upc:
                found = n.html
                break
    assert found, upc
    cards_html.append(found)
    sources[upc] = {
        "page_fetch_id": cap["page_fetch_id"],
        "url": cap["url"],
        "fetched_at": cap["fetched_at"],
        "dom_key": cap["dom_key"],
        "dom_gz_sha256": hashlib.sha256(raw).hexdigest(),
    }
    fetch_id = ((prov[upc].get("source_check") or {}).get("response") or {}).get("fetch_id") or cap["page_fetch_id"]
    for f in sorted((RUNDIR / "live" / "raw").glob(f"{fetch_id}.*.products_v2.json.gz")):
        for p in json.loads(gzip.decompress(f.read_bytes()))["data"]["products"]:
            if ((p.get("item") or {}).get("upc") or p.get("id")) == upc:
                products[upc] = p
                sources[upc]["state_artifact"] = f.name
                sources[upc]["state_artifact_gz_sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()
    assert upc in products, upc

page = (
    "<!doctype html><html><body>\n"
    "<!-- Grid cards saved by run Q2 (01M6E5V6CASQ8F00VC8PE9TFYW, 2026-11-02, store 53100502 PICKUP); each card's\n"
    "     outer HTML is unchanged; only the rest of each page is left out. Sources: SOURCES_RC2_SIZES.json. -->\n"
    '<div data-testid="paginate-items">\n' + "\n".join(cards_html) + "\n</div></body></html>\n"
)
(OUT / "q2_cards_rc2_no_quantity.html").write_text(page, encoding="utf-8", newline="\n")
(OUT / "q2_state_products_rc2_no_quantity.json").write_text(
    json.dumps({"data": {"products": [products[u] for u in UPCS]}}, ensure_ascii=False, indent=1) + "\n",
    encoding="utf-8",
    newline="\n",
)
(OUT / "SOURCES_RC2_SIZES.json").write_text(json.dumps(sources, indent=1) + "\n", encoding="utf-8", newline="\n")
for upc in UPCS:
    item = products[upc].get("item") or {}
    print(upc, repr(item.get("customerFacingSize")), sources[upc]["url"])
