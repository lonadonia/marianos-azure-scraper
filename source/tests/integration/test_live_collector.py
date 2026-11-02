"""The live collector end to end: a local Chromium over CDP stands in for Scrapfly's cloud browser, a
local mock site (SYNTHETIC pages shaped like the live ones of 2026-10-20: store picker, a paginated grid
with a "Load More Results" button, products-search requests with page.offset) stands in for Mariano's,
and a fake Account API answers for Scrapfly. Chromium resolves no host except 127.0.0.1, so nothing can
reach the retailer or Scrapfly."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.collection.live import LiveCollector
from marianos_headless.collection.nodes import Node
from marianos_headless.core.schema import OUTPUT_FIELDS
from marianos_headless.core.settings import (
    AcquisitionSettings,
    PrivateLabelConfig,
    ScrapflyBrowserSettings,
    Settings,
    StoreConfig,
)
from marianos_headless.db.models import (
    CapturedResponse,
    CategorySource,
    CollectionSegment,
    Event,
    MembershipRow,
    NodeCoverage,
    PageFetch,
    ProductObservation,
    RecordRow,
    Run,
    StoreAttestation,
)
from marianos_headless.publishing.supporting_log import supporting_log
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests import synthetic_marianos as syn
from tests.integration.helpers import seed

pytest.importorskip("playwright")
pytestmark = [pytest.mark.postgres, pytest.mark.browser]

KEY = "scp-live-test-key-never-sent-0123456789"
LAKESHORE = ("53100503", "Marianos Lakeshore East", "333 E Benton Pl, CHICAGO, IL 60601")
OTHER = ("53100511", "Marianos South Loop", "1615 S Clark St, CHICAGO, IL 60616")
PAGE = 24


def _products(prefix: str, n: int, *, approx_every: int = 0) -> tuple[syn.Product, ...]:
    out = []
    for i in range(n):
        size = "about 1 lb" if approx_every and i % approx_every == approx_every - 1 else "15 oz"
        out.append(
            syn.Product(
                f"{prefix}{i:06d}"[-13:].rjust(13, "0"),
                f"item-{prefix}-{i}",
                f"Synthetic {prefix} item {i}",
                size,
                f"${1 + i % 7}.{i % 100:02d}",
                ppm=f"$0.{(i % 9) + 1:01d}0/oz",
            )
        )
    return tuple(out)


_CANNED = list(_products("0009100", 60, approx_every=20))  # 3 approximate weights: excluded, not verified
# Offers as the live grid shows them: a coupon ("Coupon: …" + "View Offer") and a multi-unit deal; the third
# product has a pickup-only coupon its card does not show.
_CANNED[5] = replace(_CANNED[5], zone="$1.99 Synthetic canned coupon", clip=True)
_CANNED[6] = replace(_CANNED[6], zone="2 For $5.00")
CANNED = tuple(_CANNED)
SODA = _products("0009200", 10)
COUPONS = [
    {
        "id": "9001",
        "type": "STANDARD",
        "displayDescription": "$1.99 Synthetic canned coupon",
        "requirementDescription": "When You Buy ONE (1) Synthetic canned item. Limit 5 per transaction.",
        "expirationDate": "2026-10-20T23:59:59Z",
        "modalities": ["PICKUP", "IN_STORE", "DELIVERY"],
        "upcs": [CANNED[5].upc],
        "requirementQuantity": 1,
    },
    {
        "id": "9002",
        "type": "STANDARD",
        "displayDescription": "Save 20% on Synthetic canned items PICKUP OR DELIVERY ONLY",
        "requirementDescription": "Pickup or delivery orders only.",
        "expirationDate": "2026-10-20T23:59:59Z",
        "modalities": ["PICKUP", "DELIVERY"],
        "upcs": [CANNED[7].upc],
        "requirementQuantity": 1,
    },
]


def _product_json(p: syn.Product, loc: str) -> dict[str, Any]:
    """A product of ``/atlas/v1/product/v2/products`` (live shape, 2026-10-20) for the store ``loc``."""
    prices: dict[str, Any] = {
        "sourceLocationId": loc,
        "regular": {
            "defaultDescription": p.price,
            "expirationDate": {"value": "9999-12-31T00:00:00Z"},
            **({"equivalizedUnitPriceString": p.ppm} if p.ppm else {}),
        },
    }
    if p.zone and not p.clip:
        prices["promo"] = {
            "defaultDescription": p.zone,
            "expirationDate": {"value": "2026-10-21T03:59:59.999Z", "timezone": "UTC"},
            "nfor": 2,
        }
    return {
        "item": {"upc": p.upc, "customerFacingSize": p.size},
        "price": {"sellBy": "Unit", "orderBy": "Unit", "storePrices": prices},
        "fulfillmentOptions": ["IN_STORE", "PICKUP"],
        "inventory": {"locations": [{"locationId": loc, "stockLevel": "HIGH"}]},
    }


SPONSORED = syn.Product(
    "0009999000001", "sponsored-thing", "Sponsored Snack", "8 oz", "$4.99", ppm="$0.62/oz"
)
# SYNTHETIC ("sponsored_own" mode): an advertised product of Canned Foods itself, shown only as a sponsored
# card; its product data names the listing (01006), so it is a product of the listing (release 1.5.0).
SPONSORED_OWN = syn.Product(
    "0009999000002", "sponsored-own-beans", "Sponsored Own Beans", "15 oz", "$1.29", ppm="$0.09/oz"
)
CATALOG = {
    "01006": ("Canned Foods", CANNED),
    "04001": ("Soda & Pop", SODA),
    # SYNTHETIC child listings of Canned Foods (overlapping by five products), read when the site's search
    # cannot reach every result of the parent ("windowed" modes).
    "0100600001": ("Canned A", CANNED[:35]),
    "0100600002": ("Canned B", CANNED[30:]),
    "0100600009": ("Canned B (short)", CANNED[30:50]),
}


def _windowed_meta(mode: str, tax: str) -> dict[str, Any]:
    """availableCount and the category facet as the live search states them (2026-10-23), for the windowed
    modes: the parent reaches 24 of its 60 results; its children are small enough."""
    if mode not in ("windowed", "windowed_gap"):
        return {}
    if tax != "01006":
        return {"availableCount": 250}
    second = (
        ("0100600009", "canned-b-short", 20) if mode == "windowed_gap" else ("0100600002", "canned-b", 30)
    )
    return {
        "availableCount": PAGE,
        "facets": {
            "category": [
                {
                    "id": "01",
                    "name": "Pantry",
                    "count": 60,
                    "children": [
                        {
                            "id": "01006",
                            "name": "Canned Foods",
                            "count": 60,
                            "slug": "canned",
                            "children": [
                                {"id": "0100600001", "name": "Canned A", "count": 35, "slug": "canned-a"},
                                {"id": second[0], "name": "Canned B", "count": second[2], "slug": second[1]},
                            ],
                        }
                    ],
                }
            ]
        },
    }


def _grid_html(
    base: str,
    products: tuple[syn.Product, ...],
    start: int,
    *,
    sponsored: bool,
    ad_product: syn.Product = SPONSORED,
) -> str:
    cards = "".join(syn.grid_card(start + i, p, base) for i, p in enumerate(products))
    if sponsored:
        ad = syn.grid_card(900, ad_product, base).replace(
            '<div data-testid="product-image">', '<span>Sponsored</span><div data-testid="product-image">', 1
        )
        cards = ad + cards
    return cards


def make_handler(mode: str) -> type[BaseHTTPRequestHandler]:
    picker = syn.store_picker((OTHER,) if mode == "store_not_listed" else (OTHER, LAKESHORE))

    class H(BaseHTTPRequestHandler):
        hits: ClassVar[list[str]] = []

        def log_message(self, *a: object) -> None:
            pass

        def _send(self, status: int, body: str, ctype: str = "text/html") -> None:
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _context(self) -> tuple[str, str, str]:
            cookies = self.headers.get("Cookie", "")
            if "store=53100503" in cookies and "mod=IN_STORE" in cookies:
                return syn.state_script(), syn.header() + picker, "53100503"
            hdr = syn.header(
                modality_word="Pickup", name="Marianos Frankfort", address="21001 S La Grange Rd"
            )
            return syn.default_store_state(), hdr + picker, "53100509"

        def do_GET(self) -> None:
            H.hits.append(self.path)
            base = f"http://{self.headers['Host']}"
            parts = urlsplit(self.path)
            state, hdr, loc = self._context()
            if parts.path == "/robots.txt":
                self._send(200, "User-agent: *\nDisallow: /checkout\n", "text/plain")
            elif parts.path == "/":
                self._send(200, syn.page(hdr + "<main>home</main>", state=state))
            elif parts.path.startswith("/pl/"):
                tax = parts.path.rstrip("/").rsplit("/", 1)[-1]
                if mode == "refuse_second" and tax == "04001":
                    self._send(403, "<h1>Access Denied</h1>Reference #18.abc.123")
                    return
                title, products = CATALOG[tax]
                total = len(products)
                offset_param = "" if mode == "no_offset" else "&page.offset=' + o + '"
                more = (
                    '<div><button class="citrus-Button LoadMore__load-more-button" id="more" '
                    'onclick="loadMore()">Load More Results</button></div>'
                    if total > PAGE
                    else ""
                )
                ad_product = SPONSORED_OWN if mode == "sponsored_own" else SPONSORED
                shown = [p.upc for p in products[:PAGE]]
                # The live page also requests the data of its sponsored card's product.
                first = json.dumps(
                    [ad_product.upc, *shown] if mode == "sponsored_own" and tax == "01006" else shown
                )
                script = (
                    f"<script>const LOC='{loc}', TAX='{tax}', TOTAL={total}, SIZE={PAGE}; let offset=0;"
                    "function url(o){return '/atlas/v1/search/v1/products-search?filter.locationId=' + LOC"
                    f" + '&filter.taxonomies=' + TAX + '{offset_param}&page.size=' + SIZE;}}"
                    # As the live page: the shown products' data and coupons, by UPC.
                    "function q(name, upcs){return upcs.map(u => name + '=' + u).join('&');}"
                    "function details(upcs){"
                    "fetch('/atlas/v1/product/v2/products?' + q('filter.gtin13s', upcs));"
                    "fetch('/atlas/v1/savings-coupons/v2/coupons?' + q('filter.upc', upcs)"
                    " + '&filter.type=standard&filter.type=cash_back');}"
                    f"fetch(url(0)); details({first});"
                    "async function loadMore(){offset += SIZE;"
                    "const r = await fetch(url(offset) + '&o=' + offset); const j = await r.json();"
                    "document.getElementById('grid').insertAdjacentHTML('beforeend', j.html);"
                    "details(j.data.productsSearch.map(x => x.upc));"
                    "if (offset + SIZE >= TOTAL) document.getElementById('more').remove();}</script>"
                )
                # SYNTHETIC: a survey layer over the whole page once the store is selected; Escape does not
                # close it, so only a click through the page reaches the Load More button.
                overlay = (
                    '<div id="survey" style="position:fixed;inset:0;z-index:9999;'
                    'background:rgba(0,0,0,.2)">Tell us about your visit</div>'
                    if mode == "overlay" and loc == "53100503"
                    else ""
                )
                if mode == "captcha_overlay" and loc == "53100503":
                    # SYNTHETIC: a CAPTCHA layer that appears when the pointer reaches Load More (after the
                    # page was read and checked). The frame's tag is assembled in the script, so the page as
                    # first served carries no CAPTCHA markup.
                    overlay = (
                        "<script>document.addEventListener('mouseover',(e)=>{"
                        "if(!e.target.closest||!e.target.closest('#more')"
                        "||document.getElementById('cpt'))return;"
                        "const f='<if'+'rame title=\"h'+'captcha\" src=\"about:blank\"></if'+'rame>';"
                        "document.body.insertAdjacentHTML('beforeend','<div id=\"cpt\" style=\""
                        "position:fixed;inset:0;z-index:9999;background:#fff\">'+f+'</div>');});</script>"
                    )
                body = (
                    f"{overlay}{hdr}"
                    f'<div data-testid="SearchHeader"><h1 data-testid="SearchHeader-title">{title}</h1>'
                    f'<h2 data-testid="SearchHeader-heading">{total} results</h2></div>'
                    f'<div class="PaginateItems" data-testid="paginate-items"><div id="grid">'
                    f"{_grid_html(base, products[:PAGE], 0, sponsored=tax == '01006', ad_product=ad_product)}"
                    f"</div>{more}</div>" + script
                )
                self._send(200, syn.page(body, state=state))
            elif parts.path == "/atlas/v1/search/v1/products-search":
                q = parse_qs(parts.query)
                tax = q["filter.taxonomies"][0]
                offset = int((q.get("page.offset") or q.get("o") or ["0"])[0])
                _, products = CATALOG[tax]
                chunk = products[offset : offset + PAGE]
                body = {
                    "data": {"productsSearch": [{"upc": p.upc} for p in chunk]},
                    "meta": {
                        "productsSearch": {
                            "page": {"offset": offset, "size": PAGE},
                            "totalCount": len(products),
                            **_windowed_meta(mode, tax),
                        }
                    },
                    "html": _grid_html(base, chunk, offset, sponsored=False),
                }
                self._send(200, json.dumps(body), "application/json")
            elif parts.path == "/atlas/v1/product/v2/products":
                wanted = set(parse_qs(parts.query).get("filter.gtin13s", []))
                found = [_product_json(p, loc) for _, ps in CATALOG.values() for p in ps if p.upc in wanted]
                if mode == "sponsored_own" and SPONSORED_OWN.upc in wanted:
                    own = _product_json(SPONSORED_OWN, loc)
                    taxonomy = {"department": {"code": "01"}, "commodity": {"code": "006"}}
                    found.append({**own, "item": {**own["item"], "taxonomies": [taxonomy]}})
                self._send(200, json.dumps({"data": {"products": found}}), "application/json")
            elif parts.path == "/atlas/v1/savings-coupons/v2/coupons":
                wanted = set(parse_qs(parts.query).get("filter.upc", []))
                found = [c for c in COUPONS if wanted & set(c["upcs"])]
                self._send(200, json.dumps({"data": {"coupons": found}}), "application/json")
            else:
                self._send(404, "not found")

    return H


@pytest.fixture
def site(request: pytest.FixtureRequest) -> Iterator[tuple[str, type[BaseHTTPRequestHandler]]]:
    handler = make_handler(getattr(request, "param", "ok"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", handler
    srv.shutdown()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


def _chromium_path() -> str | None:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
        return path if Path(path).exists() else None
    except Exception:
        return None


CHROMIUM = _chromium_path()
requires_chromium = pytest.mark.skipif(CHROMIUM is None, reason="Playwright Chromium not installed")


@pytest.fixture
def cloud_browser() -> Iterator[str]:
    assert CHROMIUM is not None
    port = _free_port()
    proc = subprocess.Popen(
        [
            CHROMIUM,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={tempfile.mkdtemp()}",
            "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1).read()
                break
            except Exception:
                time.sleep(0.1)
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(10)


class FakeAccount:
    """Scrapfly's Account API (``GET /account``) for the tests: remaining credits as configured."""

    def __init__(self, remaining: int = 5000):
        self.remaining = remaining
        self.calls = 0

    def __call__(self, url: str, **kw: Any) -> Any:
        self.calls += 1
        assert kw["headers"]["Authorization"] == f"Bearer {KEY}"
        remaining = self.remaining

        class Resp:
            status_code = 200

            def json(self) -> Any:
                return {
                    "subscription": {
                        "plan_name": "TEST",
                        "period": {"start": "2026-10-19 00:00:00", "end": "2026-11-19 00:00:00"},
                        "usage": {
                            "scrape": {"limit": 10000, "current": 10000 - remaining, "remaining": remaining}
                        },
                        "extra_scrape_allowed": False,
                    },
                    "account": {"suspended": False},
                }

        return Resp()


