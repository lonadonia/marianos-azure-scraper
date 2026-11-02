"""The Oxylabs Web API collector end to end (release 1.3.0): a fake Oxylabs API (an httpx mock transport,
nothing leaves the process) serves SYNTHETIC search pages shaped like the probe pages of 2026-10-28 (the
store and fulfillment as request parameters, the products and the search in the page state), robots.txt and
the Coupons page. The run goes through the same pipeline, records, checks and exports as a browser run."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection import oxylabs_live
from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    OxylabsSettings,
    PrivateLabelConfig,
    Settings,
    StoreConfig,
)
from marianos_headless.db.models import (
    CategorySource,
    CollectionSegment,
    Event,
    ListingPage,
    NodeCoverage,
    ProductObservation,
    ProviderUsage,
    RecordRow,
    Run,
    StoreAttestation,
)
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests import synthetic_marianos as syn
from tests.integration.helpers import seed

pytestmark = [pytest.mark.postgres]

KEY = "oxy-test-key-never-sent-0123456789abcdef"
BASE = "https://www.marianos.com"
CEREAL_TAX, BARS_TAX, CANNED_TAX = "0300100001", "0300200001", "0100600001"
ROBOTS = "User-agent: *\nDisallow: /checkout$\nDisallow: /locations*\n"

CEREAL = (
    syn.Product("0001600012254", "cheerios", "Cheerios Cereal", "8.9 oz", "$4.99", ppm="$0.56/oz"),
    syn.Product(
        "0003800019828", "honey-smacks", "Honey Smacks", "15.3 oz", "$5.49", original="$8.79", ppm="$0.36/oz"
    ),
    syn.Product(
        "0001600027532", "lucky", "Lucky Charms", "10.5 oz", "$4.79", zone="2 For $8.00", ppm="$0.46/oz"
    ),
    syn.Product("0088491212971", "sponsored-granola", "Sponsored Granola", "11 oz", "$6.29", ppm="$0.57/oz"),
    syn.Product("0020000000000", "bulk-oats", "Bulk Oats", "about 1 lb", "$2.99"),  # approximate weight
)
BAR_ON_CEREAL = syn.Product("0003000057322", "quaker-bar", "Quaker Chewy Bar", "8 ct", "$3.49")
CANNED = syn.Product("0002400016725", "del-monte-corn", "Del Monte Corn", "15.25 oz", "$1.29")
UNPRICED = syn.Product("0001111001885", "poultry-herb-blend", "Poultry Herb Blend", "0.5 oz", "")
BARS = (
    syn.Product("0003800035902", "nutri-grain", "Nutri-Grain Bars", "8 ct", "$4.29"),
    syn.Product("0003800040005", "pop-tarts", "Pop-Tarts", "8 ct", "$3.99", ppm="$0.29/oz"),
    BAR_ON_CEREAL,
)


class FakeOxylabs:
    """The Web API's Mariano's scrapers: ``/v1/scrape/marianos`` (url) and ``/v1/scrape/marianos/search``."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.requests: list[dict[str, Any]] = []

    def _page(self, query: str) -> str:
        if query == "Cereal & Granola":
            products = (
                *((p, CEREAL_TAX) for p in CEREAL),
                (BAR_ON_CEREAL, BARS_TAX),
                (CANNED, CANNED_TAX),
            )
            if self.mode == "unpriced":  # one product out of stock: no price shown or stated
                products = (*products, (UNPRICED, CEREAL_TAX))
            kw: dict[str, Any] = {}
            if self.mode == "price_elsewhere":
                kw["price_location"] = {CEREAL[0].upc: "53100511"}
            if self.mode == "default_store":
                kw["source"] = "DEFAULT_MODALITY_ADDRESS"
            return syn.search_page(BASE, products, query=query, total=431, sponsored=(CEREAL[3].upc,), **kw)
        if self.mode == "empty_bars":  # the search found nothing at the store
            return syn.search_page(BASE, (), query=query, total=0)
        if self.mode == "unread_bars":  # the store's page, no product shown, yet the search reports results
            return syn.search_page(BASE, (), query=query, total=5)
        return syn.search_page(BASE, tuple((p, BARS_TAX) for p in BARS), query=query, total=3)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, **body})
        assert body["output"] == ["html"]
        if body.get("url", "").endswith("/robots.txt"):
            # Not a store page: with store parameters the live scraper fails it (2026-10-29).
            if "store_id" in body or "fulfillment_type" in body:
                return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
        else:
            assert body["store_id"] == "53100503" and body["fulfillment_type"] == "in_store"
        n = len(self.requests)
        if self.mode == "auth":
            return httpx.Response(401, json={"title": "Unauthorized"})
        if request.url.path == "/v1/scrape/marianos/search":
            if self.mode == "fail_bars" and body["query"] != "Cereal & Granola":
                return httpx.Response(
                    500,
                    json={
                        "title": "Internal Server Error",
                        "detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES",
                    },
                )
            html = self._page(body["query"])
        elif body["url"].endswith("/robots.txt"):
            html = ROBOTS
        elif "/savings/cl/coupons" in body["url"]:
            assert body.get("run_js") is True
            html = syn.coupons_page(3)
        else:
            return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
        return httpx.Response(
            200,
            json={
                "status": "done",
                "results": [{"html": html, "metadata": {"status_code": 200}}],
                "metadata": {"request_id": f"req-{n}", "timestamp": "2026-10-28T20:00:00Z"},
            },
        )


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
def env(
    migrated_engine: Engine, tmp_path: Path, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": dev_store,
        "private_label": private_label,
        "tmp": tmp_path,
    }


