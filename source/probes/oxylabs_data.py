"""Q1: the site's own data requests through the Oxylabs Web API's Mariano's URL scraper (test plan 1.4.0).

The website's Load More asks the site for one page of a listing (``/atlas/v1/search/v1/products-search`` with
``filter.taxonomies``, ``filter.locationId`` and ``page.offset``), then for the products of that page
(``/atlas/v1/product/v2/products?filter.gtin13s=…``) and their coupons (``/atlas/v1/savings-coupons/v2/
coupons?filter.upc=…``). These URLs are rebuilt here exactly as the site made them (captured live on
2026-10-23, run 01M5NAQKQ0H28DCGK5BE8XCP2N of release 1.2.1) and sent to ``POST /v1/scrape/marianos`` with
the store and fulfillment parameters, one hypothesis per submission (TEST_PLAN_140.md section 4).

Each submission is reserved in the probe ledger before it is sent (phase Q1, cap 20). The answer is saved
sanitized (no Authorization header, no key), its body gzipped as received, and one row is appended to the
hypothesis log (``hypotheses.csv``): what changed, what was expected, the provider's request id, the status,
the identities returned and the store the answer states.

    python -m probes.oxylabs_data search --hyp H1 --taxonomy 03001 --offset 0
    python -m probes.oxylabs_data products --hyp H3 --upcs-from H2
    python -m probes.oxylabs_data coupons --hyp H4 --upcs-from H2
"""

from __future__ import annotations

import argparse
import csv
import gzip
import html as html_lib
import json
import re
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from probes.common import CapReached, Evidence, Ledger, out_dir, read_dotenv, revision, secrets_dir, utc_now

BASE = "https://webapi.oxylabs.io"
SITE = "https://www.marianos.com"
PHASE = "Q1"
CAP = 20
STORE = "53100503"
FACETS = (
    "TAXONOMY",
    "BRAND",
    "NUTRITION",
    "MORE_OPTIONS",
    "PRICE",
    "SAVINGS",
    "COLOR",
    "FLAVOR",
    "SCENT",
    "FSA_HSA_ELIGIBLE",
)
PROJECTIONS = ",".join(
    ("items.full", "offers.compact", "nutrition.label", "inventory.projected", "preferences.compact",
     "variantGroupings.compact")
)  # fmt: skip
LOG_FIELDS = (
    "hyp",
    "requested_at",
    "seconds",
    "kind",
    "change",
    "expected",
    "url",
    "status",
    "provider_request_id",
    "provider_state",
    "body_kind",
    "identities",
    "new_identities",
    "total",
    "available",
    "store_stated",
    "evidence",
    "charged",
)


def search_url(*, taxonomy: str, offset: int, size: int, query: str = "", group: bool = True) -> str:
    """The products-search request of a listing page, in the order the site writes its parameters."""
    pairs: list[tuple[str, str]] = [("option.facets", f) for f in FACETS]
    if group:
        pairs.append(("option.groupBy", "PRODUCT_VARIANT"))
    pairs.append(("filter.locationId", STORE))
    if query:
        pairs.append(("filter.query", query))
    if taxonomy:
        pairs.append(("filter.taxonomies", taxonomy))
    pairs += [("filter.fulfillmentMethods", m) for m in ("IN_STORE", "PICKUP", "DELIVERY")]
    pairs += [("page.offset", str(offset)), ("page.size", str(size)), ("option.personalization", "RELEVANCE")]
    return f"{SITE}/atlas/v1/search/v1/products-search?{urlencode(pairs)}"


def products_url(upcs: Iterable[str]) -> str:
    pairs = [("filter.gtin13s", u) for u in upcs] + [("filter.verified", "true")]
    return f"{SITE}/atlas/v1/product/v2/products?{urlencode(pairs)}&projections={quote(PROJECTIONS, safe='')}"


def coupons_url(upcs: Iterable[str]) -> str:
    pairs = [("filter.upc", u) for u in upcs] + [("filter.type", "standard"), ("filter.type", "cash_back")]
    return f"{SITE}/atlas/v1/savings-coupons/v2/coupons?{urlencode(pairs)}"


_PRE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.S | re.I)


def body_json(text: str) -> Any:
    """The JSON the site answered: the raw body, or the text a browser shows inside its ``<pre>``."""
    t = text.strip()
    if t.startswith(("{", "[")):
        return json.loads(t)
    m = _PRE.search(text)
    if m:
        return json.loads(html_lib.unescape(m.group(1)))
    raise ValueError("no JSON in the answer")


