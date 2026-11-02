"""The client's store, on its own real pages (release 1.8.0).

FIXTURE (tests/fixtures/oxylabs_2026-11-02, captured live by the probes of 2026-11-02 at store 53100502,
Pickup,
replayed offline; nothing here is a live run). Each test reads the page as a run would."""

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

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection import pagination
from marianos_headless.collection.config import CollectionConfig
from marianos_headless.collection.live import grid_cards
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.collection.pagination import PageVerdict
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    PrivateLabelConfig,
    Settings,
    StoreConfig,
    load_stores,
)
from marianos_headless.db.models import (
    CategorySource,
    ListingPage,
    ProductObservation,
    RecordRow,
    Run,
    StoreAttestation,
    Task,
)
from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.search_state import brand_facets, listing_children, search_summary
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from marianos_headless.worker.store_selection import verify_store
from tests.conftest import CONFIG
from tests.integration.helpers import seed

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "oxylabs_2026-11-02"
KEY = "oxy-replay-key-never-sent-0123456789"
BASE = "https://www.marianos.com"
ROBOTS = "User-agent: *\nDisallow: /checkout$\n"
TARGET = "marianos-53100502-pickup"
OTHER = "marianos-53100503-instore"


def _html(name: str) -> str:
    return gzip.decompress((FIX / f"{name}.html.gz").read_bytes()).decode("utf-8")


def _store(key: str) -> StoreConfig:
    return next(s for s in load_stores(CONFIG / "stores.yaml").stores if s.key == key)


def _facts(page: int, html: str) -> pagination.PageFacts:
    return pagination.page_facts(page, search_summary(parse_initial_state(html)), len(grid_cards(html)[1]))


def test_the_listing_pages_state_the_clients_store_and_pickup(settings: Settings) -> None:
    for name in ("listing_03001_p1", "listing_03001_p2", "search_cereal_p1", "listing_0300100001_brand"):
        v = verify_store(_store(TARGET), settings, _html(name), fetch_id="f", purpose="listing", url=BASE)
        checks = {c.name: c for c in v.checks}
        assert all(
            checks[c].ok for c in ("location_id", "store_name", "address", "postal_code", "fulfillment")
        )
        v = verify_store(_store(OTHER), settings, _html(name), fetch_id="f", purpose="listing", url=BASE)
        assert not v.passed


def test_page_2_of_the_rendered_listing_is_a_real_next_page() -> None:
    one, two = _facts(1, _html("listing_03001_p1")), _facts(2, _html("listing_03001_p2"))
    assert (one.returned_page, one.taxonomy_id, one.total, one.available) == (1, "03001", 397, 250)
    assert (two.returned_page, two.loaded_pages, two.location_id, two.modality) == (
        2,
        (2,),
        "53100502",
        "PICKUP",
    )
    j = pagination.judge(two, taxonomy="03001", earlier=[one.organic], store_verified=True)
    assert j.verdict is PageVerdict.NEW and len(j.new) == 24
    assert pagination.last_page(one.total, one.available) == 11  # 250 reachable, 24 a page


def test_page_2_without_rendering_holds_no_cards_and_does_not_count() -> None:
    one = _facts(1, _html("listing_03001_p1"))
    j = pagination.judge(
        _facts(2, _html("listing_03001_p2_no_js")),
        taxonomy="03001",
        earlier=[one.organic],
        store_verified=True,
    )
    assert j.verdict is PageVerdict.MALFORMED and "0 cards" in j.detail


def test_the_search_routes_page_2_is_page_1_again() -> None:
    """Probe L18: the response says page 2 and ranks 25-48, and it holds the 24 products of page 1."""
    one, two = _facts(1, _html("search_cereal_p1")), _facts(2, _html("search_cereal_p2"))
    assert two.returned_page == 2 and two.loaded_pages == (2,) and one.organic == two.organic
    j = pagination.judge(two, taxonomy=None, earlier=[one.organic], store_verified=True)
    assert j.verdict is PageVerdict.REPEATED and len(j.duplicates) == 24


def test_the_retailers_own_filters_divide_the_listing() -> None:
    state = parse_initial_state(_html("listing_03001_p1"))
    children = listing_children(state, "03001")
    assert sum(c["count"] for c in children) >= 397 and all(c["id"].startswith("03001") for c in children)
    brands = brand_facets(state)
    assert sum(b["count"] for b in brands) == 397
    filtered = _facts(1, _html("listing_0300100001_brand"))
    assert (filtered.total, filtered.available, len(filtered.organic)) == (8, 8, 8)


