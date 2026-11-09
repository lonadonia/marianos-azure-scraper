"""Release 1.9.0 (M4): the Oxylabs collector reads the product's own page for each card that shows a digital
coupon, once per product and run, before the step's records are built.

A fake Web API (an httpx mock transport, nothing leaves the process) serves SYNTHETIC search pages for the
Vernon Hills store (53100502, PICKUP) and, for product pages, the REAL pages saved by stage O1 on 2026-11-06
(``tests/fixtures/oxylabs_2026-11-06``): one the provider rendered (its coupons shown) and one it did not."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, select

from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    CoverageSettings,
    OxylabsSettings,
    PrivateLabelConfig,
    Settings,
    load_stores,
)
from marianos_headless.db.models import CapturedResponse as CapturedRow
from marianos_headless.db.models import Event, ProductObservation, RecordRow
from marianos_headless.db.models import PageFetch as PageFetchRow
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests import synthetic_marianos as syn
from tests.integration.helpers import seed
from tests.integration.test_oxylabs_collector import (
    BASE,
    CEREAL_TAX,
    KEY,
    ROBOTS,
    _ceiling,
    _no_sleep,
    _nodes,
)

pytestmark = [pytest.mark.postgres]

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "oxylabs_2026-11-06"
VH = {
    "location_id": "53100502",
    "modality": "PICKUP",
    "store_name": "Marianos Vernon Hills",
    "store_address": "1720 N Milwaukee Ave",
    "store_postal": "60061",
}
# The four M4 products as cards of a synthetic search page (their zones as Q2 saw them), and one without.
PURINA = syn.Product(
    "0001780014939",
    "natural-dog-food-chicken-and-rice-formula-dry-dog-food-for-digestive-and-gut-health-support",
    "Natural Dog Food, Chicken and Rice Formula",
    "31.1 lb.",
    "$54.99",
    zone="Save $10.00 on 2 Purina ONE",
    clip=True,
)
LAMB = syn.Product(
    "0001780014941",
    "one-natural-dog-food-lamb-and-rice-formula-dry-dog-food-for-digestive-and-gut-health-support",
    "ONE Natural Dog Food, Lamb and Rice Formula",
    "31.1 lb.",
    "$54.99",
    zone="Save $10.00 on 2 Purina ONE",
    clip=True,
)
ENERGIZER = syn.Product(
    "0003980014995",
    "energizer-ultimate-child-shield-2032-3v-lithium-coin-batteries",
    "Energizer Ultimate Child Shield 2032",
    "10 Count",
    "$19.99",
    original="$21.99",
    zone="Save $1.00 on Energizer",
    clip=True,
)
TEMPTATIONS = syn.Product(
    "0002310014848",
    "temptations-birthday-adult-crunchy-and-soft-cat-treats-lobster-and-beef",
    "Temptations Birthday Cat Treats",
    "16 oz",
    "$8.99",
    original="$9.49",
    zone="$6.99 Temptations Cat Treats",
    clip=True,
)
PLAIN = syn.Product("0001600012254", "cheerios", "Cheerios Cereal", "8.9 oz", "$4.99", ppm="$0.56/oz")
PRODUCT_PAGES = {
    PURINA.upc: ("pdp_0001780014939_rendered.html.gz", True),
    LAMB.upc: ("pdp_0001780014941_unrendered.html.gz", False),
}


class FakeTermsApi:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, **body})
        n = len(self.requests)
        url = body.get("url", "")
        meta: dict[str, Any] = {"status_code": 200}
        if url.endswith("/robots.txt"):
            assert "store_id" not in body
            html = ROBOTS
        else:
            assert body["store_id"] == "53100502" and body["fulfillment_type"] == "pickup"
            if request.url.path == "/v1/scrape/marianos/search":
                products = (
                    (
                        (PURINA, CEREAL_TAX),
                        (LAMB, CEREAL_TAX),
                        (ENERGIZER, CEREAL_TAX),
                        (TEMPTATIONS, CEREAL_TAX),
                    )
                    if body["query"] == "Cereal & Granola"
                    else ((PLAIN, "0300200001"),)
                )
                html = syn.search_page(BASE, products, query=body["query"], total=len(products), **VH)
            elif "/savings/cl/coupons" in url:
                html = syn.coupons_page(1)
            elif "/p/" in url:
                assert body.get("run_js") is True
                upc = url.rsplit("/", 1)[-1]
                if upc not in PRODUCT_PAGES:
                    return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
                name, rendered = PRODUCT_PAGES[upc]
                html = gzip.decompress((FIX / name).read_bytes()).decode("utf-8")
                meta = {
                    "page": 1,
                    "run_js": rendered,
                    "url": url,
                    "statuses": {"http_request": {"code": 200}},
                }
            else:
                return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
        return httpx.Response(
            200,
            json={
                "status": "done",
                "results": [{"html": html, "metadata": meta}],
                "metadata": {"request_id": f"req-{n}", "timestamp": "2026-11-06T18:30:00Z"},
            },
        )


@pytest.fixture
def vh_env(migrated_engine: Engine, tmp_path: Path, private_label: PrivateLabelConfig) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    store = next(
        s for s in load_stores(ROOT / "config" / "stores.yaml").stores if s.key == "marianos-53100502-pickup"
    )
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": store,
        "private_label": private_label,
        "tmp": tmp_path,
    }


def _run(env: dict[str, Any], settings: Settings, fake: FakeTermsApi, *, read: bool, limits: Limits) -> str:
    acq = AcquisitionSettings(
        browser_provider=BrowserProvider.OXYLABS, oxylabs=OxylabsSettings(listing_route="search")
    )
    pipe = Pipeline(
        env["engine"],
        env["storage"],
        Settings(
            acquisition=acq,
            records=settings.records,
            attestation=settings.attestation,
            coverage=CoverageSettings(read_product_terms=read),
        ),
        env["store"],
        env["private_label"],
    )
    nodes = _nodes(env["factory"])
    with env["factory"]() as s:
        run_id = pipe.create_live_run(
            s,
            nodes,
            trigger="console",
            snapshot={
                "plan": {"nodes": [n.as_dict() for n in nodes], "skipped": []},
                "started_by": "test",
                "provider": "oxylabs",
            },
        )
        s.commit()
    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(fake),
        sleep=_no_sleep,
        config=CollectionConfig(limits=limits),
        trigger="manual",
    )
    asyncio.run(pipe.execute(run_id, "test-collector", resume=False, collector=collector))
    return run_id


def _product_pages(fake: FakeTermsApi) -> list[str]:
    return [r["url"].rsplit("/", 1)[-1] for r in fake.requests if "/p/" in r.get("url", "")]


def test_each_coupon_card_gets_one_bounded_read_of_its_own_page(
    vh_env: dict[str, Any], settings: Settings
) -> None:
    _ceiling(vh_env["factory"], 20)
    fake = FakeTermsApi()
    run_id = _run(vh_env, settings, fake, read=True, limits=Limits(max_product_term_reads=3))
    # Only coupon cards, in page order, once each, within the limit; the plain card's page is never read.
    assert _product_pages(fake) == [PURINA.upc, LAMB.upc, ENERGIZER.upc]
    with vh_env["factory"]() as s:
        obs = {
            o.upc: o.provenance
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }
        recs = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        terms = {u: p.get("coupon_terms", {}).get("status") for u, p in obs.items()}
        assert terms == {
            PURINA.upc: "read",
            LAMB.upc: "unread_not_rendered",
            ENERGIZER.upc: "request_failed",
            TEMPTATIONS.upc: "unread_limit",
            PLAIN.upc: None,
        }
        purina = recs[PURINA.upc]
        assert purina.record["digital_deals_description"].startswith(
            "Coupon: Save $10.00 on 2 Purina ONE — Save $10.00 on any TWO (2) Purina ONE Dry Dog Food bags"
        )
        assert purina.record["digital_deals_description"].endswith("(Exp. Nov. 10; Sign In To Clip)")
        assert purina.record["digital_deals_price"] == "" and "DIGITAL_TERMS_UNREAD" not in purina.flags
        coupons = obs[PURINA.upc]["coupon_terms"]
        assert coupons["coupon_ids"] == ["4257015", "4257014"] and coupons["rendered"] is True
        assert coupons["request_id"] and coupons["fetch_id"]
        for upc in (LAMB.upc, ENERGIZER.upc, TEMPTATIONS.upc):
            assert "DIGITAL_TERMS_UNREAD" in recs[upc].flags, upc
            assert recs[upc].record["digital_deals_price"] == "", upc
        assert "run_js False" in obs[LAMB.upc]["coupon_terms"]["reason"]
        # The product pages are kept as captures (the page and its Savings section), with the provider's
        # statement of rendering in the page event.
        pages = list(
            s.scalars(
                select(PageFetchRow).where(
                    PageFetchRow.run_id == run_id, PageFetchRow.purpose == "product_terms"
                )
            )
        )
        # Three reads: two brought a page, the failed one keeps its row without a page.
        assert len(pages) == 3 and sum(p.dom_artifact_id is not None for p in pages) == 2
        kinds = list(
            s.scalars(
                select(CapturedRow.kind).where(
                    CapturedRow.run_id == run_id, CapturedRow.kind == "pdp_savings"
                )
            )
        )
        assert len(kinds) == 2
        captured = [
            json.loads(e.data) if isinstance(e.data, str) else e.data
            for e in s.scalars(select(Event).where(Event.run_id == run_id, Event.code == "PAGE_CAPTURED"))
        ]
        assert sorted(str(d.get("rendered")) for d in captured if "/p/" in json.dumps(d)) in (
            [],
            ["False", "True"],
        )


def test_without_the_setting_no_product_page_is_read(vh_env: dict[str, Any], settings: Settings) -> None:
    _ceiling(vh_env["factory"], 20)
    fake = FakeTermsApi()
    run_id = _run(vh_env, settings, fake, read=False, limits=Limits())
    assert _product_pages(fake) == []
    with vh_env["factory"]() as s:
        recs = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        assert all(
            "DIGITAL_TERMS_UNREAD" in recs[p.upc].flags for p in (PURINA, LAMB, ENERGIZER, TEMPTATIONS)
        )
        assert recs[TEMPTATIONS.upc].record["digital_deals_price"] == ""


def test_a_zero_limit_reads_no_page_and_says_why(vh_env: dict[str, Any], settings: Settings) -> None:
    _ceiling(vh_env["factory"], 20)
    fake = FakeTermsApi()
    run_id = _run(vh_env, settings, fake, read=True, limits=Limits(max_product_term_reads=0))
    assert _product_pages(fake) == []
    with vh_env["factory"]() as s:
        obs = [
            o.provenance
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        ]
        assert {o["coupon_terms"]["status"] for o in obs if "coupon_terms" in o} == {"unread_limit"}


def test_the_spending_ceiling_stops_term_reads_without_losing_the_page(
    vh_env: dict[str, Any], settings: Settings
) -> None:
    # robots.txt, the first search page, the Coupons page and one product page: the next product page meets
    # the ceiling.
    _ceiling(vh_env["factory"], 4)
    fake = FakeTermsApi()
    run_id = _run(vh_env, settings, fake, read=True, limits=Limits())
    assert _product_pages(fake) == [PURINA.upc]
    with vh_env["factory"]() as s:
        obs = {
            o.upc: o.provenance
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }
        assert obs[PURINA.upc]["coupon_terms"]["status"] == "read"
        assert {obs[u]["coupon_terms"]["status"] for u in (LAMB.upc, ENERGIZER.upc, TEMPTATIONS.upc)} == {
            "unread_ceiling"
        }
