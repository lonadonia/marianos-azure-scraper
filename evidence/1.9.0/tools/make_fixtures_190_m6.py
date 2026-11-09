"""Add the M6 fixtures to tests/fixtures/oxylabs_2026-11-06 (release 1.9.0): real saved data, trimmed only.

- q2_cards_m6_sizes.html / q2_state_products_m6_sizes.json: the grid cards and page-state data of the three
  sizes Q2 (01M6E5V6CASQ8F00VC8PE9TFYW) left unresolved, as Q2 saved them.
- o1_state_products_m6.json: the product data of the seven M6 product pages stage O1 saved on 2026-11-06
  (the page state each product page carries; read with the collector's own state parser).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

from marianos_headless.collection.live import CARD_CSS, GRID_CSS, grid_cards
from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.search_state import state_products

OUT = Path(sys.argv[1])
Q2 = Path("C:/m6/q180/data")
RUN = "01M6E5V6CASQ8F00VC8PE9TFYW"
RUNDIR = Q2 / "runs" / "marianos-53100502-pickup" / RUN
O1 = Path("C:/m8/evidence/live190/o1/captures")
SIZES = ["0001780010048", "0065922318120", "0087786900820"]
O1_PAGES = {
    "0081675102373": "07_m6a_pdp_0081675102373",
    "0086001079386": "08_m6b_pdp_0086001079386",
    "0001820020352": "09_m6c_pdp_0001820020352",
    "0073679800140": "10_m6d_pdp_0073679800140",
    "0001780010048": "11_s1_pdp_0001780010048",
    "0065922318120": "12_s2_pdp_0065922318120",
    "0087786900820": "13_s3_pdp_0087786900820",
}

prov = json.loads((RUNDIR / "exports" / "provenance.json").read_text(encoding="utf-8"))["records"]
cards_html: list[str] = []
q2_sources: dict[str, dict] = {}
q2_products: dict[str, dict] = {}
for upc in SIZES:
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
    q2_sources[upc] = {
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
                q2_products[upc] = p
                q2_sources[upc]["state_artifact"] = f.name
                q2_sources[upc]["state_artifact_gz_sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()
    assert upc in q2_products, upc

page = (
    "<!doctype html><html><body>\n"
    "<!-- Grid cards saved by run Q2 (01M6E5V6CASQ8F00VC8PE9TFYW, 2026-11-02, store 53100502 PICKUP); each card's\n"
    "     outer HTML is unchanged; only the rest of each page is left out. Sources: SOURCES_M6.json. -->\n"
    '<div data-testid="paginate-items">\n' + "\n".join(cards_html) + "\n</div></body></html>\n"
)
(OUT / "q2_cards_m6_sizes.html").write_text(page, encoding="utf-8", newline="\n")
(OUT / "q2_state_products_m6_sizes.json").write_text(
    json.dumps({"data": {"products": [q2_products[u] for u in SIZES]}}, ensure_ascii=False, indent=1) + "\n",
    encoding="utf-8",
    newline="\n",
)

o1_products: list[dict] = []
o1_sources: dict[str, dict] = {}
for upc, cap in O1_PAGES.items():
    raw = (O1 / f"{cap}.raw.gz").read_bytes()
    env = json.loads(gzip.decompress(raw))
    rec = json.loads((O1 / f"{cap}.json").read_text(encoding="utf-8"))
    r0 = env["results"][0]
    products = [p for p in state_products(parse_initial_state(r0["html"])) if p.get("id") == upc]
    assert len(products) == 1, (upc, len(products))
    o1_products.append(products[0])
    o1_sources[upc] = {
        "capture": f"C:/m8/evidence/live190/o1/captures/{cap}.raw.gz",
        "capture_sha256": rec.get("raw_sha256"),
        "capture_gz_sha256": hashlib.sha256(raw).hexdigest(),
        "request_id": rec.get("request_id"),
        "result_metadata_run_js": (r0.get("metadata") or {}).get("run_js"),
        "state_path": "calypso.domains.products.<upc>.data",
    }
(OUT / "o1_state_products_m6.json").write_text(
    json.dumps({"data": {"products": o1_products}}, ensure_ascii=False, indent=1) + "\n",
    encoding="utf-8",
    newline="\n",
)
(OUT / "SOURCES_M6.json").write_text(
    json.dumps({"q2_cards_and_state": q2_sources, "o1_product_pages": o1_sources}, indent=1) + "\n",
    encoding="utf-8",
    newline="\n",
)
for f in sorted(OUT.iterdir()):
    print(f.name, f.stat().st_size)