def _upcs_in(obj: Any, out: list[str]) -> None:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if k in ("upc", "gtin13") and isinstance(v, str) and v.isdigit() and v not in out:
                out.append(v)
            else:
                _upcs_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _upcs_in(v, out)


def analyse(kind: str, doc: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"top_keys": sorted(doc.keys()) if isinstance(doc, Mapping) else type(doc).__name__}
    data = doc.get("data") if isinstance(doc, Mapping) else None
    if kind == "search":
        meta = ((doc.get("meta") or {}).get("productsSearch") or {}) if isinstance(doc, Mapping) else {}
        upcs: list[str] = []
        _upcs_in(data, upcs)
        out.update(
            body_kind="products_search" if meta or data is not None else "unknown",
            data_keys=sorted(data.keys()) if isinstance(data, Mapping) else type(data).__name__,
            meta_keys=sorted(meta.keys()),
            total=meta.get("totalCount"),
            available=meta.get("availableCount"),
            upcs=upcs,
            category_facet=_facet_summary((meta.get("facets") or {}).get("category")),
            price_facet=(meta.get("facets") or {}).get("price"),
        )
    elif kind == "products":
        products = (data or {}).get("products") if isinstance(data, Mapping) else None
        rows = []
        for p in products or []:
            item, price = p.get("item") or {}, p.get("price") or {}
            sp = price.get("storePrices") or {}
            inv = [
                (loc.get("locationId"), loc.get("stockLevel"))
                for loc in (p.get("inventory") or {}).get("locations") or []
            ]
            rows.append(
                {
                    "upc": item.get("upc"),
                    "description": (item.get("description") or "")[:60],
                    "size": item.get("customerFacingSize"),
                    "sourceLocationId": sp.get("sourceLocationId"),
                    "regular": (sp.get("regular") or {}).get("price"),
                    "promo": (sp.get("promo") or {}).get("price"),
                    "ppm": (sp.get("regular") or {}).get("equivalizedUnitPriceString"),
                    "sellBy": price.get("sellBy"),
                    "orderBy": price.get("orderBy"),
                    "inventory": inv,
                }
            )
        out.update(
            body_kind="products_v2" if products is not None else "unknown",
            products=rows,
            upcs=[r["upc"] for r in rows if r["upc"]],
            store_stated=sorted({str(r["sourceLocationId"]) for r in rows if r["sourceLocationId"]}),
        )
    else:
        coupons = (data or {}).get("coupons") if isinstance(data, Mapping) else None
        items = list(coupons.values()) if isinstance(coupons, Mapping) else list(coupons or [])
        out.update(
            body_kind="coupons" if coupons is not None else "unknown",
            coupons=[
                {
                    "id": c.get("id"),
                    "type": c.get("type"),
                    "title": c.get("title"),
                    "modalities": c.get("modalities"),
                    "upcs": len(c.get("upcs") or []),
                    "displayDescription": (c.get("displayDescription") or "")[:100],
                }
                for c in items
            ],
            upcs=sorted({u for c in items for u in (c.get("upcs") or [])}),
        )
    return out


def page_analysis(text: str, member_of: str) -> dict[str, Any]:
    """A website page: the store its state names, its search summary, its grid cards and, for each product
    of the page state, whether its own taxonomy places it in ``member_of``."""
    from marianos_headless.collection.live import grid_cards
    from marianos_headless.sites.marianos.initial_state import parse_initial_state
    from marianos_headless.sites.marianos.search_state import (
        price_location,
        search_summary,
        state_products,
        taxonomy_ids,
    )
    from probes.oxylabs_web import analyse as page_store_analysis

    out = page_store_analysis(text)
    state = parse_initial_state(text)
    summary = search_summary(state)
    subs = summary.sub_commodities if summary is not None else {}
    _, cards, sponsored, displayed = grid_cards(text)
    products = state_products(state)
    rows = []
    for prod in products:
        upc = str((prod.get("item") or {}).get("upc") or prod.get("id") or "")
        ids = taxonomy_ids(prod, subs.get(upc, ()))
        rows.append({"upc": upc, "member": (member_of in ids) if member_of else None,
                     "store": price_location(prod), "taxonomies": ids[:4]})  # fmt: skip
    grid_upcs = [c.upc for c in cards if c.upc]
    out.update(
        body_kind="page",
        upcs=grid_upcs,
        displayed_total=displayed,
        total=summary.total if summary is not None else None,
        available=summary.available if summary is not None else None,
        request_vars=(state.get("search") or {}).get("searchAll", {}).get("requestVars"),
        grid_cards_n=len(cards),
        sponsored_cards=len(sponsored),
        state_products=len(rows),
        members=sum(1 for r in rows if r["member"]),
        non_members=[r for r in rows if r["member"] is False][:10],
        stores_stated=sorted({str(r["store"]) for r in rows if r["store"]}),
        store_stated=sorted({str(r["store"]) for r in rows if r["store"]}),
    )
    return out