def _nodes(factory: sessionmaker[Session]) -> list[Node]:
    with factory() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
    return [
        Node(12, "Breakfast", ids[12], "Cereal & Granola", "03001", f"{BASE}/pl/cereal-granola/03001"),
        Node(
            12,
            "Breakfast",
            ids[12],
            "Bars & Toaster Pastries",
            "03002",
            f"{BASE}/pl/bars-toaster-pastries/03002",
        ),
    ]


def _ceiling(factory: sessionmaker[Session], submissions: int, usd: float = 1.0) -> None:
    with factory() as s:
        oxylabs.set_ceiling(s, submissions=submissions, usd=usd, actor="test", reason="test")
        s.commit()


def _run(
    env: dict[str, Any],
    settings: Settings,
    fake: FakeOxylabs,
    *,
    run_id: str | None = None,
    limits: Limits | None = None,
) -> tuple[str, str]:
    # The fake provider serves search pages only; the page loop has its own tests (test_listing_pages.py).
    acq = AcquisitionSettings(
        browser_provider=BrowserProvider.OXYLABS, oxylabs=OxylabsSettings(listing_route="search")
    )
    pipe = Pipeline(
        env["engine"],
        env["storage"],
        Settings(acquisition=acq, records=settings.records, attestation=settings.attestation),
        env["store"],
        env["private_label"],
    )
    resume = run_id is not None
    if run_id is None:
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
        config=CollectionConfig(limits=limits or Limits()),
        trigger="manual",
    )
    status = asyncio.run(pipe.execute(run_id, "test-collector", resume=resume, collector=collector))
    return run_id, status