def _settings(
    base: str, cdp: str, settings: Settings, entry_url: str | None = None, **scrapfly: Any
) -> Settings:
    acq = AcquisitionSettings(
        navigation_min_interval_s=1.0,
        navigation_interval_jitter_s=0.0,
        entry_url=entry_url,
        scrapfly=ScrapflyBrowserSettings(endpoint=cdp, target_url=base + "/", **scrapfly),
    )
    return Settings(acquisition=acq, records=settings.records, attestation=settings.attestation)


def _nodes(factory: sessionmaker[Session], base: str) -> list[Node]:
    with factory() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
    return [
        Node(7, "Grocery", ids[7], "Canned Foods", "01006", f"{base}/pl/canned-foods/01006?pzn=relevance"),
        Node(11, "Beverages", ids[11], "Soda & Pop", "04001", f"{base}/pl/soda-pop/04001?pzn=relevance"),
    ]


@pytest.fixture
def env(
    migrated_engine: Engine,
    tmp_path: Path,
    dev_store: StoreConfig,
    private_label: PrivateLabelConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    monkeypatch.setattr(LiveCollector, "LISTING_SETTLE_MS", 300)
    monkeypatch.setattr(LiveCollector, "STEP_SETTLE_MS", 200)
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": dev_store,
        "private_label": private_label,
        "tmp": tmp_path,
    }


