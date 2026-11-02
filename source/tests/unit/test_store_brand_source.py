"""store_brand from source-backed brand data only (release 1.3.1; brief: "Private label only from
source-backed brand data, else 'no'").

FIXTURE: the real Oxylabs search page for "cereal" of 2026-10-28 (tests/fixtures/oxylabs_2026-10-28), its
cards and the product data of its page state, replayed offline."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import CategoryAssignment, StoreFields
from marianos_headless.collection.live import build_card, grid_cards
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig
from marianos_headless.sites.marianos.dom_parsers import CardObservation
from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.search_state import state_products
from marianos_headless.sites.marianos.source_json import PRODUCTS, ResponseRef, SourceIndex

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "oxylabs_2026-10-28"
KROGER_APPLE_CRUNCH, CASCADIAN = "0001111013876", "0002190845556"
STORE = StoreFields("60601", "Marianos Lakeshore East", "333 E Benton Pl, CHICAGO, IL 60601", "")


@pytest.fixture(scope="module")
def page() -> tuple[dict[str, CardObservation], list[dict[str, object]]]:
    html = gzip.decompress((FIX / "search_cereal.html.gz").read_bytes()).decode("utf-8")
    _, cards, _, _ = grid_cards(html)
    return {c.upc or "": c for c in cards}, state_products(parse_initial_state(html))


def _build(
    card: CardObservation,
    products: list[dict[str, object]],
    settings: Settings,
    store: StoreConfig,
    private_label: PrivateLabelConfig,
) -> object:
    idx = SourceIndex()
    if products:
        body = json.dumps({"data": {"products": products}})
        idx.add(PRODUCTS, body, ResponseRef(PRODUCTS, "F1", "c" * 64, "2026-10-28T18:56:16Z"))
    return build_card(
        card,
        fetch_id="F1",
        observed_at="2026-10-28T18:56:16+00:00",
        store=store,
        store_values=STORE,
        store_provenance={},
        category=CategoryAssignment("Breakfast", "Cereal & Granola"),
        crawl_date="2026-10-28",
        settings=settings,
        detector=PrivateLabelDetector(private_label, settings.records.store_brand_positive_value),
        sources=idx,
    ).built


def test_the_products_own_brand_decides(
    page: tuple[dict[str, CardObservation], list[dict[str, object]]],
    settings: Settings,
    dev_store: StoreConfig,
    private_label: PrivateLabelConfig,
) -> None:
    cards, products = page
    kroger = _build(cards[KROGER_APPLE_CRUNCH], products, settings, dev_store, private_label)
    assert kroger.record["store_brand"] == "yes"  # type: ignore[attr-defined]
    signals = kroger.provenance["_store_brand_signals"]  # type: ignore[attr-defined]
    assert (signals["brand"], signals["brand_source"]) == ("Kroger", "product_data")
    national = _build(cards[CASCADIAN], products, settings, dev_store, private_label)
    assert national.record["store_brand"] == "no"  # type: ignore[attr-defined]
    assert national.provenance["_store_brand_signals"]["brand"] == "Cascadian Farm Organic"  # type: ignore[attr-defined]


def test_without_brand_data_a_kroger_title_and_upc_are_not_enough(
    page: tuple[dict[str, CardObservation], list[dict[str, object]]],
    settings: Settings,
    dev_store: StoreConfig,
    private_label: PrivateLabelConfig,
) -> None:
    cards, _ = page
    built = _build(cards[KROGER_APPLE_CRUNCH], [], settings, dev_store, private_label)
    assert built.record["store_brand"] == "no"  # type: ignore[attr-defined]
    signals = built.provenance["_store_brand_signals"]  # type: ignore[attr-defined]
    assert signals["brand_source"] == "none"
    assert signals["signals"] == {"brand": None, "upc_prefix": True, "title_prefix": True}
