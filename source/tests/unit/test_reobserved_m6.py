"""Release 1.9.0 (M6): the earlier offer and size findings, checked again against the products as Vernon Hills
(53100502, PICKUP) showed them on 2026-11-06.

Fixture data (``tests/fixtures/oxylabs_2026-11-06``, ``SOURCES_M6.json``): the product data each product page
saved by the gated stage O1 carries in its page state, and the grid cards and page-state data of the three
sizes Q2 left unresolved, as Q2 saved them. The Buy 1 Save and dip products were not in Q2's listings: their
cards here are SYNTHETIC (``tests.synthetic_marianos``), showing what the saved product page displays (title,
size, price); their product data is the saved one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from marianos_headless.assembly.offers import OfferKind, classify, derive_deal_fields, is_volume_text
from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import CategoryAssignment, RecordStatus, StoreFields
from marianos_headless.collection.live import CardBuild, build_card, grid_cards
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import (
    PrivateLabelConfig,
    RecordSettings,
    Settings,
    StoreConfig,
    load_stores,
)
from marianos_headless.sites.marianos.dom_parsers import CardObservation
from marianos_headless.sites.marianos.source_json import PRODUCTS, ResponseRef, SourceIndex, product_offers
from tests import synthetic_marianos as syn

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "oxylabs_2026-11-06"
BASE = "https://www.marianos.com"
CUTWATER, FINNISH, NUTRL, DIP = "0081675102373", "0086001079386", "0001820020352", "0073679800140"
PUPPY_CHOW, BLUE_DOG, ULTRA_CHEWY = "0001780010048", "0065922318120", "0087786900820"
STORE = StoreFields(
    "60061",
    "Marianos Vernon Hills",
    "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
    "https://www.marianos.com/logo.svg",
)


def o1_index() -> SourceIndex:
    idx = SourceIndex()
    idx.add(
        PRODUCTS,
        (FIX / "o1_state_products_m6.json").read_text("utf-8"),
        ResponseRef(PRODUCTS, "O1", "f" * 64, "2026-11-06T18:00:00Z"),
    )
    return idx


def q2_index() -> SourceIndex:
    idx = SourceIndex()
    idx.add(
        PRODUCTS,
        (FIX / "q2_state_products_m6_sizes.json").read_text("utf-8"),
        ResponseRef(PRODUCTS, "Q2", "c" * 64, "2026-11-02T13:13:14Z"),
    )
    return idx


def synthetic_card(p: syn.Product) -> CardObservation:
    _, parsed, _, _ = grid_cards(f'<div data-testid="paginate-items">{syn.grid_card(0, p, BASE)}</div>')
    assert parsed and parsed[0].upc == p.upc
    return parsed[0]


@pytest.fixture(scope="module")
def q2_cards() -> dict[str, CardObservation]:
    grid, parsed, _, _ = grid_cards((FIX / "q2_cards_m6_sizes.html").read_text("utf-8"))
    assert grid
    return {c.upc or "": c for c in parsed}


@pytest.fixture(scope="module")
def vernon_hills() -> StoreConfig:
    return next(
        s for s in load_stores(ROOT / "config" / "stores.yaml").stores if s.key == "marianos-53100502-pickup"
    )


@pytest.fixture
def build(settings: Settings, vernon_hills: StoreConfig, private_label: PrivateLabelConfig) -> Any:
    detector = PrivateLabelDetector(private_label, settings.records.store_brand_positive_value)

    def run(
        card: CardObservation, idx: SourceIndex, category: tuple[str, str] = ("Pet", "Dog Food")
    ) -> CardBuild:
        return build_card(
            card,
            fetch_id="O1",
            observed_at="2026-11-06T18:00:00+00:00",
            store=vernon_hills,
            store_values=STORE,
            store_provenance={},
            category=CategoryAssignment(*category),
            crawl_date="2026-11-06",
            settings=settings,
            detector=detector,
            sources=idx,
        )

    return run


# -- Buy 1 Save: one retail unit, not a multi-unit volume offer ----------------------------------------


def test_the_current_buy_one_save_offer_is_kept_with_its_source_terms_and_not_as_volume() -> None:
    facts = o1_index().product(NUTRL)
    assert facts is not None and facts.size == "8 cans / 12 fl oz"
    offers = product_offers(facts, tz="America/Chicago")
    assert [(o.text, o.offer_code, o.starts_at, o.ends_at) for o in offers] == [
        (
            "Buy 1 Save $2",
            "9f58fa85-1362-46af-8aff-5ba15dfeecb4",
            "2026-09-16T00:00:00.000Z",
            "2027-01-05T23:59:59.000Z",
        )
    ]
    assert "PICKUP" in (offers[0].modalities or ())
    assert not is_volume_text("Buy 1 Save $2")
    assert classify(offers[0], "PICKUP").kind is OfferKind.OTHER_PROMO
    deals = derive_deal_fields(offers, RecordSettings(), "PICKUP")
    assert deals.volume_deals_description == deals.volume_deals_price == ""
    assert deals.digital_deals_price == ""  # no payable price is calculated from a saving


def test_the_buy_one_save_product_keeps_its_multipack_size_and_no_promotion_price(build: Any) -> None:
    card = synthetic_card(
        syn.Product(
            NUTRL,
            "nutrl-vodka-hard-seltzer",
            "Nutrl Vodka Hard Seltzer, Real Fruit Juice Variety",
            "8 cans / 12 fl oz",
            "$18.99",
        )
    )
    b = build(card, o1_index(), ("Beer, Wine & Liquor", "Hard Seltzer")).built
    assert b.record["weight"] == "8 cans / 12 fl oz"  # the pack identity, separate from the offer
    assert b.record["volume_deals_description"] == b.record["volume_deals_price"] == ""
    assert b.record["sale_price"] == "" and b.record["regular_price"] == "18.99"
    assert RecordFlag.OTHER_PROMO_UNCLASSIFIED in b.flags
    kept = [c for c in b.deals.classified if c.offer.text == "Buy 1 Save $2"]
    assert len(kept) == 1 and kept[0].kind is OfferKind.OTHER_PROMO
    assert kept[0].offer.offer_code == "9f58fa85-1362-46af-8aff-5ba15dfeecb4"


@pytest.mark.parametrize(("upc", "size"), [(CUTWATER, "4 cans / 12 fl oz"), (FINNISH, "12 cans / 12 fl oz")])
def test_the_named_examples_state_no_offer_today(upc: str, size: str) -> None:
    # Reobserved at Vernon Hills PICKUP on 2026-11-06: the product data states no offer (the earlier
    # "Buy 1 Save" offers are not current). Nothing is carried forward.
    facts = o1_index().product(upc)
    assert facts is not None and facts.size == size and facts.offers == ()
    assert product_offers(facts, tz="America/Chicago") == []


# -- size ------------------------------------------------------------------------------------------------


def test_the_dip_size_comes_from_its_current_pack_evidence_not_the_serving(build: Any) -> None:
    facts = o1_index().product(DIP)
    assert facts is not None and facts.size == "2 tbsp"  # the retailer's displayed size is still the serving
    card = synthetic_card(
        syn.Product(
            DIP,
            "avocado-green-goddess-dip-spread",
            "Avocado Green Goddess Dip & Spread 8 oz.",
            "2 tbsp",
            "$4.99",
        )
    )
    b = build(card, o1_index(), ("Deli", "Dips")).built
    assert b.record["weight"] == "8 oz"
    assert RecordFlag.SIZE_CONFLICT_RESOLVED in b.flags
    ev = b.provenance["_size_evidence"]
    assert ev["rule"] == "R3"
    assert ev["observations"]["displayed"] == "2 tbsp"
    assert ev["observations"]["product_data"] == "8 OUNCES"
    assert ev["observations"]["title"] == "Avocado Green Goddess Dip & Spread 8 oz."


@pytest.mark.parametrize(
    ("upc", "displayed", "product_data"),
    [
        (PUPPY_CHOW, "4 lb.", "4.4 POUNDS"),
        (BLUE_DOG, "16.2 oz", "18 OUNCES"),
        (ULTRA_CHEWY, "1.3 oz", "1.2 OUNCES"),
    ],
)
def test_the_three_unresolved_sizes_stay_unresolved_with_the_current_evidence(
    q2_cards: dict[str, CardObservation], build: Any, upc: str, displayed: str, product_data: str
) -> None:
    # The product pages of 2026-11-06 show the same displayed size and product data as Q2: still two
    # different quantities, so neither is chosen; both are kept in the record's provenance.
    for idx in (q2_index(), o1_index()):
        b = build(q2_cards[upc], idx).built
        assert b.record["weight"] == ""
        assert RecordFlag.SIZE_CONFLICT_UNRESOLVED in b.flags
        obs = b.provenance["_size_evidence"]["observations"]
        assert (obs["displayed"], obs["product_data"]) == (displayed, product_data)
        assert b.status is RecordStatus.VALID  # the price is verified; only the size is left empty


def test_the_m6_fixture_sources_are_recorded() -> None:
    src = json.loads((FIX / "SOURCES_M6.json").read_text("utf-8"))
    assert set(src["o1_product_pages"]) == {CUTWATER, FINNISH, NUTRL, DIP, PUPPY_CHOW, BLUE_DOG, ULTRA_CHEWY}
    assert all(
        len(v["capture_gz_sha256"]) == 64 and v["request_id"] for v in src["o1_product_pages"].values()
    )