def _run(
    env: dict[str, Any],
    base: str,
    cdp: str,
    settings: Settings,
    *,
    limits: Limits | None = None,
    account: FakeAccount | None = None,
    run_id: str | None = None,
    **scrapfly: Any,
) -> tuple[str, str, FakeAccount]:
    pipe = Pipeline(
        env["engine"],
        env["storage"],
        _settings(base, cdp, settings, **scrapfly),
        env["store"],
        env["private_label"],
    )
    cfg = CollectionConfig(limits=limits or Limits())
    if run_id is None:
        nodes = _nodes(env["factory"], base)
        with env["factory"]() as s:
            run_id = pipe.create_live_run(
                s,
                nodes,
                trigger="console",
                snapshot={
                    "plan": {"nodes": [n.as_dict() for n in nodes], "skipped": []},
                    "started_by": "test",
                },
            )
            s.commit()
        resume = False
    else:
        resume = True
    acct = account or FakeAccount()
    collector = LiveCollector(
        pipe, run_id, api_key=SecretStr(KEY), config=cfg, trigger="manual", account_get=acct
    )
    status = asyncio.run(pipe.execute(run_id, "test-collector", resume=resume, collector=collector))
    return run_id, status, acct


def _no_key_anywhere(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            assert KEY.encode() not in path.read_bytes(), path


@requires_chromium
def test_a_live_run_selects_the_store_pages_with_load_more_and_verifies_every_step(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, handler = site
    run_id, status, account = _run(env, base, cloud_browser, settings)
    assert status == "validated", status
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code is None and run.counts["collection_complete"] is True
        recs = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
        by_status = {st: sum(1 for r in recs if r.status == st) for st in {r.status for r in recs}}
        assert len(recs) == 70 and by_status == {"valid": 67, "excluded": 3}
        assert SPONSORED.upc not in {r.upc for r in recs}  # ads are not products of the listing
        verified = s.scalar(
            select(func.count(func.distinct(ProductObservation.upc))).where(
                ProductObservation.run_id == run_id, ProductObservation.provenance["verified"].as_boolean()
            )
        )
        assert verified == 67
        rec = next(r.record for r in recs if r.upc == CANNED[30].upc)
        assert set(rec) == set(OUTPUT_FIELDS)
        assert (rec["category"], rec["sub_category"], rec["store_name"], rec["zipcode"]) == (
            "Grocery",
            "Canned Foods",
            "Marianos Lakeshore East",
            "60601",
        )
        assert rec["ppm"] == CANNED[30].ppm and rec["url"].endswith(f"/p/{CANNED[30].slug}/{CANNED[30].upc}")
        # Offers: the coupon's "View Offer" terms and final price come from the page's own coupon response;
        # the multi-unit deal's validity from its product response; a pickup-only coupon stays out.
        by_upc = {r.upc: r.record for r in recs}
        coupon, volume, pickup = by_upc[CANNED[5].upc], by_upc[CANNED[6].upc], by_upc[CANNED[7].upc]
        assert coupon["digital_deals_description"] == (
            "Coupon: $1.99 Synthetic canned coupon — When You Buy ONE (1) Synthetic canned item. "
            "Limit 5 per transaction. (Exp. 10/20/2026)"
        )
        assert coupon["digital_deals_price"] == "1.99" and coupon["volume_deals_description"] == ""
        assert (volume["volume_deals_description"], volume["volume_deals_price"]) == (
            "2 For $5.00 (Exp. 10/20/2026)",
            "5.00",
        )
        assert pickup["digital_deals_description"] == pickup["digital_deals_price"] == ""
        assert not any("View Offer" in v for r in recs for v in r.record.values())
        kinds = {
            k for (k,) in s.execute(select(CapturedResponse.kind).where(CapturedResponse.run_id == run_id))
        }
        assert {"products_search", "products_v2", "coupons"} <= kinds
        obs = {
            o.upc: o for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }
        # Every product's store and fulfillment are confirmed by the site's own product response (the
        # responses of the default store, before the store was selected, are never read).
        assert {o.provenance["source_check"]["result"] for o in obs.values()} == {"PASS"}
        fetches = sorted(
            s.scalars(select(PageFetch).where(PageFetch.run_id == run_id)), key=lambda f: f.started_at
        )
        confirmed = next(f.started_at for f in fetches if f.purpose == "confirm_store")
        before_selection = {f.id for f in fetches if f.started_at < confirmed}
        used = {o.provenance["source_check"]["response"]["fetch_id"] for o in obs.values()}
        assert used and not used & before_selection
        assert any(
            "PICKUP OR DELIVERY ONLY" in n
            for n in obs[CANNED[7].upc].provenance["fields"]["_offers_left_out"]["notes"]
        )
        empty = [f for f, v in rec.items() if not v]
        assert set(obs[CANNED[30].upc].provenance["missing"]) == set(empty)
        assert obs[CANNED[30].upc].provenance["segment"] is not None
        log = supporting_log(s, run_id)
        assert log["counts"]["observed"] == {
            "fresh": 70,
            "fresh_earlier_segment": 0,
            "carried_forward": 0,  # from an earlier run: none (this store's first run)
            "not_recorded": 0,
        }
        cov = {c.taxonomy_id: c for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))}
        assert (cov["01006"].status, cov["01006"].total_count, cov["01006"].organic_upcs) == ("DONE", 60, 60)
        assert (cov["04001"].status, cov["04001"].coverage_ratio) == ("DONE", 1.0)
        purposes = [
            p for (p,) in s.execute(select(PageFetch.purpose).where(PageFetch.run_id == run_id)).all()
        ]
        assert purposes.count("load_more") == 2 and "confirm_store" in purposes and "robots" in purposes
        atts = list(s.scalars(select(StoreAttestation).where(StoreAttestation.run_id == run_id)))
        assert {a.phase for a in atts} >= {"preflight", "task_start", "periodic", "final"}
        assert all(a.result == "PASS" for a in atts)
        (seg,) = s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        assert seg.ended_at is not None and seg.browser_sessions == seg.browsers_closed == 1
        assert seg.products_verified == 67 and seg.account_remaining_start == 5000
        codes = [c for (c,) in s.execute(select(Event.code).where(Event.run_id == run_id)).all()]
        assert "BROWSER_CLOSED" in codes and "STORE_VERIFIED" in codes and codes.count("PAGE_COLLECTED") == 4
    assert account.calls == 2  # once when the segment starts, once when it ends
    searches = [h for h in handler.hits if "products-search" in h]
    assert any("page.offset=24" in h for h in searches) and any("page.offset=48" in h for h in searches)
    _no_key_anywhere(env["tmp"])


