"""Build tests/fixtures/oxylabs_2026-11-06 for release 1.9.0 (M4/M6): real saved pages, trimmed only.

- q2_cards_m4.html: the grid cards of the four M4 products as run Q2 (01M6E5V6CASQ8F00VC8PE9TFYW) saved them
  (each card's outer HTML unchanged, inside the grid container the parser reads).
- q2_state_products_m4.json: the same products' page-state product data saved by Q2 (products_v2 artifacts).
- pdp_*.html.gz: product pages saved by stage O1 (2026-11-06), passed through the collector's sanitizer (as the
  collector stores pages): one rendered (coupons shown), two unrendered (provider states run_js false).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

from marianos_headless.collection.live import CARD_CSS, GRID_CSS, grid_cards
from marianos_headless.sites.marianos.sanitize import sanitize_html

OUT = Path(sys.argv[1])
Q2 = Path("C:/m6/q180/data")
RUN = "01M6E5V6CASQ8F00VC8PE9TFYW"
O1 = Path("C:/m8/evidence/live190/o1/captures")
UPCS = ["0001780014939", "0001780014941", "0002310014848", "0003980014995"]

OUT.mkdir(parents=True, exist_ok=True)
prov = json.loads(
    (Q2 / "runs" / "marianos-53100502-pickup" / RUN / "exports" / "provenance.json").read_text(encoding="utf-8")
)["records"]
cards_html: list[str] = []
sources: dict[str, dict] = {}
products: dict[str, dict] = {}
for upc in UPCS:
    cap = prov[upc]["capture"]
    raw = (Q2 / cap["dom_key"]).read_bytes()
    html = gzip.decompress(raw).decode("utf-8")
    tree = LexborHTMLParser(html)
    grid = tree.css_first(GRID_CSS)
    found = None
    for n in grid.css(CARD_CSS):
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
    resp = (prov[upc].get("source_check") or {}).get("response") or {}
    fetch_id = resp.get("fetch_id")
    raw_dir = Q2 / "runs" / "marianos-53100502-pickup" / RUN / "live" / "raw"
    for f in sorted(raw_dir.glob(f"{fetch_id}.*.products_v2.json.gz")):
        doc = json.loads(gzip.decompress(f.read_bytes()))
        for p in doc["data"]["products"]:
            if ((p.get("item") or {}).get("upc") or p.get("id")) == upc:
                products[upc] = p
                sources[upc]["state_artifact"] = f.name
                sources[upc]["state_artifact_gz_sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()
    assert upc in products, upc

page = (
    "<!doctype html><html><body>\n"
    "<!-- Grid cards saved by run Q2 (01M6E5V6CASQ8F00VC8PE9TFYW, 2026-11-02, store 53100502 PICKUP); each card's\n"
    "     outer HTML is unchanged; only the rest of each page is left out. Sources: README.md. -->\n"
    '<div data-testid="paginate-items">\n' + "\n".join(cards_html) + "\n</div></body></html>\n"
)
(OUT / "q2_cards_m4.html").write_text(page, encoding="utf-8", newline="\n")
(OUT / "q2_state_products_m4.json").write_text(
    json.dumps({"data": {"products": [products[u] for u in UPCS]}}, ensure_ascii=False, indent=1) + "\n",
    encoding="utf-8",
    newline="\n",
)

pdps = {
    "pdp_0001780014939_rendered.html.gz": "03_c3_pdp_js",
    "pdp_0001780014941_unrendered.html.gz": "04_c4_pdp_0001780014941",
    "pdp_0001820020352_unrendered_sale.html.gz": "09_m6c_pdp_0001820020352",
}
pdp_meta = {}
for name, cap in pdps.items():
    env = json.loads(gzip.decompress((O1 / f"{cap}.raw.gz").read_bytes()))
    rec = json.loads((O1 / f"{cap}.json").read_text(encoding="utf-8"))
    r0 = env["results"][0]
    sanitized, report = sanitize_html(r0["html"])
    body = sanitized.encode("utf-8")
    (OUT / name).write_bytes(gzip.compress(body, mtime=0))
    pdp_meta[name] = {
        "capture": f"C:/m8/evidence/live190/o1/captures/{cap}.raw.gz",
        "capture_sha256": rec.get("raw_sha256"),
        "request_id": rec.get("request_id"),
        "url": r0.get("url") or (r0.get("metadata") or {}).get("url"),
        "result_metadata_run_js": (r0.get("metadata") or {}).get("run_js"),
        "requested": env.get("params"),
        "sanitized_html_sha256": hashlib.sha256(body).hexdigest(),
        "sanitize": {"input_sha256": report.input_sha256, "output_sha256": report.output_sha256},
    }
(OUT / "SOURCES.json").write_text(
    json.dumps({"q2_cards_and_state": sources, "o1_product_pages": pdp_meta}, indent=1) + "\n",
    encoding="utf-8",
    newline="\n",
)
print(json.dumps({"cards": len(cards_html), "products": len(products), "pdps": list(pdp_meta)}, indent=1))
for f in sorted(OUT.iterdir()):
    print(f.name, f.stat().st_size)