def _no_key_anywhere(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            assert KEY.encode() not in path.read_bytes(), path


def test_an_oxylabs_run_verifies_every_page_and_records_products_by_their_own_taxonomy(
    env: dict[str, Any], settings: Settings
) -> None:
    _ceiling(env["factory"], 10)
    fake = FakeOxylabs()
    run_id, status = _run(env, settings, fake)
    # Read through the first page of a search, no listing can be complete: the run is never published.
    assert status == "rejected", status
    assert [r["path"] for r in fake.requests] == [
        "/v1/scrape/marianos",  # robots.txt
        "/v1/scrape/marianos/search",  # Cereal & Granola (store verified, then recorded)
        "/v1/scrape/marianos",  # the Coupons page, rendered
        "/v1/scrape/marianos/search",  # Bars & Toaster Pastries
    ]
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.counts["gates"]["G1"] == "PASS" and run.counts["gates"]["G3"] == "FAIL"
        recs = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        # The cereal page's cereals; its bar is recorded under Bars (its own taxonomy); its can is in no
        # planned listing and is not recorded; the sponsored cereal is recorded once.
        assert CANNED.upc not in recs
        assert {u for u, r in recs.items() if r.record["sub_category"] == "Cereal & Granola"} == {
            p.upc for p in CEREAL
        }
        assert recs[BAR_ON_CEREAL.upc].record["sub_category"] == "Bars & Toaster Pastries"
        assert recs[CEREAL[4].upc].status == "excluded"  # "about 1 lb"
        assert recs[CEREAL[1].upc].status == "valid"
        assert (recs[CEREAL[1].upc].record["regular_price"], recs[CEREAL[1].upc].record["sale_price"]) == (
            "8.79",
            "5.49",
        )
        assert recs[CEREAL[2].upc].record["volume_deals_description"].startswith("2 For $8.00")
        obs = {
            o.upc: o for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id))
        }
        sponsored = obs[CEREAL[3].upc].provenance["membership"]
        assert sponsored["placement"] == "sponsored" and sponsored["price_location"] == "53100503"
        assert sponsored["read_through"]["search"] == "Cereal & Granola"
        bar = obs[BAR_ON_CEREAL.upc].provenance
        assert (
            bar["node"] == "03002"
            and bar["read_on"] == "03001"
            and BARS_TAX in bar["membership"]["taxonomy_ids"]
        )
        assert {o.provenance["source_check"]["result"] for o in obs.values()} == {"PASS"}
        cov = {c.taxonomy_id: c for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))}
        assert cov["03001"].status == cov["03002"].status == "INCOMPLETE"
        assert cov["03001"].total_count is None and cov["03001"].organic_upcs == len(CEREAL)
        read = cov["03001"].partition["read"]
        assert (read["query"], read["query_total"], read["cards"], read["members"]) == (
            "Cereal & Granola",
            431,
            7,
            5,
        )
        task_reason = s.scalar(
            select(Event.message).where(Event.run_id == run_id, Event.code == "NODE_INCOMPLETE")
        )
        assert task_reason and "accessible pages exhausted; coverage incomplete" in task_reason
        atts = list(s.scalars(select(StoreAttestation).where(StoreAttestation.run_id == run_id)))
        assert {a.phase for a in atts} >= {"preflight", "task_start", "final"} and all(
            a.result == "PASS" for a in atts
        )
        checks = {c["name"]: c for c in atts[0].checks["checks"]}
        assert (
            checks["provider_request"]["ok"]
            and checks["price_locations"]["ok"]
            and checks["search_request"]["ok"]
        )
        usage = list(s.scalars(select(ProviderUsage).where(ProviderUsage.run_id == run_id)))
        assert len(usage) == 4 and {u.state for u in usage} == {"settled"}
        assert round(sum(u.cost_usd for u in usage), 6) == 0.006 and {u.cost_source for u in usage} == {
            "rule"
        }
        assert run.counts["coupons_route"]["coupon_cards"] == 3
        assert run.counts["coupons_route"]["status"] == "READ"
        (seg,) = s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        assert (
            seg.credits_estimated == 4
            and seg.account_remaining_start == 10
            and seg.account_remaining_end == 6
        )
        codes = [c for (c,) in s.execute(select(Event.code).where(Event.run_id == run_id)).all()]
        assert "PROVIDER_SESSION_OPENED" in codes and "PROVIDER_SESSION_CLOSED" in codes
    _no_key_anywhere(env["tmp"])


def test_without_a_ceiling_nothing_is_sent(env: dict[str, Any], settings: Settings) -> None:
    fake = FakeOxylabs()
    run_id, status = _run(env, settings, fake)
    assert status == "interrupted" and fake.requests == []
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "SPENDING_CEILING"


def test_the_ceiling_stops_the_run_resumably_and_a_raised_ceiling_continues_it(
    env: dict[str, Any], settings: Settings
) -> None:
    _ceiling(env["factory"], 3)
    fake = FakeOxylabs()
    run_id, status = _run(env, settings, fake)
    assert status == "interrupted" and len(fake.requests) == 3  # robots, cereal, coupons: never a fourth
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "SPENDING_CEILING"
        assert s.scalar(select(func.count()).select_from(ProviderUsage)) == 3
    _ceiling(env["factory"], 5)  # counted from now: five more
    run_id, status = _run(env, settings, fake, run_id=run_id)
    assert status == "rejected"  # finished; incomplete as every Oxylabs listing is
    with env["factory"]() as s:
        n = s.scalar(select(func.count()).select_from(RecordRow).where(RecordRow.run_id == run_id))
        assert n == len(CEREAL) + len(BARS)  # nothing twice
        assert s.scalar(select(func.count()).select_from(ProviderUsage)) == 5  # robots again, then bars


def test_a_listing_the_provider_cannot_bring_stays_unread_without_charge_and_the_run_stops_resumably(
    env: dict[str, Any], settings: Settings
) -> None:
    """Release 1.8.0: a page the provider did not bring never closes its listing: the task comes back within
    its bounded attempts, and the run then stops at that page, resumable."""
    _ceiling(env["factory"], 30)
    fake = FakeOxylabs("fail_bars")
    run_id, status = _run(env, settings, fake)
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "PROVIDER_ERROR"
        rows = list(s.scalars(select(ListingPage).where(ListingPage.taxonomy_id == "03002")))
        assert [(r.requested_page, r.state, r.verdict) for r in rows] == [(1, "failed", "failed")] * 3
        cov = {
            c.taxonomy_id: c.status
            for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))
        }
        assert cov.get("03002") != "DONE"
        failed = list(s.scalars(select(ProviderUsage).where(ProviderUsage.outcome == "provider_failed_free")))
        # Three task attempts of three submissions each (408/429/5xx are retried), none charged: Oxylabs does
        # not bill a faulted scrape.
        assert len(failed) == 9 and sum(u.cost_usd for u in failed) == 0