@requires_chromium
def test_a_product_limit_stops_inside_a_page_and_a_resume_continues_without_counting_twice(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, _ = site
    run_id, status, _ = _run(env, base, cloud_browser, settings, limits=Limits(max_products_per_run=30))
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert (
            run is not None
            and run.stop_code == "RUN_PRODUCT_LIMIT"
            and "30 verified" in (run.stop_detail or "")
        )
        valid = s.scalar(
            select(func.count())
            .select_from(RecordRow)
            .where(RecordRow.run_id == run_id, RecordRow.status == "valid")
        )
        assert valid == 30  # exactly the limit, never more
        (seg,) = s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        assert seg.stop_code == "RUN_PRODUCT_LIMIT" and seg.browsers_closed == seg.browser_sessions == 1
    # The administrator raises the limit and resumes: the run continues from its checkpoint.
    _, status, _ = _run(env, base, cloud_browser, settings, run_id=run_id)
    assert status == "validated", status
    with env["factory"]() as s:
        recs = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
        assert len(recs) == 70 and len({r.upc for r in recs}) == 70
        assert sum(r.status == "valid" for r in recs) == 67
        segs = list(s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run_id)))
        assert len(segs) == 2 and all(x.browsers_closed == x.browser_sessions for x in segs)
        assert sum(x.products_verified for x in segs) == 67  # repeated clicks after the resume count nothing
        # The products the first segment saw are carried forward as observed then, not observed again.
        first = min(segs, key=lambda x: x.started_at).id
        seen_first = s.scalar(
            select(func.count())
            .select_from(ProductObservation)
            .where(
                ProductObservation.run_id == run_id, ProductObservation.provenance["segment"].astext == first
            )
        )
        log = supporting_log(s, run_id)
        assert seen_first and log["counts"]["observed"] == {
            "fresh": 70 - seen_first,
            "fresh_earlier_segment": seen_first,  # observed by the first segment of this same run
            "carried_forward": 0,  # from an earlier run: none
            "not_recorded": 0,
        }
        carried = [u for u, r in log["records"].items() if r["observation"]["earlier_segment"]]
        assert len(carried) == seen_first and all(
            log["records"][u]["observation"]["segment"] == first for u in carried
        )


