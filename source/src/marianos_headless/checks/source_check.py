"""Check Mariano's records against the site's own product data, independently of the collector's parser
(offline: no network request). Used by the automated canary (the first recorded page step of a run) and
by ``marianos-collector validate-export`` (a whole run's export against its stored responses).

A listing page requests its products' data from ``/atlas/v1/product/v2/products`` (stored by the run as
``live/raw/<step>.<n>.products_v2.json.gz``). For every record the product is looked up by its UPC and
compared: the response names the configured store as the source of its prices
(``price.storePrices.sourceLocationId``), and the record's displayed regular and sale prices equal the
store's regular and promotional prices in the response. A record whose UPC is in no response is reported
``unverified`` (never assumed correct).

A listing page also embeds, in its server-rendered state (``window.__INITIAL_STATE__``), the product data of
its first page (``calypso.useCases.getProducts.*.response.data.products`` and ``calypso.domains.products``),
the same objects as the product responses. Release 1.2.1 reads them from the stored page copies as a second,
labelled class of evidence (``embedded_page_data``): the site's structured data for the store, not the card
text the record was read from. Each result names the evidence that decided it (a product response is
preferred when both agree).
"""

from __future__ import annotations

import gzip
import json
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_AMOUNT = re.compile(r"\d+(?:\.\d+)?")


def products_of(body: bytes) -> Iterable[dict[str, Any]]:
    """The products of one products response (empty for anything else)."""
    try:
        data = json.loads(body)
    except ValueError:
        return []
    products = ((data or {}).get("data") or {}).get("products") if isinstance(data, dict) else None
    return [p for p in products or [] if isinstance(p, dict)]


def upc13(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits.zfill(13)[-13:] if digits else ""


def amount(text: Any) -> Decimal | None:
    m = _AMOUNT.search(str(text or "").replace(",", ""))
    if not m:
        return None
    try:
        return Decimal(m.group(0))
    except InvalidOperation:
        return None


def store_prices(product: Mapping[str, Any]) -> tuple[str, Decimal | None, Decimal | None]:
    """(source location id, regular price, promotional price) of a product in the response."""
    sp = ((product.get("price") or {}).get("storePrices")) or {}
    reg = sp.get("regular") or {}
    # "price" ("USD 3.99"); a response without it gives the regular price as its description ("$3.99").
    regular = amount(reg.get("price") or reg.get("defaultDescription"))
    # A promotion's description may be a multi-buy ("2 For $5.00"): only its "price" is a unit price.
    promo = amount((sp.get("promo") or {}).get("price"))
    return str(sp.get("sourceLocationId") or ""), regular, promo


PRODUCT_RESPONSE = "product_response"
EMBEDDED_PAGE_DATA = "embedded_page_data"


def embedded_products(html: str) -> list[dict[str, Any]]:
    """The product objects a page's server-rendered state embeds (empty when it has none)."""
    from marianos_headless.sites.marianos.initial_state import parse_initial_state

    try:
        state = parse_initial_state(html)
    except ValueError:
        return []
    calypso = state.get("calypso") if isinstance(state, dict) else None
    if not isinstance(calypso, dict):
        return []
    found: list[dict[str, Any]] = []
    for case in (calypso.get("useCases") or {}).get("getProducts", {}).values():
        data = ((case or {}).get("response") or {}).get("data") if isinstance(case, dict) else None
        found.extend(p for p in (data or {}).get("products") or [] if isinstance(p, dict))
    for entry in ((calypso.get("domains") or {}).get("products") or {}).values():
        data = entry.get("data") if isinstance(entry, dict) else None
        if isinstance(data, dict):
            found.append(data)
    return [p for p in found if isinstance(p.get("item"), dict) and p["item"].get("upc")]


def index(bodies: Iterable[bytes], pages: Iterable[str] = ()) -> dict[str, list[dict[str, Any]]]:
    """Products by UPC: from product responses, then from page copies' embedded data, each tagged with
    its evidence class (``_evidence``)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for evidence, products in (
        (PRODUCT_RESPONSE, (p for body in bodies for p in products_of(body))),
        (EMBEDDED_PAGE_DATA, (p for html in pages for p in embedded_products(html))),
    ):
        for p in products:
            key = upc13((p.get("item") or {}).get("upc") or p.get("upc"))
            if key:
                out.setdefault(key, []).append({**p, "_evidence": evidence})
    return out


def compare(record: Mapping[str, Any], product: Mapping[str, Any], location_id: str) -> dict[str, bool]:
    location, regular, promo = store_prices(product)
    rec_regular, rec_sale = amount(record.get("regular_price")), amount(record.get("sale_price"))
    if rec_regular is None and rec_sale is None and not location:
        # No price shown on the page and none in the site's data for the store: consistent.
        return {"no_price_shown_or_returned": True}
    checks = {"store": location == location_id}
    if rec_regular is not None:
        checks["regular_price"] = regular is not None and rec_regular == regular
    if rec_sale is not None:
        # A sale shows the promotional price; with no promotion in the response the sale cannot be checked.
        checks["sale_price"] = promo is not None and rec_sale == promo
    return checks


def check_records(
    records: Iterable[Mapping[str, Any]], products: Mapping[str, list[dict[str, Any]]], location_id: str
) -> dict[str, Any]:
    summary = {"records": 0, "verified": 0, "mismatch": 0, "unverified": 0}
    by_evidence: dict[str, int] = {}
    fields: dict[str, int] = {}
    results = []
    for rec in records:
        summary["records"] += 1
        candidates = products.get(upc13(rec.get("upc")), [])
        if not candidates:
            summary["unverified"] += 1
            results.append(
                {
                    "upc": rec.get("upc"),
                    "result": "unverified",
                    "reason": "UPC in no product response and in no page's embedded data",
                }
            )
            continue
        # The candidate with the fewest differences decides; a product response before embedded page data.
        scored = sorted(
            ((compare(rec, p, location_id), p.get("_evidence", PRODUCT_RESPONSE)) for p in candidates),
            key=lambda c: (sum(not ok for ok in c[0].values()), c[1] != PRODUCT_RESPONSE),
        )
        best, evidence = scored[0]
        bad = [k for k, ok in best.items() if not ok]
        for k in bad:
            fields[k] = fields.get(k, 0) + 1
        result = "mismatch" if bad else "verified"
        summary[result] += 1
        by_evidence[f"{result}:{evidence}"] = by_evidence.get(f"{result}:{evidence}", 0) + 1
        results.append(
            {
                "upc": rec.get("upc"),
                "result": result,
                "evidence": evidence,
                "mismatched_fields": bad,
                "candidates": len(candidates),
            }
        )
    return {"summary": summary, "by_evidence": by_evidence, "mismatched_fields": fields, "results": results}


def check(
    records: list[dict[str, Any]], raw_dir: Path, location_id: str, dom_dir: Path | None = None
) -> dict[str, Any]:
    """Every record against the products responses stored under ``raw_dir`` and, with ``dom_dir``, the
    product data embedded in the page copies stored there."""
    files = sorted(p for p in raw_dir.rglob("*products_v2*") if p.is_file())
    bodies = []
    for f in files:
        data = f.read_bytes()
        bodies.append(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
    pages = []
    for f in sorted(dom_dir.rglob("*.html*")) if dom_dir is not None else []:
        data = f.read_bytes()
        pages.append((gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data).decode("utf-8", "replace"))
    products = index(bodies, pages)
    out = check_records(records, products, location_id)
    return {
        "responses_read": len(files),
        "pages_read": len(pages),
        "products_in_sources": len(products),
        **out,
    }