def _facet_summary(tree: Any, depth: int = 0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in tree or []:
        if not isinstance(n, Mapping):
            continue
        out.append({"id": n.get("id"), "name": n.get("name"), "count": n.get("count"), "depth": depth})
        out.extend(_facet_summary(n.get("children"), depth + 1))
    return out


def earlier_upcs(root: Path, hyp: str) -> list[str]:
    for row in reversed(list(_log_rows(root))):
        if row["hyp"] == hyp and row["identities"]:
            return [str(u) for u in json.loads(row["identities"])]
    raise SystemExit(f"no identities logged for {hyp}")


def _log_rows(root: Path) -> Iterable[dict[str, str]]:
    log = root / "hypotheses.csv"
    if log.exists():
        with log.open(encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="probes.oxylabs_data")
    ap.add_argument("kind", choices=["search", "products", "coupons", "page", "scraper-search"])
    ap.add_argument("--hyp", required=True)
    ap.add_argument("--change", default="")
    ap.add_argument("--expected", default="")
    ap.add_argument("--taxonomy", default="")
    ap.add_argument("--query", default="")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--size", type=int, default=24)
    ap.add_argument("--no-group", action="store_true")
    ap.add_argument("--upcs-from", default="", help="a hypothesis whose identities are asked for")
    ap.add_argument("--url", default="", help="page: a website page, read with its embedded page state")
    ap.add_argument("--member-of", default="", help="page: the listing ID the products must belong to")
    ap.add_argument("--price-range", default="", help="scraper-search: the search scraper's price_range")
    ap.add_argument("--brand", default="", help="scraper-search: the search scraper's brand")
    ap.add_argument("--run-js", action="store_true", help="the provider renders the page with JavaScript")
    ap.add_argument(
        "--endpoint",
        choices=["marianos", "general"],
        default="marianos",
        help="general: /v1/scrape (no store parameters; the store is in the products-search URL)",
    )
    ap.add_argument("--dry-run", action="store_true", help="print the request; nothing is sent")
    a = ap.parse_args(argv)

    root = out_dir() / "oxylabs_data"
    if a.kind == "page":
        url = a.url
    elif a.kind == "scraper-search":
        url = ""
    elif a.kind == "search":
        url = search_url(
            taxonomy=a.taxonomy, offset=a.offset, size=a.size, query=a.query, group=not a.no_group
        )
    else:
        upcs = earlier_upcs(root, a.upcs_from)
        url = products_url(upcs) if a.kind == "products" else coupons_url(upcs)
    body: dict[str, Any] = {"output": ["html"], "location": "US", "url": url}
    if a.endpoint == "marianos":
        body.update(store_id=STORE, fulfillment_type="in_store")
    path = "/v1/scrape/marianos" if a.endpoint == "marianos" else "/v1/scrape"
    if a.kind == "scraper-search":
        # the dedicated search scraper: query plus its documented filters, the store parameters
        body = {
            "output": ["html"],
            "location": "US",
            "query": a.query,
            "store_id": STORE,
            "fulfillment_type": "in_store",
        }
        if a.price_range:
            body["price_range"] = a.price_range
        if a.brand:
            body["brand"] = a.brand
        path = "/v1/scrape/marianos/search"
    if a.run_js:
        body["run_js"] = True
    if a.dry_run:
        print(json.dumps(body, indent=1))
        return 0

    env = read_dotenv(secrets_dir() / "oxylabs.env")
    key = env.get("OXYLABS_API") or env["OXYLABS_WEB_API_KEY"]
    rev = revision()
    ev = Evidence(root / "evidence", [key])
    ledger = Ledger(out_dir() / "ledger.sqlite", {("oxylabs", PHASE): CAP})
    name = f"{a.hyp}_{a.kind}"
    try:
        res = ledger.reserve("oxylabs", PHASE, 1, f"{name}: POST {path}", rev["commit"])
    except CapReached as e:
        print(f"stopped: {e}")
        return 4
    t, t0 = utc_now(), time.monotonic()
    try:
        r = httpx.post(
            BASE + path,
            json=body,
            timeout=200,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
    except httpx.HTTPError as e:
        ledger.settle(res, 1, f"transport {type(e).__name__} (kept as possibly charged)")
        ev.save(f"{name}_transport", {"at": t, "body": body, "error": repr(e)})
        print(f"transport error {e!r}")
        return 1
    secs = round(time.monotonic() - t0, 1)
    free = r.status_code == 401 or b"REQUEST_FAILED_AFTER_TOO_MANY_RETRIES" in r.content[:4000]
    charged = r.status_code == 200 or not free
    ledger.settle(res, 1 if charged else 0, str(r.status_code))
    try:
        envelope = r.json()
    except ValueError:
        envelope = {"_text": r.text[:4000]}
    results = envelope.get("results") if isinstance(envelope, dict) else None
    r0 = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
    html = r0.get("html")
    text = html if isinstance(html, str) else ""
    analysis: dict[str, Any] = {"answer_bytes": len(text.encode("utf-8"))}
    if text:
        ev_path = root / "evidence" / f"{name}.body.gz"
        ev_path.parent.mkdir(parents=True, exist_ok=True)
        ev_path.write_bytes(gzip.compress(text.encode("utf-8")))
        try:
            analysis.update(
                page_analysis(text, a.member_of)
                if a.kind in ("page", "scraper-search")
                else analyse(a.kind, body_json(text))
            )
        except ValueError as e:
            analysis["body_kind"] = f"not JSON ({e}); first bytes: {text[:160]!r}"
    meta = r0.get("metadata") or {}
    if a.kind == "scraper-search":
        # the page the provider built from the query and filters, as its answer names it
        url = str(r0.get("url") or f"search scraper: {json.dumps(body, sort_keys=True)}")
    record = {
        "requested_at": t,
        "seconds": secs,
        "hypothesis": a.hyp,
        "change": a.change,
        "expected": a.expected,
        "endpoint": path,
        "request_body": body,
        "status": r.status_code,
        "headers": {k: v for k, v in r.headers.items() if k.lower() not in ("authorization", "set-cookie")},
        "revision": rev,
        "envelope": {k: v for k, v in envelope.items() if k != "results"}
        if isinstance(envelope, dict)
        else {},
        "result_metadata": meta,
        "analysis": analysis,
    }
    saved = ev.save(name, record)
    known: set[str] = set()
    for row in _log_rows(root):
        known.update(json.loads(row["identities"] or "[]"))
    ids = analysis.get("upcs") or []
    log = root / "hypotheses.csv"
    new_file = not log.exists()
    with log.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(
            {
                "hyp": a.hyp,
                "requested_at": t,
                "seconds": secs,
                "kind": a.kind,
                "change": a.change,
                "expected": a.expected,
                "url": url,
                "status": r.status_code,
                "provider_request_id": meta.get("request_id")
                or (envelope.get("instance") if isinstance(envelope, dict) else ""),
                "provider_state": envelope.get("state") or envelope.get("title")
                if isinstance(envelope, dict)
                else "",
                "body_kind": analysis.get("body_kind", ""),
                "identities": json.dumps(ids),
                "new_identities": len([u for u in ids if u not in known]),
                "total": analysis.get("total", ""),
                "available": analysis.get("available", ""),
                "store_stated": json.dumps(analysis.get("store_stated", [])),
                "evidence": saved.name,
                "charged": 1 if charged else 0,
            }
        )
    print(f"{name}: HTTP {r.status_code} in {secs}s, {analysis['answer_bytes']} bytes, saved {saved.name}")
    print(
        json.dumps({k: v for k, v in analysis.items() if k not in ("products", "coupons")}, indent=1)[:3000]
    )
    for row in (analysis.get("products") or analysis.get("coupons") or [])[:30]:
        print("   ", json.dumps(row, ensure_ascii=False)[:300])
    print(f"oxylabs submissions recorded in {PHASE}: {ledger.used('oxylabs', PHASE):g} of {CAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