@requires_chromium
def test_the_credit_budget_stops_the_run_and_closes_the_browser(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, _ = site
    # An inflated bandwidth rate makes the first responses cost more than the run's budget.
    run_id, status, _ = _run(
        env,
        base,
        cloud_browser,
        settings,
        limits=Limits(max_credits_per_run=100),
        credits_per_mb_residential=10_000_000,
    )
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "RUN_CREDIT_LIMIT"
        (seg,) = s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        assert seg.credits_estimated > 100 and seg.browsers_closed == seg.browser_sessions == 1
        assert s.scalar(select(func.count()).select_from(RecordRow).where(RecordRow.run_id == run_id)) == 0


@requires_chromium
def test_the_account_reserve_is_kept(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, _ = site
    run_id, status, account = _run(
        env, base, cloud_browser, settings, limits=Limits(min_credit_reserve=500), account=FakeAccount(520)
    )
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert (
            run is not None and run.stop_code == "CREDIT_RESERVE" and "reserve 500" in (run.stop_detail or "")
        )
        segs = list(s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run_id)))
        assert len(segs) == 1 and segs[0].browser_sessions == 0  # no cloud browser was opened at all
    assert account.calls == 2


@requires_chromium
@pytest.mark.parametrize("site", ["refuse_second"], indirect=True)
def test_a_refusal_stops_the_run_keeps_what_was_verified_and_closes_the_browser(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, handler = site
    run_id, status, _ = _run(env, base, cloud_browser, settings)
    assert status == "rejected"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "SITE_REFUSAL"
        assert s.scalar(select(func.count()).select_from(RecordRow).where(RecordRow.run_id == run_id)) == 60
        (seg,) = s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        assert seg.browsers_closed == seg.browser_sessions == 1
    assert len([h for h in handler.hits if h.startswith("/pl/soda")]) == 1  # never retried


@requires_chromium
@pytest.mark.parametrize("site", ["store_not_listed"], indirect=True)
def test_a_store_the_picker_cannot_select_stops_before_any_product(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, _ = site
    run_id, status, _ = _run(env, base, cloud_browser, settings)
    assert status == "rejected"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "STORE_NOT_VERIFIED"
        assert s.scalar(select(func.count()).select_from(RecordRow).where(RecordRow.run_id == run_id)) == 0


@requires_chromium
@pytest.mark.parametrize("site", ["no_offset"], indirect=True)
def test_a_load_more_step_without_paging_evidence_is_not_counted(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, _ = site
    run_id, status, _ = _run(env, base, cloud_browser, settings)
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.counts["collection_complete"] is False
        cov = {c.taxonomy_id: c for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))}
        assert cov["01006"].status == "INCOMPLETE" and cov["01006"].organic_upcs == 24
        assert cov["04001"].status == "DONE"
        assert s.scalar(select(func.count()).select_from(RecordRow).where(RecordRow.run_id == run_id)) == 34
    assert status == "rejected"  # coverage below the threshold: never reported as complete


@requires_chromium
@pytest.mark.parametrize("site", ["overlay"], indirect=True)
def test_a_layer_over_the_load_more_button_does_not_lose_the_listing(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    """SYNTHETIC: a layer covers the page after the store is selected; the plain click times out, Escape does
    not close it, and the step clicks the button through the page: the listing is read to its end and the
    step says how the button was clicked."""
    base, _ = site
    run_id, status, _ = _run(env, base, cloud_browser, settings)
    assert status in ("validated", "rejected")
    with env["factory"]() as s:
        cov = {c.taxonomy_id: c for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))}
        assert cov["01006"].status == "DONE" and cov["01006"].organic_upcs == len(CANNED)
        steps = [
            e.data
            for e in s.scalars(select(Event).where(Event.run_id == run_id, Event.code == "PAGE_COLLECTED"))
            if e.data.get("node") == "01006" and e.data.get("step", 0) > 0
        ]
    assert steps and all(d["click_via"] == "dom_click" and len(d["click_problems"]) == 2 for d in steps)


