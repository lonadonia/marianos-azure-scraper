"""Release 1.9.0 (M4): complete coupon terms from a product's own page, and (M3) source-value anomalies of the
displayed price per measure.

Fixture data (``tests/fixtures/oxylabs_2026-11-06``): the four M4 products' grid cards and page-state data as
run Q2 saved them (2026-11-02, Vernon Hills 53100502, PICKUP), and product pages saved by the gated stage O1
(2026-11-06), one rendered (its coupons shown) and two the provider brought without running their scripts.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from marianos_headless.assembly.offers import OfferKind, OfferSource
from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import (
    CategoryAssignment,
    RecordStatus,
    SourceCheck,
    StoreFields,
    ppm_source_anomalies,
)
from marianos_headless.collection.live import CardBuild, build_card, grid_cards
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig, load_stores
from marianos_headless.sites.marianos.dom_parsers import CardObservation
from marianos_headless.sites.marianos.pdp_savings import parse_pdp_savings, savings_document
from marianos_headless.sites.marianos.source_json import PDP_SAVINGS, PRODUCTS, ResponseRef, SourceIndex

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "oxylabs_2026-11-06"
PURINA, PURINA_LAMB, TEMPTATIONS, ENERGIZER = (
    "0001780014939",
    "0001780014941",
    "0002310014848",
    "0003980014995",
)
NUTRL = "0001820020352"
RENDERED = "pdp_0001780014939_rendered.html.gz"
UNRENDERED = "pdp_0001780014941_unrendered.html.gz"
SALE = "pdp_0001820020352_unrendered_sale.html.gz"
STORE = StoreFields(
    "60061",
    "Marianos Vernon Hills",
    "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
    "https://www.marianos.com/logo.svg",
)


def page(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def cards() -> dict[str, CardObservation]:
    grid, parsed, _, _ = grid_cards((FIX / "q2_cards_m4.html").read_text("utf-8"))
    assert grid
    return {c.upc or "": c for c in parsed}


def index(
    pdp: dict[str, tuple[str, bool | None]] | None = None, *, docs: dict[str, Any] | None = None
) -> SourceIndex:
    """Q2's product data, plus the Savings section of the given product pages (``upc: (page, rendered)``) or
    of hand-made documents (``docs``, marked as such in each test)."""
    idx = SourceIndex()
    idx.add(
        PRODUCTS,
        (FIX / "q2_state_products_m4.json").read_text("utf-8"),
        ResponseRef(PRODUCTS, "Q2", "c" * 64, "2026-11-02T13:13:14Z"),
    )
    for upc, (name, rendered) in (pdp or {}).items():
        doc = savings_document(page(name), upc=upc, rendered=rendered, requested_run_js=True)
        idx.add(
            PDP_SAVINGS,
            json.dumps(doc),
            ResponseRef(PDP_SAVINGS, "O1-" + upc, "d" * 64, "2026-11-06T18:30:00Z"),
        )
    for upc, doc in (docs or {}).items():
        idx.add(
            PDP_SAVINGS,
            json.dumps(doc),
            ResponseRef(PDP_SAVINGS, "HAND-" + upc, "e" * 64, "2026-11-06T18:30:00Z"),
        )
    return idx


@pytest.fixture(scope="module")
def vernon_hills() -> StoreConfig:
    return next(
        s for s in load_stores(ROOT / "config" / "stores.yaml").stores if s.key == "marianos-53100502-pickup"
    )


@pytest.fixture
def build(settings: Settings, vernon_hills: StoreConfig, private_label: PrivateLabelConfig) -> Any:
    detector = PrivateLabelDetector(private_label, settings.records.store_brand_positive_value)

    def run(card: CardObservation, idx: SourceIndex) -> CardBuild:
        return build_card(
            card,
            fetch_id="Q2",
            observed_at="2026-11-02T13:13:14+00:00",
            store=vernon_hills,
            store_values=STORE,
            store_provenance={},
            category=CategoryAssignment("Pet Supplies", "Dog Food"),
            crawl_date="2026-11-02",
            settings=settings,
            detector=detector,
            sources=idx,
        )

    return run


# -- the product page's Savings section -----------------------------------------------------------------


def test_a_rendered_product_page_names_each_coupon_with_its_complete_terms() -> None:
    s = parse_pdp_savings(page(RENDERED))
    assert s.section and [r.row_kind for r in s.rows] == ["other-coupon", "cash-back"]
    coupon, cash = s.rows
    assert (coupon.coupon_id, coupon.tag, coupon.headline) == (
        "4257015",
        "Coupon",
        "Save $10.00 on 2 Purina ONE",
    )
    assert (cash.coupon_id, cash.tag, cash.headline) == (
        "4257014",
        "Cash Back",
        "$10.00 Cash Back on 2 Purina ONE",
    )
    assert coupon.is_coupon and cash.is_coupon
    assert (coupon.coupon_type, cash.coupon_type) == ("STANDARD", "CASH_BACK")
    # Eligibility, quantity and size conditions, word for word.
    assert coupon.description == (
        "Save $10.00 on any TWO (2) Purina ONE Dry Dog Food bags (8 lb or larger) or Wet Dog Food 12-count "
        "packages (13 oz cans). Mix or match."
    )
    # The legal copy behind "Show More": redemption limits and restrictions, as displayed.
    assert coupon.legal.startswith("NOT FOR RESALE.")
    assert "Limit of one coupon per household." in coupon.legal
    # The expiry as displayed: no year is invented; days left is relative to the observation.
    assert (coupon.expiry_text, coupon.days_left_text) == ("Exp. Nov. 10", "4 days left!")
    assert (coupon.action, cash.action) == ("Sign In To Clip", "Sign In for Cash Back")
    assert coupon.qualifying_upcs == (PURINA,)
    assert coupon.terms.startswith(coupon.description) and coupon.terms.endswith(coupon.legal)


def test_an_unrendered_product_page_shows_no_coupon_and_proves_nothing() -> None:
    s = parse_pdp_savings(page(UNRENDERED))
    assert not s.section and s.rows == ()
    idx = index({PURINA_LAMB: (UNRENDERED, False)})
    read = idx.terms_read(PURINA_LAMB)
    assert read is not None and read.rendered is False and read.coupon_ids == ()
    assert idx.coupons_for(PURINA_LAMB) == []


def test_a_sale_row_is_a_promotion_not_a_coupon() -> None:
    # Server-rendered, so present although the provider did not run the page's scripts.
    s = parse_pdp_savings(page(SALE))
    assert [(r.row_kind, r.tag, r.coupon_id, r.headline, r.expiry_text) for r in s.rows] == [
        ("must-buy", "Sale", "", "Buy 1 Save $2", "Exp. Jan. 05")
    ]
    assert not s.rows[0].is_coupon and s.coupons() == []
    idx = index({NUTRL: (SALE, False)})
    read = idx.terms_read(NUTRL)
    assert read is not None and read.other_rows == ("Buy 1 Save $2",) and idx.coupons_for(NUTRL) == []


def test_a_coupon_attaches_only_to_the_product_whose_page_shows_it() -> None:
    idx = index({PURINA: (RENDERED, True)})
    assert [c.coupon_id for c in idx.coupons_for(PURINA)] == ["4257015", "4257014"]
    # Another Purina ONE product: the same brand and headline do not make the coupon its own.
    assert idx.coupons_for(PURINA_LAMB) == []
    c = idx.coupons_for(PURINA)[0]
    assert c.relation == "shown in the product's own Savings section; listed among its Qualifying Products"
    assert c.as_dict()["locators"]["expiry"] == '[data-testid="CouponExpiryDate-4257015"]'


def test_the_same_page_unrendered_gives_no_coupon() -> None:
    # The rendered page's content with the provider's statement that it was not rendered: nothing is linked.
    assert index({PURINA: (RENDERED, False)}).coupons_for(PURINA) == []
    assert index({PURINA: (RENDERED, None)}).coupons_for(PURINA) == []


# -- the record ------------------------------------------------------------------------------------------


def test_the_card_coupon_gets_its_complete_terms_and_no_price(
    cards: dict[str, CardObservation], build: Any
) -> None:
    card = cards[PURINA]
    assert card.zone is not None and (card.zone.label, card.zone.text) == (
        "Coupon",
        "Save $10.00 on 2 Purina ONE",
    )
    b = build(card, index({PURINA: (RENDERED, True)})).built
    desc = b.record["digital_deals_description"]
    assert desc.startswith(
        "Coupon: Save $10.00 on 2 Purina ONE — Save $10.00 on any TWO (2) Purina ONE Dry Dog Food bags "
        "(8 lb or larger) or Wet Dog Food 12-count packages (13 oz cans). Mix or match. NOT FOR RESALE."
    )
    assert "Limit of one coupon per household." in desc
    assert desc.endswith("(Exp. Nov. 10; Sign In To Clip)")
    # Savings wording: no price is derived (no subtraction, no division by the quantity).
    assert b.record["digital_deals_price"] == ""
    assert "states a discount or no final price" in b.missing["digital_deals_price"]
    assert RecordFlag.DIGITAL_TERMS_UNREAD not in b.flags
    # The zone and the page show the same coupon: one offer, both sightings kept.
    digital = [c for c in b.deals.classified if c.kind is OfferKind.DIGITAL]
    assert len(digital) == 1 and digital[0].offer.coupon_id == "4257015"
    assert set(digital[0].offer.sources) == {OfferSource.ZONE, OfferSource.PDP}
    # The cash-back coupon is kept in the supporting files, not in the digital fields (settings).
    assert RecordFlag.CASHBACK_OFFER_EXCLUDED in b.flags and "Cash Back" not in desc
    assert b.status is RecordStatus.VALID


def test_without_the_page_the_headline_alone_is_kept_and_flagged(
    cards: dict[str, CardObservation], build: Any
) -> None:
    for upc, idx in ((PURINA, index()), (PURINA_LAMB, index({PURINA_LAMB: (UNRENDERED, False)}))):
        b = build(cards[upc], idx).built
        assert b.record["digital_deals_description"] == "Coupon: Save $10.00 on 2 Purina ONE"
        assert b.record["digital_deals_price"] == ""
        assert RecordFlag.DIGITAL_TERMS_UNREAD in b.flags
    e = build(cards[ENERGIZER], index()).built
    assert e.record["digital_deals_description"] == "Coupon: Save $1.00 on Energizer"
    assert e.record["digital_deals_price"] == "" and RecordFlag.DIGITAL_TERMS_UNREAD in e.flags


def _hand_made(upc: str, headline: str, terms: str) -> dict[str, Any]:
    """A hand-made Savings document (not a capture): the Temptations page was never brought rendered."""
    return {
        "data": {
            "upc": upc,
            "rendered": True,
            "section": True,
            "rows": [
                {
                    "row_kind": "other-coupon",
                    "tag": "Coupon",
                    "coupon_id": "9999001",
                    "headline": headline,
                    "description": terms,
                    "legal": "Limit of one coupon per household.",
                    "expiry_text": "Exp. Nov. 09",
                    "days_left_text": "",
                    "action": "Sign In To Clip",
                    "qualifying_upcs": [upc],
                    "locators": {},
                }
            ],
        }
    }


def test_an_explicit_coupon_price_needs_its_terms(cards: dict[str, CardObservation], build: Any) -> None:
    card = cards[TEMPTATIONS]
    assert card.zone is not None and card.zone.text == "$6.99 Temptations Cat Treats"
    # Q2's export (1.8.0rc4) had "6.99" from the card's headline alone; 1.9.0 needs the coupon's terms.
    bare = build(card, index()).built
    assert bare.record["digital_deals_price"] == "" and RecordFlag.DIGITAL_TERMS_UNREAD in bare.flags
    assert "complete terms were not read" in bare.missing["digital_deals_price"]
    one = _hand_made(TEMPTATIONS, "$6.99 Temptations Cat Treats", "Buy ONE (1) Temptations Cat Treats 16 oz.")
    priced = build(card, index(docs={TEMPTATIONS: one})).built
    assert priced.record["digital_deals_price"] == "6.99"
    assert RecordFlag.DIGITAL_TERMS_UNREAD not in priced.flags
    assert priced.record["digital_deals_description"].endswith("(Exp. Nov. 09; Sign In To Clip)")


def test_a_coupon_of_another_product_or_wording_does_not_merge(
    cards: dict[str, CardObservation], build: Any
) -> None:
    # The page's coupon has other wording than the card's: both are kept, neither replaces the other.
    other = _hand_made(TEMPTATIONS, "Save $1.00 on Temptations", "Save $1.00 on any ONE (1) Temptations.")
    b = build(cards[TEMPTATIONS], index(docs={TEMPTATIONS: other})).built
    texts = sorted(c.offer.text for c in b.deals.classified if c.kind is OfferKind.DIGITAL)
    assert texts == ["$6.99 Temptations Cat Treats", "Save $1.00 on Temptations"]
    # The card's headline still has no terms: its price stays out.
    assert b.record["digital_deals_price"] == "" and RecordFlag.DIGITAL_TERMS_UNREAD in b.flags


def test_an_expiry_without_a_year_stays_as_displayed(cards: dict[str, CardObservation], build: Any) -> None:
    b = build(cards[PURINA], index({PURINA: (RENDERED, True)})).built
    digital = next(c for c in b.deals.classified if c.kind is OfferKind.DIGITAL)
    assert digital.offer.expiry_text == "Exp. Nov. 10" and "2026" not in b.record["digital_deals_description"]


# -- M3: the displayed price per measure ----------------------------------------------------------------


def _check(quantity: str, unit: str) -> SourceCheck:
    return SourceCheck(response={"kind": "products_v2"}, size_quantity=quantity, size_unit=unit)


def test_ppm_equal_to_the_item_price_on_a_multi_unit_pack_is_an_anomaly() -> None:
    # UPC 0084024314377: "$19.99/oz" on a $19.99 pack of 12 x 2.6 oz (31.2 OUNCES), as displayed.
    assert ppm_source_anomalies("$19.99/oz", ("19.99", ""), _check("31.2", "OUNCES")) == [
        RecordFlag.PPM_EQUALS_ITEM_PRICE
    ]


def test_ppm_in_a_measure_for_a_pack_stated_as_a_count_is_an_anomaly() -> None:
    # UPC 0001280052496 (Headlight): "$7.99/oz" with a $7.99 sale on a product whose data states 1 EACH.
    assert ppm_source_anomalies("$7.99/oz", ("10.49", "7.99"), _check("1", "EACH")) == [
        RecordFlag.PPM_UNIT_FAMILY_MISMATCH
    ]
    # And a count unit for a pack stated as a weight (Q2 census: "$8.99/each" on 3.15 POUNDS).
    assert ppm_source_anomalies("$8.99/each", ("8.99", ""), _check("3.15", "POUNDS")) == [
        RecordFlag.PPM_EQUALS_ITEM_PRICE,
        RecordFlag.PPM_UNIT_FAMILY_MISMATCH,
    ]


def test_an_ordinary_ppm_or_one_without_product_data_is_not_flagged() -> None:
    assert ppm_source_anomalies("$0.56/oz", ("4.99", ""), _check("8.9", "OUNCES")) == []
    assert ppm_source_anomalies("$1.82/lb", ("7.99", ""), _check("4.4", "POUNDS")) == []
    assert ppm_source_anomalies("$19.99/oz", ("19.99", ""), None) == []
    assert (
        ppm_source_anomalies("$19.99/oz", ("19.99", ""), replace(_check("31.2", "OUNCES"), response=None))
        == []
    )
    assert ppm_source_anomalies("", ("19.99", ""), _check("31.2", "OUNCES")) == []