class Replay:
    """The real page 1 of Cereal & Granola (or of Candles, release 1.8.0rc2); everything below it not
    served."""

    def __init__(self, pages: dict[str, str] | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self.pages = pages or {"/pl/cereal-granola/03001": "listing_03001_p1"}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        url = body["url"]
        if url.endswith("/robots.txt"):
            html = ROBOTS
        elif any(url.endswith(path) for path in self.pages):
            assert body["store_id"] == "53100502" and body["fulfillment_type"] == "pickup"
            html = _html(next(name for path, name in self.pages.items() if url.endswith(path)))
        else:
            return httpx.Response(500, json={"detail": "REQUEST_FAILED_AFTER_TOO_MANY_RETRIES"})
        return httpx.Response(
            200,
            json={
                "status": "done",
                "results": [{"html": html, "metadata": {"status_code": 200}}],
                "metadata": {"request_id": f"replay-{len(self.requests)}"},
            },
        )


@pytest.mark.postgres
def test_the_real_first_page_goes_through_the_run_at_the_clients_store(
    migrated_engine: Engine, tmp_path: Path, private_label: PrivateLabelConfig, settings: Settings
) -> None:
    factory, _ = seed(migrated_engine)
    store = _store(TARGET)
    with factory() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
        oxylabs.set_ceiling(s, submissions=30, usd=1, actor="test", reason="replay")
        s.commit()
    nodes = [Node(12, "Breakfast", ids[12], "Cereal & Granola", "03001", f"{BASE}/pl/cereal-granola/03001")]
    acq = AcquisitionSettings(browser_provider=BrowserProvider.OXYLABS)
    pipe = Pipeline(
        migrated_engine,
        LocalStorageAdapter(tmp_path / "data"),
        Settings(acquisition=acq, records=settings.records, attestation=settings.attestation),
        store,
        private_label,
    )
    with factory() as s:
        run_id = pipe.create_live_run(
            s,
            nodes,
            trigger="console",
            snapshot={"plan": {"nodes": [n.as_dict() for n in nodes], "skipped": []}, "provider": "oxylabs"},
        )
        s.commit()
    replay = Replay()

    async def nap(_: float) -> None:
        return None

    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(replay),
        sleep=nap,
        config=CollectionConfig(),
        trigger="manual",
    )
    status = asyncio.run(pipe.execute(run_id, "replay", collector=collector))
    assert status == "interrupted"  # the child listings are not in this fixture: the provider "brings" none
    with factory() as s:
        r = s.get(Run, run_id)
        assert r is not None and r.stop_code == "PROVIDER_ERROR"
        pages = list(
            s.scalars(
                select(ListingPage).where(ListingPage.run_id == run_id, ListingPage.taxonomy_id == "03001")
            )
        )
        assert [(p.requested_page, p.state, p.verdict, p.total, p.available) for p in pages] == [
            (1, "completed", "new", 397, 250)
        ]
        assert pages[0].location_id == "53100502" and pages[0].modality == "PICKUP"
        recs = {x.upc: x for x in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        assert len(recs) >= 24
        assert {x.record["store_name"] for x in recs.values()} == {"Marianos Vernon Hills"}
        assert {x.record["store_location"] for x in recs.values()} == {
            "1720 N Milwaukee Ave, Vernon Hills, IL 60061"
        }
        obs = list(s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id)))
        assert {o.provenance["membership"]["price_location"] for o in obs} <= {"53100502", None}
        atts = list(s.scalars(select(StoreAttestation).where(StoreAttestation.run_id == run_id)))
        assert atts and all(a.result == "PASS" for a in atts)
        children = list(s.scalars(select(Task).where(Task.run_id == run_id, Task.kind == "listing_node")))
        planned = {(t.cursor or {}).get("node", {}).get("taxonomy_id") for t in children}
        assert "0300100001" in planned and len(planned) >= 4  # the site's own subcategories