@requires_chromium
@pytest.mark.parametrize("site", ["captcha_overlay"], indirect=True)
def test_a_challenge_over_the_load_more_button_stops_the_run_and_is_never_clicked_through(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    """SYNTHETIC: a CAPTCHA layer covers the page when the pointer reaches Load More: no click through it;
    the run stops as a refusal with the page copy kept."""
    base, _ = site
    run_id, status, _ = _run(env, base, cloud_browser, settings)
    assert status == "rejected"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "SITE_REFUSAL"
        steps = [
            e.data
            for e in s.scalars(select(Event).where(Event.run_id == run_id, Event.code == "PAGE_COLLECTED"))
            if e.data.get("node") == "01006"
        ]
        challenged = list(s.scalars(select(PageFetch).where(PageFetch.run_id == run_id, PageFetch.challenge)))
    assert [d["step"] for d in steps] == [0]  # nothing after the covered button
    assert not any(d.get("click_via") == "dom_click" for d in steps)
    assert challenged and challenged[-1].purpose == "load_more"


@requires_chromium
@pytest.mark.parametrize("site", ["windowed"], indirect=True)
def test_a_listing_beyond_the_result_window_is_read_through_its_child_listings(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    """SYNTHETIC: Canned Foods reports 60 results, its search reaches 24; the site's category facet names two
    overlapping child listings (35 and 30 products). The first page is kept, both children are read, products
    are recorded once, and the listing is complete because the distinct products reach its 60 results."""
    base, _ = site
    run_id, status, _ = _run(env, base, cloud_browser, settings)
    assert status == "validated", status
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.counts["collection_complete"] is True
        recs = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
        assert len(recs) == len({r.upc for r in recs}) == 70  # 60 canned (once each) and 10 sodas
        cov = {c.taxonomy_id: c for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))}
        assert cov["01006"].status == "PARTITIONED" and cov["01006"].total_count == 60
        parts = cov["01006"].partition["partitions"]
        assert [x["id"] for x in parts] == ["0100600001", "0100600002"] and all(x["task"] for x in parts)
        assert cov["0100600001"].status == cov["0100600002"].status == "DONE"
        assert cov["0100600001"].partition["parent"] == "01006"
        events = [e.code for e in s.scalars(select(Event).where(Event.run_id == run_id))]
    assert events.count("LISTING_PARTITIONED") == 1


