"""M3: trace an exported PPM value to the exact saved source node (independent of the collector's code).

Standard library only. For each UPC it reads the run's export and provenance, opens the linked saved page,
checks the stored file's SHA-256 against the provenance, finds the product's own card in the markup (card
boundaries from the raw HTML, not the collector's parser), lists the card's size/$-per-unit slots, decodes the
page's ``window.__INITIAL_STATE__`` with its own JS-literal decoder, and prints the product's structured
unit-price nodes and the page's own store/fulfillment request state.

Usage: python -I ppm_trace.py <run evidence dir> <out dir> <upc> [<upc> ...]
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

CARD_START = re.compile(r'data-testid="(mini-product-card-\d+|carousel-product-card-[^"]+|product-card-[^"]+)"')
SIZING = re.compile(r'data-testid="product-item-sizing"[^>]*>([^<]*)<')
MARKER = re.compile(r"window\.__INITIAL_STATE__\s*=\s*JSON\.parse\('")
PPM_DISPLAY = re.compile(r"^\$\d[\d,]*(?:\.\d+)?\s*/\s*[A-Za-z][A-Za-z .]*$")


def js_literal(html: str) -> str:
    m = MARKER.search(html)
    if m is None:
        raise SystemExit("no __INITIAL_STATE__")
    i, start = m.end(), m.end()
    while i < len(html):
        if html[i] == "\\":
            i += 2
            continue
        if html[i] == "'":
            return html[start:i]
        i += 1
    raise SystemExit("unterminated literal")


ESC = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0", "'": "'", '"': '"',
       "\\": "\\", "/": "/"}


def js_decode(raw: str) -> str:
    out, i = [], 0
    while i < len(raw):
        c = raw[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        n = raw[i + 1]
        if n == "u":
            out.append(chr(int(raw[i + 2 : i + 6], 16)))
            i += 6
        elif n == "x":
            out.append(chr(int(raw[i + 2 : i + 4], 16)))
            i += 4
        elif n == "\n":
            i += 2
        else:
            out.append(ESC.get(n, n))
            i += 2
    return "".join(out)


def state_of(html: str) -> dict:
    return json.loads(js_decode(js_literal(html)))


def dig(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def card_of(html: str, upc: str) -> tuple[str, int, int, list[str]]:
    """The card whose own product link names the UPC: (card test id, start, end, sizing slot texts)."""
    starts = [(m.start(), m.group(1)) for m in CARD_START.finditer(html)]
    href = re.search(r'href="/p/[^"]*/' + re.escape(upc) + r'(?:\?[^"]*)?"', html)
    if href is None:
        raise SystemExit(f"{upc}: no product link in the page")
    found = []
    for idx, (pos, tid) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(html)
        if pos <= href.start() < end:
            found.append((tid, pos, end))
    if not found:
        raise SystemExit(f"{upc}: link outside every card")
    tid, pos, end = found[-1]
    slots = [m.group(1).strip() for m in SIZING.finditer(html, pos, end)]
    links = set(re.findall(r'href="/p/[^"]*/(\d{13})', html[pos:end]))
    if links != {upc}:
        raise SystemExit(f"{upc}: card {tid} links other products too: {sorted(links)}")
    return tid, pos, end, slots


def product_data(state: dict, upc: str) -> tuple[str, dict]:
    prods = dig(state, "calypso", "domains", "products", default={}) or {}
    for key, v in prods.items():
        data = v.get("data") if isinstance(v, dict) else None
        if isinstance(data, dict) and str(data.get("id")) == upc:
            return f"calypso.domains.products[{key!r}].data", data
    raise SystemExit(f"{upc}: not in the page state")


def main() -> int:
    run_dir, out_dir, upcs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    out_dir.mkdir(parents=True, exist_ok=True)
    exp = run_dir / "data" / "exports"
    products = {r["upc"]: r for r in json.loads((exp / "products.json").read_text(encoding="utf-8"))}
    prov = json.loads((exp / "provenance.json").read_text(encoding="utf-8"))
    rows, report = [], {"run_id": prov.get("run_id"), "collector": prov.get("collector"), "traces": []}
    for upc in upcs:
        rec = products[upc]
        pr = prov["records"][upc]
        f = pr["fields"]["ppm"]
        cap = pr["capture"]
        page = run_dir / "data" / "live" / "dom" / Path(cap["dom_key"]).name
        gz = page.read_bytes()
        file_sha = hashlib.sha256(gz).hexdigest()
        html = gzip.decompress(gz).decode("utf-8")
        html_sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
        tid, pos, end, slots = card_of(html, upc)
        ppm_slots = [s for s in slots if PPM_DISPLAY.match(s)]
        size_slots = [s for s in slots if not PPM_DISPLAY.match(s)]
        sponsored = "pla-compliance-tag" in html[pos:end]
        state = state_of(html)
        path, data = product_data(state, upc)
        sp = dig(data, "price", "storePrices", default={}) or {}
        rv = dig(state, "search", "searchAll", "requestVars", default={}) or {}
        nodes = {
            f"{path}.price.storePrices.regular.equivalizedUnitPrice": dig(sp, "regular", "equivalizedUnitPrice"),
            f"{path}.price.storePrices.regular.equivalizedUnitPriceString": dig(sp, "regular", "equivalizedUnitPriceString"),
            f"{path}.price.storePrices.promo.equivalizedUnitPrice": dig(sp, "promo", "equivalizedUnitPrice"),
            f"{path}.price.storePrices.promo.equivalizedUnitPriceString": dig(sp, "promo", "equivalizedUnitPriceString"),
            f"{path}.price.storePrices.regular.price": dig(sp, "regular", "price"),
            f"{path}.price.storePrices.promo.price": dig(sp, "promo", "price"),
            f"{path}.price.storePrices.sourceLocationId": sp.get("sourceLocationId"),
            f"{path}.item.customerFacingSize": dig(data, "item", "customerFacingSize"),
            f"{path}.item.pidSizeQuantity": dig(data, "item", "pidSizeQuantity"),
            f"{path}.item.pidSizeUnitOfMeasureName": dig(data, "item", "pidSizeUnitOfMeasureName"),
            f"{path}.price.sellBy": dig(data, "price", "sellBy"),
        }
        context = {k: rv.get(k) for k in ("locationId", "activeModalityType", "taxonomyId", "page", "brandName")}
        exported = rec["ppm"]
        in_card = exported in ppm_slots
        in_state = any(exported in (v if isinstance(v, list) else [v]) for k, v in nodes.items()
                       if k.endswith("equivalizedUnitPriceString") and v)
        excerpt = re.sub(r"\s+", " ", html[pos:end])
        (out_dir / f"excerpt_{upc}_card.html").write_text(excerpt, encoding="utf-8")
        (out_dir / f"excerpt_{upc}_state.json").write_text(
            json.dumps({"path": path, "nodes": nodes, "request_state": context}, indent=1, ensure_ascii=False),
            encoding="utf-8")
        verdict = (
            "SOURCE_VALUE_ANOMALY: the source itself displays this value for this product at this store and "
            "fulfillment (card slot and structured node agree); exported as displayed, never recomputed"
            if in_card and in_state else
            "EXTRACTION_MISMATCH: the exported value is not what the product's own card/node states"
        )
        t = {
            "upc": upc,
            "title": rec["product_title"],
            "run_id": prov.get("run_id"),
            "collector": prov.get("collector"),
            "status": pr.get("status"),
            "exported": {"ppm": exported, "weight": rec["weight"], "regular_price": rec["regular_price"],
                         "sale_price": rec["sale_price"], "unit_price": rec["unit_price"], "crawl_date": rec["crawl_date"]},
            "provenance_ppm": f,
            "capture": cap,
            "file": str(page.relative_to(run_dir)).replace("\\", "/"),
            "file_sha256": file_sha,
            "file_sha256_matches_provenance": file_sha == cap["dom_sha256"],
            "decoded_html_sha256": html_sha,
            "card": {"test_id": tid, "offset": [pos, end], "sizing_slots": slots, "ppm_slots": ppm_slots,
                     "size_slots": size_slots, "sponsored_placement": sponsored},
            "structured": nodes,
            "request_state": context,
            "exported_value_in_card_slot": in_card,
            "exported_value_in_structured_node": in_state,
            "conclusion": verdict,
        }
        report["traces"].append(t)
        rows.append({
            "upc": upc, "run_id": prov.get("run_id"), "revision": (prov.get("collector") or {}).get("commit", "")
            if isinstance(prov.get("collector"), dict) else prov.get("collector"),
            "record_status": pr.get("status"), "exported_ppm": exported, "exported_weight": rec["weight"],
            "source_locator": f"{t['file']} card {tid}: [data-testid=\"product-item-sizing\"] slot '{';'.join(ppm_slots)}'",
            "structured_locator": f"{path}.price.storePrices.regular.equivalizedUnitPrice = "
            + json.dumps(nodes[f'{path}.price.storePrices.regular.equivalizedUnitPrice'], ensure_ascii=False),
            "observed_at": cap["fetched_at"], "store_context": f"{context['locationId']} {context['activeModalityType']}",
            "stored_file_sha256": file_sha, "provenance_sha256": cap["dom_sha256"],
            "decoded_html_sha256": html_sha,
            "transformation": "card slot text taken as displayed (dom_parsers: second sizing slot matching $/unit); "
            "no arithmetic",
            "conclusion": verdict.split(":")[0],
        })
    (out_dir / "PPM_TRACE.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    with (out_dir / "PPM_RECONCILIATION.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    for t in report["traces"]:
        print(json.dumps({k: t[k] for k in ("upc", "exported", "file_sha256_matches_provenance", "card",
                                             "structured", "request_state", "conclusion")}, indent=1,
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