@pytest.mark.postgres
@pytest.mark.parametrize("page", ["listing_32001_p1", "listing_32001_p1_mini"])
def test_a_price_the_product_data_states_for_no_store_is_exported_as_displayed_and_never_valid(
    migrated_engine: Engine,
    tmp_path: Path,
    private_label: PrivateLabelConfig,
    settings: Settings,
    page: str,
) -> None:
    """Release 1.8.0rc2, from the live qualification run Q1 of 1.8.0rc1 (2026-11-02): on the real Candles
    page 1 at 53100502 Pickup, UPC 0019798100139 shows $8.69 while its own data states that price for no store
    (``price.storePrices`` without ``sourceLocationId``; the price is under ``postalCodes`` for 60061; the
    store's stock level is TEMPORARILY_OUT_OF_STOCK). 1.8.0rc1 counted it VALID and the canary's source check
    stopped the run. Now the record keeps its displayed price, is flagged and not valid, and the canary (its
    source check unchanged) lets the run go on to page 2. FIXTURE: a replay of the stored page."""
    factory, _ = seed(migrated_engine)
    store = _store(TARGET)
    with factory() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
        oxylabs.set_ceiling(s, submissions=30, usd=1, actor="test", reason="replay")
        s.commit()
    nodes = [
        Node(
            23,
            "Candles Home Fragrances",
            ids[23],
            "Candles Home Fragrances",
            "32001",
            f"{BASE}/pl/candles-home-fragrances/32001",
        )
    ]
    acq = AcquisitionSettings(browser_provider=BrowserProvider.OXYLABS)
    pipe = Pipeline(
        migrated_engine,
        LocalStorageAdapter(tmp_path / "data"),
        Settings(acquisition=acq, records=settings.records, attestation=settings.attestation),
        store,
        private_label,
    )
    with factory() as s:
        run_id = pipe.create_live_run(
            s,
            nodes,
            trigger="console",
            snapshot={"plan": {"nodes": [n.as_dict() for n in nodes], "skipped": []}, "provider": "oxylabs"},
        )
        s.commit()
    replay = Replay({"/pl/candles-home-fragrances/32001": page})

    async def nap(_: float) -> None:
        return None

    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(replay),
        sleep=nap,
        config=CollectionConfig(),
        trigger="manual",
    )
    status = asyncio.run(pipe.execute(run_id, "replay", collector=collector))
    with factory() as s:
        r = s.get(Run, run_id)
        assert r is not None
        # Past the canary: page 2 was asked for (and not served by this fixture).
        assert r.stop_code != "CANARY_CHECK_FAILED" and status == "interrupted"
        assert any(str(b["url"]).endswith("32001?page=2") for b in replay.requests)
        recs = {x.upc: x for x in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
        [obs] = s.scalars(
            select(ProductObservation).where(
                ProductObservation.run_id == run_id, ProductObservation.upc == "0019798100139"
            )
        )
    candle = recs["0019798100139"]
    assert candle.status == "exported_not_valid" and "PRICE_STORE_NOT_STATED" in candle.flags
    assert candle.record["regular_price"] == "8.69"  # exported as displayed
    why = obs.provenance["fields"]["_price_store_not_stated"]
    assert why["product_data"]["price_location"] is None
    assert why["product_data"]["postal_codes_with_a_price"] == ["60061"]
    assert why["product_data"]["stock_level_at_store"] == "TEMPORARILY_OUT_OF_STOCK"
    others = [x for k, x in recs.items() if k != "0019798100139"]
    assert len(others) == 23 and {x.status for x in others} == {"valid"}
    assert not any("PRICE_STORE_NOT_STATED" in x.flags for x in others)


def test_a_store_price_and_a_price_for_no_store_are_told_apart() -> None:
    """Release 1.8.0rc2 (unit): the product data's price and the store it states it for."""
    from marianos_headless.sites.marianos.source_json import ResponseRef, parse_product

    ref = ResponseRef(kind="products_v2", fetch_id="f", sha256="0" * 64, observed_at="2026-11-02T12:16:51Z")
    base = {"item": {"upc": "0019798100139"}, "inventory": {"locations": []}}
    no_store = parse_product(
        {
            **base,
            "price": {"storePrices": {"regular": {"price": "USD 8.69"}, "sellerId": "KR001"}},
            "postalCodes": [{"postalCode": "60061", "prices": [{"regular": {"price": "USD 8.69"}}]}],
        },
        ref,
    )
    at_store = parse_product(
        {
            **base,
            "price": {"storePrices": {"regular": {"price": "USD 8.69"}, "sourceLocationId": "53100502"}},
        },
        ref,
    )
    unpriced = parse_product({**base, "price": {"storePrices": {}}}, ref)
    assert no_store is not None and at_store is not None and unpriced is not None
    assert no_store.price_postal_codes == ("60061",)
    assert no_store.check("53100502", "PICKUP").price_store_not_stated
    assert not at_store.check("53100502", "PICKUP").price_store_not_stated
    assert not unpriced.check("53100502", "PICKUP").price_store_not_stated  # no price stated at all


def test_the_grids_mini_cards_read_the_same_as_its_product_cards() -> None:
    """Release 1.8.0rc3, from the live qualification run Q1b of 1.8.0rc2 (2026-11-02): 13 minutes after Q1's
    Candles page 1 (product-card-N cards), the same page came with its 24 products as mini-product-card-N
    cards (class MiniProductCard). 1.8.0rc2 saw no card and stopped the run as abnormal. Both now read as the
    same 24 cards, field by field; only the card's own test id differs. FIXTURE: the two stored pages."""
    _, regular, _, _ = grid_cards(_html("listing_32001_p1"))
    _, mini, _, _ = grid_cards(_html("listing_32001_p1_mini"))
    assert len(regular) == len(mini) == 24
    assert all(c.card_testid.startswith("product-card-") for c in regular)
    assert all(c.card_testid.startswith("mini-product-card-") for c in mini)
    for a, b in zip(regular, mini, strict=True):
        assert {**vars(a), "card_testid": ""} == {**vars(b), "card_testid": ""}
