"""P3: the Oxylabs Web API alone (the Bearer-key service at webapi.oxylabs.io), for Mariano's Lakeshore East.

The key (``OXYLABS_API`` in ``oxylabs.env``) is a Web API key; the Classic Web Scraper API (an API username
and password at realtime.oxylabs.io) has no credentials here and is NOT TESTED. The Web API lists dedicated
Mariano's scrapers (``/v1/scrape/marianos``, ``/marianos/search``, ``/marianos/product``) whose OPTIONS
answers (2026-10-28 18:43Z) name ``store_id`` and ``fulfillment_type`` (``delivery``, ``in_store``,
``pickup``); the search scraper also takes ``brand`` and ``price_range`` (format not documented).

Each submission is reserved in the ledger before it is sent (one result each). Oxylabs documents no balance or
usage API; this ledger is the count. Every answer is analysed with the collector's own page parsers: the store
the page state says is active, the header's store and modality, the product cards and their displayed prices.
A page whose state does not show store 53100503 In Store is a failed location test, whatever prices it shows.

    python -m probes.oxylabs_web fetch --endpoint marianos --url URL [--store 53100503 --fulfillment in_store]
    python -m probes.oxylabs_web fetch --endpoint marianos/search --query "honey smacks" [...]
    python -m probes.oxylabs_web fetch --endpoint marianos/product --query 0003800019828 [...]
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import httpx

from marianos_headless.collection.live import grid_cards
from marianos_headless.sites.marianos.dom_parsers import parse_page
from marianos_headless.sites.marianos.initial_state import InitialStateNotFound, parse_initial_state
from marianos_headless.sites.marianos.search_state import search_summary
from marianos_headless.sites.marianos.store_context import store_context_from_state
from probes.common import (
    CAPS,
    CapReached,
    Evidence,
    Ledger,
    out_dir,
    read_dotenv,
    revision,
    secrets_dir,
    utc_now,
)

BASE = "https://webapi.oxylabs.io"
PHASE = "P3"
LOCATION = "53100503"


def analyse(html: str) -> dict[str, Any]:
    out: dict[str, Any] = {"html_bytes": len(html.encode("utf-8"))}
    try:
        ctx = store_context_from_state(parse_initial_state(html))
        st = ctx.store(LOCATION)
        out["state"] = {
            "active_modality": ctx.active_modality,
            "active_destination": (ctx.active_modality_entry() or None)
            and ctx.active_modality_entry().destination_location_id,  # type: ignore[union-attr]
            "store_ids": [s.location_id for s in ctx.stores],
            "laf_store_ids": list(ctx.laf_store_ids),
            "cms_scopes": list(ctx.cms_scopes),
            "store_53100503": None
            if st is None
            else {
                "vanity_name": st.vanity_name,
                "postal_code": st.postal_code,
                "address_lines": list(st.address_lines),
            },
            "site_version": ctx.site_version,
        }
    except InitialStateNotFound as e:
        out["state"] = {"error": f"no initial state: {e}"}
    except Exception as e:
        out["state"] = {"error": f"{type(e).__name__}: {e}"}
    page = parse_page(html)
    h = page.header
    out["header"] = (
        None
        if h is None
        else {
            "vanity_name": h.vanity_name,
            "modality_text": h.modality_text,
            "button_label": h.button_label,
            "logo_url": h.logo_url,
        }
    )
    out["cards"] = len(page.cards)
    out["cards_with_upc"] = sum(1 for c in page.cards if c.upc)
    out["cards_with_price"] = sum(1 for c in page.cards if c.price.regular_price)
    out["cards_with_ppm"] = sum(1 for c in page.cards if c.ppm_text)
    out["coupon_cards"] = len(page.coupons)
    # The collector's own grid reader (parse_page reads category listings, not the search grid).
    _, grid, _, _ = grid_cards(html)
    out["grid_cards"] = len(grid)
    try:
        summary = search_summary(parse_initial_state(html))
    except (InitialStateNotFound, ValueError):
        summary = None
    out["search"] = summary.as_dict() if summary is not None else None
    out["first_cards"] = [
        {
            "upc": c.upc,
            "title": c.title[:70],
            "size": c.size_text,
            "kind": c.price.kind.value,
            "regular": c.price.regular_price,
            "sale": c.price.sale_price,
            "ppm": c.ppm_text,
            "zone": c.zone.text[:80] if c.zone else "",
            "url": c.url,
        }
        for c in page.cards[:60]
    ]
    low = html.lower()
    out["markers"] = {
        k: (k in low)
        for k in (
            "lakeshore east",
            "access denied",
            "captcha",
            "edgesuite",
            "pickup",
            "in store",
            "delivery",
            "prices may vary",
        )
    }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="probes.oxylabs_web")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument(
        "--endpoint", choices=["marianos", "marianos/search", "marianos/product", "general"], required=True
    )
    f.add_argument("--url", default="")
    f.add_argument("--query", default="")
    f.add_argument("--store", default="")
    f.add_argument("--fulfillment", default="")
    f.add_argument("--run-js", action="store_true")
    f.add_argument("--brand", default="", help="the search scraper's brand filter (a partition test)")
    f.add_argument("--price-range", default="", help="the search scraper's price_range filter")
    f.add_argument("--output", default="html")
    f.add_argument("--name", required=True)
    a = ap.parse_args(argv)
    env = read_dotenv(secrets_dir() / "oxylabs.env")
    key = env.get("OXYLABS_API") or env["OXYLABS_WEB_API_KEY"]
    rev = revision()
    root = out_dir() / "oxylabs_web"
    ev = Evidence(root / "evidence", [key])
    ledger = Ledger(out_dir() / "ledger.sqlite", CAPS)
    body: dict[str, Any] = {"output": [a.output], "location": "US"}  # the API takes a list
    if a.url:
        body["url"] = a.url
    if a.query:
        body["query"] = a.query
    if a.store:
        body["store_id"] = a.store
    if a.fulfillment:
        body["fulfillment_type"] = a.fulfillment
    if a.run_js:
        body["run_js"] = True
    if a.brand:
        body["brand"] = a.brand
    if a.price_range:
        body["price_range"] = a.price_range
    path = "/v1/scrape" if a.endpoint == "general" else f"/v1/scrape/{a.endpoint}"
    try:
        res = ledger.reserve("oxylabs", PHASE, 1, f"{a.name}: POST {path}", rev["commit"])
    except CapReached as e:
        print(f"stopped: {e}")
        return 4
    t = utc_now()
    t0 = time.monotonic()
    try:
        r = httpx.post(
            BASE + path,
            json=body,
            timeout=200,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
    except httpx.HTTPError as e:
        ledger.settle(res, 1, f"transport {type(e).__name__} (kept as possibly charged)")
        ev.save(f"{a.name}_transport", {"at": t, "path": path, "body": body, "error": repr(e)})
        print(f"transport error {e!r}")
        return 1
    secs = round(time.monotonic() - t0, 1)
    charged = r.status_code == 200 or not (
        r.status_code == 401 or b"REQUEST_FAILED_AFTER_TOO_MANY_RETRIES" in r.content[:4000]
    )
    ledger.settle(res, 1 if charged else 0, str(r.status_code))
    try:
        env_json = r.json()
    except ValueError:
        env_json = {"_text": r.text[:4000]}
    html = ""
    results = env_json.get("results") if isinstance(env_json, dict) else None
    r0 = results[0] if isinstance(results, list) and results and isinstance(results[0], dict) else {}
    if isinstance(r0.get("html"), str):
        html = r0["html"]
    record = {
        "requested_at": t,
        "seconds": secs,
        "endpoint": path,
        "request_body": body,
        "status": r.status_code,
        "headers": dict(r.headers),
        "revision": rev,
        "envelope": {
            k: v for k, v in (env_json.items() if isinstance(env_json, dict) else []) if k != "results"
        },
        "result_keys": sorted(k for k, v in r0.items() if v is not None),
        "result_metadata": r0.get("metadata"),
        "json_output": r0.get("json") if a.output == "json" else None,
    }
    record["headers"] = {
        k: v for k, v in record["headers"].items() if k.lower() not in ("authorization", "set-cookie")
    }
    analysis = analyse(html) if html else {"html_bytes": 0}
    record["analysis"] = analysis
    p = ev.save(a.name, record)
    if html:
        ev.save_text(f"{a.name}.html", html)
    print(f"{a.name}: HTTP {r.status_code} in {secs}s, html {analysis['html_bytes']} bytes, saved {p.name}")
    print(
        json.dumps(
            {
                k: analysis.get(k)
                for k in (
                    "state",
                    "header",
                    "cards",
                    "grid_cards",
                    "search",
                    "cards_with_upc",
                    "cards_with_price",
                    "cards_with_ppm",
                    "coupon_cards",
                    "markers",
                )
            },
            indent=1,
        )[:2500]
    )
    for c in analysis.get("first_cards", [])[:8]:
        print("   ", json.dumps(c, ensure_ascii=False)[:260])
    print(
        f"oxylabs submissions recorded in {PHASE}: {ledger.used('oxylabs', PHASE):g} "
        f"of {CAPS[('oxylabs', PHASE)]:g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