@pytest.mark.parametrize(
    ("mode", "reason"), [("empty_bars", "accessible pages exhausted"), ("unread_bars", "not read: ")]
)
def test_a_search_page_without_products_closes_its_listing_and_the_run_goes_on(
    env: dict[str, Any], settings: Settings, mode: str, reason: str
) -> None:
    # A search that found nothing has no price to check (its store still is); a page that shows no
    # product although its search reports results is not read. Neither stops the run.
    _ceiling(env["factory"], 10)
    run_id, status = _run(env, settings, FakeOxylabs(mode))
    assert status == "rejected"  # first pages only: never complete, never published
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code not in {"STORE_NOT_VERIFIED", "ABNORMAL_RESULT"}
        cov = {c.taxonomy_id: c for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))}
        assert cov["03002"].status == "INCOMPLETE" and reason in cov["03002"].partition["reason"]
        recs = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        assert recs[CEREAL[1].upc].status == "valid"
        atts = list(s.scalars(select(StoreAttestation).where(StoreAttestation.run_id == run_id)))
        assert atts and all(a.result == "PASS" for a in atts)
        checks = [{c["name"]: c for c in a.checks["checks"]} for a in atts]
        # The Bars page: its store and request checked, no price to check.
        assert any(
            c["price_locations"]["ok"] is None and c["search_request"]["ok"] and c["provider_request"]["ok"]
            for c in checks
        )


def test_a_product_that_states_no_price_is_kept_unpriced_and_the_run_goes_on(
    env: dict[str, Any], settings: Settings
) -> None:
    # Live 2026-10-29, the search for "Fresh Herbs": a product temporarily out of stock shows "Prices May
    # Vary" and its data states no price. It has no price location to check; every price the page states
    # is still the store's. The run goes on and the product is exported with empty prices, not valid
    # (release 1.4.0: eligible_unpriced, its availability from its own data).
    _ceiling(env["factory"], 10)
    run_id, status = _run(env, settings, FakeOxylabs("unpriced"))
    assert status == "rejected"  # first pages only: never complete, never published
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code not in {"STORE_NOT_VERIFIED", "ABNORMAL_RESULT"}
        recs = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        assert recs[CEREAL[1].upc].status == "valid"
        unpriced = recs[UNPRICED.upc]
        assert unpriced.status == "eligible_unpriced"
        assert unpriced.record["regular_price"] == unpriced.record["sale_price"] == ""
        atts = list(s.scalars(select(StoreAttestation).where(StoreAttestation.run_id == run_id)))
        assert atts and all(a.result == "PASS" for a in atts)
        checks = [{c["name"]: c for c in a.checks["checks"]} for a in atts]
        cereal = [
            c["price_locations"]
            for c in checks
            if "no price stated" in (c["price_locations"]["observed"] or {})
        ]
        assert cereal and all(c["ok"] is True and c["observed"]["no price stated"] == 1 for c in cereal)


def test_pages_that_show_no_product_in_a_row_stop_the_run(
    env: dict[str, Any], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oxylabs_live, "MAX_ABNORMAL_LISTINGS_IN_A_ROW", 1)
    _ceiling(env["factory"], 10)
    run_id, _ = _run(env, settings, FakeOxylabs("unread_bars"))
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "ABNORMAL_RESULT"


def test_a_refused_key_stops_the_run_without_charge(env: dict[str, Any], settings: Settings) -> None:
    _ceiling(env["factory"], 20)
    fake = FakeOxylabs("auth")
    run_id, status = _run(env, settings, fake)
    assert status == "interrupted" and len(fake.requests) == 1  # never retried
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "PROVIDER_AUTH"
        (u,) = s.scalars(select(ProviderUsage))
        assert (u.outcome, u.cost_usd, u.http_status) == ("auth", 0.0, 401)


@pytest.mark.parametrize("mode", ["price_elsewhere", "default_store"])
def test_a_page_not_priced_or_selected_for_the_store_stops_before_any_product(
    env: dict[str, Any], settings: Settings, mode: str
) -> None:
    _ceiling(env["factory"], 20)
    run_id, status = _run(env, settings, FakeOxylabs(mode))
    assert status == "rejected"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "STORE_NOT_VERIFIED"
        assert s.scalar(select(func.count()).select_from(RecordRow).where(RecordRow.run_id == run_id)) == 0