@requires_chromium
@pytest.mark.parametrize("site", ["windowed_gap"], indirect=True)
def test_child_listings_that_do_not_cover_the_listing_leave_it_incomplete(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    """SYNTHETIC: the children reach only 50 of the 60 results: the listing stays INCOMPLETE with the gap and
    the run is never reported complete (a sum of child counts would have hidden nothing here either)."""
    base, _ = site
    run_id, status, _ = _run(env, base, cloud_browser, settings)
    assert status == "rejected"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.counts["collection_complete"] is False
        assert run.counts["nodes"].get("INCOMPLETE", 0) >= 1
        recs = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
        assert len({r.upc for r in recs if r.upc.startswith("0009100")}) == 50


@requires_chromium
@pytest.mark.parametrize("site", ["windowed"], indirect=True)
def test_a_product_read_through_a_child_listing_is_carried_forward_under_its_listing(
    site: tuple[str, type],
    cloud_browser: str,
    env: dict[str, Any],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SYNTHETIC: the first run reads Canned Foods through its child listings; the next run finds it small
    enough to read directly (20 products) and to its end. The products the children showed are carried forward
    under Canned Foods, read to its end (not as "its listing … was not read"), with the child named."""
    base, _ = site
    first, status, _ = _run(env, base, cloud_browser, settings)
    assert status == "validated", status
    monkeypatch.setitem(CATALOG, "01006", ("Canned Foods", CANNED[:20]))
    second, _, _ = _run(env, base, cloud_browser, settings)
    with env["factory"]() as s:
        cov = {
            c.taxonomy_id: c.status
            for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == second))
        }
        assert cov["01006"] == "DONE" and "0100600001" not in cov  # read directly this time
        first_seen = {
            o.upc: o.provenance
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == first))
        }
        carried = {
            r.upc: r.provenance["historical"]
            for r in s.scalars(
                select(RecordRow).where(RecordRow.run_id == second, RecordRow.status == "historical")
            )
        }
    via_child = {u for u, p in first_seen.items() if p.get("parent") == "01006"}
    assert via_child and via_child <= {p.upc for p in CANNED[24:]}  # the children's own products
    shown = {p.upc for p in CANNED[:20]}
    for upc in via_child & carried.keys():
        h = carried[upc]
        assert upc not in shown and h["listing"] == "01006", (upc, h)
        assert h["read_through"] == first_seen[upc]["node"]
        assert h["why_not_observed"].startswith("not shown by its listing 01006, read to its end"), h
    assert via_child & carried.keys()


@requires_chromium
def test_the_page_step_limit_stops_a_listing_after_its_first_step(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, handler = site
    run_id, status, _ = _run(env, base, cloud_browser, settings, limits=Limits(max_pages_per_listing=1))
    assert status in ("validated", "rejected")
    with env["factory"]() as s:
        canned = s.scalar(
            select(func.count())
            .select_from(RecordRow)
            .where(
                RecordRow.run_id == run_id,
                RecordRow.primary_category_source_id == _nodes(env["factory"], base)[0].category_source_id,
            )
        )
        cov = {c.taxonomy_id: c for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))}
    assert canned is not None and 0 < canned <= PAGE  # the first step's cards only, of 60
    assert not any("page.offset=24" in h for h in handler.hits)  # "Load More" was never pressed
    assert cov["01006"].status == "INCOMPLETE"


@requires_chromium
def test_an_entry_page_is_opened_first_and_the_session_record_is_kept(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    base, handler = site
    run_id, status, _ = _run(
        env, base, cloud_browser, settings, limits=Limits(max_products_per_run=5), entry_url=base + "/"
    )
    assert status in ("interrupted", "validated", "rejected")
    with env["factory"]() as s:
        purposes = [
            f.purpose
            for f in s.scalars(
                select(PageFetch).where(PageFetch.run_id == run_id).order_by(PageFetch.started_at)
            )
        ]
        codes = list(s.scalars(select(Event.code).where(Event.run_id == run_id)))
    assert purposes[:2] == ["robots", "entry_page"] and "listing" in purposes
    assert "/" in handler.hits
    # The browser session's own record (its start with the user agent, its close with the cost) is kept.
    assert "SESSION_BROWSER_STARTED" in codes and "SESSION_BROWSER_CLOSED" in codes


def _short_lease(monkeypatch: pytest.MonkeyPatch, keepalive_s: float) -> None:
    from marianos_headless.collection import live
    from marianos_headless.worker import runner

    monkeypatch.setattr(runner.Worker.__init__, "__kwdefaults__", {"lease_s": 2.0})
    monkeypatch.setattr(live, "KEEPALIVE_S", keepalive_s)


@requires_chromium
def test_a_store_selection_longer_than_the_lease_keeps_the_task(
    site: tuple[str, type],
    cloud_browser: str,
    env: dict[str, Any],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live 2026-10-22: the picker's steps took longer than the task's lease and the run stopped. The
    lease is now renewed while the handler works."""
    base, _ = site
    _short_lease(monkeypatch, keepalive_s=0.3)
    run_id, status, _ = _run(env, base, cloud_browser, settings, limits=Limits(max_products_per_run=20))
    with env["factory"]() as s:
        codes = list(s.scalars(select(Event.code).where(Event.run_id == run_id)))
        run = s.get(Run, run_id)
    assert "TASK_LEASE_LOST" not in codes and "STORE_VERIFIED" in codes
    assert run is not None and run.stop_code == "RUN_PRODUCT_LIMIT", (status, run.stop_code if run else None)


@requires_chromium
def test_a_preflight_taken_over_after_its_lease_verifies_the_store_again(
    site: tuple[str, type],
    cloud_browser: str,
    env: dict[str, Any],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second fault of 2026-10-22: the task taken over found the store selected in the session but no
    verified page, and stopped with a wrong reason. It now opens the page again and verifies it."""
    base, _ = site
    _short_lease(monkeypatch, keepalive_s=1000.0)  # no renewal: the lease runs out during the selection
    run_id, status, _ = _run(env, base, cloud_browser, settings, limits=Limits(max_products_per_run=20))
    with env["factory"]() as s:
        codes = list(s.scalars(select(Event.code).where(Event.run_id == run_id)))
        run = s.get(Run, run_id)
    assert "TASK_LEASE_LOST" in codes and "TASK_LEASE_RECLAIMED" in codes  # the incident is reproduced
    assert run is not None and run.stop_code != "NOTHING_TO_COLLECT", codes
    assert "STORE_VERIFIED" in codes and run.stop_code == "RUN_PRODUCT_LIMIT", (
        status,
        run.stop_code,
        codes[-12:],
    )


@requires_chromium
@pytest.mark.parametrize("site", ["sponsored_own"], indirect=True)
def test_a_product_shown_only_as_sponsored_is_recorded_when_its_data_places_it_in_the_listing(
    site: tuple[str, type], cloud_browser: str, env: dict[str, Any], settings: Settings
) -> None:
    """SYNTHETIC (release 1.5.0): the "Sponsored" label neither excludes a product of the listing nor makes
    it a promotion. Shown only as a sponsored card, with product data naming the listing, it is recorded once
    and its placement is kept as sponsored; until 1.4.0 the Scrapfly path skipped every sponsored card."""
    base, _ = site
    run_id, status, _ = _run(env, base, cloud_browser, settings)
    assert status == "validated", status
    with env["factory"]() as s:
        recs = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        assert len(recs) == 71 and SPONSORED.upc not in recs
        own = recs[SPONSORED_OWN.upc]
        assert own.status == "valid", (own.status, own.reasons)
        assert own.record["regular_price"] == "1.29" and own.record["sub_category"] == "Canned Foods"
        deal_fields = ("volume_deals_description", "digital_deals_description", "sale_price")
        assert all(own.record[f] == "" for f in deal_fields)  # the label is not a promotion
        placements = list(
            s.execute(
                select(MembershipRow.placement, MembershipRow.via).where(
                    MembershipRow.run_id == run_id, MembershipRow.upc == SPONSORED_OWN.upc
                )
            ).all()
        )
        assert placements == [("sponsored", "paid")]
        # One placement per product, listing and kind: a card still on the page at a later Load More step
        # adds no row (until 1.4.0 the Scrapfly path wrote one per step).
        rows = list(
            s.execute(
                select(MembershipRow.upc, MembershipRow.taxonomy_id, MembershipRow.placement).where(
                    MembershipRow.run_id == run_id
                )
            ).all()
        )
        assert len(rows) == len(set(rows)) == 71  # 70 organic and the sponsored card
