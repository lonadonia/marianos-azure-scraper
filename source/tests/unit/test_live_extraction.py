"""Regression tests for the extraction failures found in run 01M5BWAPJ0RF9972ZF8G87REVE (2026-10-20).

The cards and the product and coupon responses under tests/fixtures/live_2026-10-20 were saved by that
live run (trimmed to what the extraction reads); here they are fixture data, run through the same code as
the live collector (:func:`marianos_headless.collection.live.build_card`).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from marianos_headless.acquisition.capture import classify_url
from marianos_headless.assembly.offers import OfferKind
from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import CategoryAssignment, RecordStatus, StoreFields
from marianos_headless.collection.live import CardBuild, build_card, grid_cards
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.schema import OUTPUT_FIELDS
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig
from marianos_headless.sites.marianos.dom_parsers import CardObservation, PriceDisplayKind
from marianos_headless.sites.marianos.source_json import (
    COUPONS,
    PRODUCTS,
    ResponseRef,
    SourceIndex,
    expiry_text,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "live_2026-10-20"
RUSSET, GRAPES, POMEGRANATE, BOGO = "0001111018214", "0001111061375", "0000000003127", "0001111079547"
LIMES, BOLTHOUSE, BANANAS, HERDEZ = "0000000004205", "0007146402284", "0000000004011", "0007287886572"
BEEF, ONE_SLOT = "0086344100002", "0003338320027"
STORE = StoreFields(
    "60601",
    "Marianos Lakeshore East",
    "333 E Benton Pl, CHICAGO, IL 60601",
    "https://www.marianos.com/logo.svg",
)


@pytest.fixture(scope="module")
def cards() -> dict[str, CardObservation]:
    grid, parsed, _, _ = grid_cards((FIX / "grid_cards.html").read_text("utf-8"))
    assert grid
    return {c.upc or "": c for c in parsed}


def sources(
    *,
    products: bool = True,
    coupons: bool = True,
    edit: Any = None,
    coupon_upcs: dict[str, str] | None = None,
) -> SourceIndex:
    """The saved responses; ``edit`` changes the products response, ``coupon_upcs`` gives a coupon (by ID)
    one more qualifying product."""
    idx = SourceIndex()
    if products:
        doc = json.loads((FIX / "products_v2.json").read_text("utf-8"))
        if edit is not None:
            edit(doc)
        idx.add(PRODUCTS, json.dumps(doc), ResponseRef(PRODUCTS, "F1", "a" * 64, "2026-10-20T05:26:00Z"))
    if coupons:
        doc = json.loads((FIX / "coupons.json").read_text("utf-8"))
        for c in doc["data"]["coupons"]:
            if str(c["id"]) in (coupon_upcs or {}):
                c["upcs"] = [*c["upcs"], (coupon_upcs or {})[str(c["id"])]]
        idx.add(COUPONS, json.dumps(doc), ResponseRef(COUPONS, "F1", "b" * 64, "2026-10-20T05:26:00Z"))
    return idx


@pytest.fixture
def build(settings: Settings, dev_store: StoreConfig, private_label: PrivateLabelConfig) -> Any:
    detector = PrivateLabelDetector(private_label, settings.records.store_brand_positive_value)

    def run(
        card: CardObservation, idx: SourceIndex | None = None, store: StoreConfig | None = None
    ) -> CardBuild:
        return build_card(
            card,
            fetch_id="F1",
            observed_at="2026-10-20T05:26:00+00:00",
            store=store or dev_store,
            store_values=STORE,
            store_provenance={},
            category=CategoryAssignment("Produce", "Fresh Fruit"),
            crawl_date="2026-10-20",
            settings=settings,
            detector=detector,
            sources=idx if idx is not None else sources(),
        )

    return run


# -- weight ---------------------------------------------------------------------------------------------


def test_a_picture_view_name_in_the_size_slot_is_not_a_weight(
    cards: dict[str, CardObservation], build: Any
) -> None:
    card = cards[RUSSET]
    assert card.size_text == "Front"  # what the page shows (the retailer's own size field says "Front")
    b = build(card).built
    assert b.record["weight"] == ""
    assert RecordFlag.SIZE_TEXT_NOT_A_SIZE in b.flags and b.status is RecordStatus.VALID
    assert "'Front'" in b.missing["weight"] and "picture" in b.missing["weight"]


def test_real_sizes_and_the_approximate_weight_exclusion_are_kept(
    cards: dict[str, CardObservation], build: Any
) -> None:
    assert build(cards[BOLTHOUSE]).built.record["weight"] == "12 oz"
    assert build(cards[ONE_SLOT]).built.record["weight"] == "1 lb"
    approx = build(replace(cards[ONE_SLOT], size_text="approx. 1.5 lb")).built
    assert approx.status is RecordStatus.EXCLUDED and RecordFlag.APPROX_WEIGHT in approx.reasons


# -- coupons ------------------------------------------------------------------------------------------


def test_the_coupon_zone_text_has_no_button_label(cards: dict[str, CardObservation]) -> None:
    zone = cards[GRAPES].zone
    assert zone is not None
    assert (zone.label, zone.text) == ("Coupon", "$4.99 Kroger Seedless Grapes")
    assert zone.requires_clip and zone.details and zone.checkbox_label == "$4.99 Kroger Seedless Grapes"
    assert "View Offer" not in zone.text


def test_a_coupon_gets_its_view_offer_terms_and_its_final_price(
    cards: dict[str, CardObservation], build: Any
) -> None:
    b = build(cards[GRAPES]).built
    desc = b.record["digital_deals_description"]
    assert desc.startswith("Coupon: $4.99 Kroger Seedless Grapes — When You Buy ONE (1) Kroger Red, Green")
    assert "Use up to 5 times per transaction" in desc and "October 14-October 20 only" in desc
    assert desc.endswith("(Exp. 10/20/2026)") and "View Offer" not in desc
    assert b.record["digital_deals_price"] == "4.99"  # "$4.99 <product>" is the price with the coupon
    assert b.record["regular_price"] == "7.49"  # the displayed price, untouched
    assert b.record["volume_deals_description"] == b.record["volume_deals_price"] == ""
    assert "_offer_details_4251508" in b.provenance and b.source_check["result"] == "PASS"


def test_without_the_coupon_response_the_card_text_alone_is_kept_clean(
    cards: dict[str, CardObservation], build: Any
) -> None:
    b = build(cards[GRAPES], sources(coupons=False)).built
    assert b.record["digital_deals_description"] == "Coupon: $4.99 Kroger Seedless Grapes"
    assert b.record["digital_deals_price"] == "4.99"


def test_a_discount_coupon_or_cash_back_never_sets_a_price(
    cards: dict[str, CardObservation], build: Any
) -> None:
    # The saved "SAVE $0.50 on Totino's" and "$0.50 Cash Back" coupons, listed for a product without a zone.
    idx = sources(coupon_upcs={"4248723": ONE_SLOT, "4248722": ONE_SLOT})
    b = build(cards[ONE_SLOT], idx).built
    assert b.record["digital_deals_description"].startswith("SAVE $0.50 on Totino")
    assert b.record["digital_deals_price"] == ""
    assert "Cash Back" not in b.record["digital_deals_description"]
    assert RecordFlag.CASHBACK_OFFER_EXCLUDED in b.flags
    assert "states a discount or no final price" in b.missing["digital_deals_price"]


def test_a_coupon_price_not_below_the_shown_price_is_not_a_final_price(
    cards: dict[str, CardObservation], build: Any
) -> None:
    card = cards[GRAPES]
    cheaper = replace(card, price=replace(card.price, regular_price="3.99"))
    b = build(cheaper).built
    assert b.record["digital_deals_price"] == "" and RecordFlag.DEAL_PRICE_NOT_BELOW_PRICE in b.flags
    assert b.record["digital_deals_description"].startswith("Coupon: $4.99 Kroger Seedless Grapes")


def test_a_coupon_needing_several_units_has_no_headline_price(
    cards: dict[str, CardObservation], build: Any
) -> None:
    idx = sources()
    idx.coupons["4251508"] = replace(idx.coupons["4251508"], quantity=2)
    assert build(cards[GRAPES], idx).built.record["digital_deals_price"] == ""


def test_a_pickup_only_coupon_the_card_does_not_show_stays_out_of_an_in_store_record(
    cards: dict[str, CardObservation], build: Any
) -> None:
    # "Save 20% on Private Selection Potatoes PICKUP OR DELIVERY ONLY" (live: listed for other potatoes).
    idx = sources(coupon_upcs={"4247050": BOGO})
    assert set(idx.coupons["4247050"].modalities) == {"PICKUP", "DELIVERY"}
    cb = build(cards[BOGO], idx)
    assert "Save 20%" not in cb.built.record["digital_deals_description"]
    assert cb.built.record["digital_deals_description"] == ""
    assert any("PICKUP OR DELIVERY ONLY" in n and "not IN_STORE" in n for n in cb.details.notes)
    assert "_offers_left_out" in cb.built.provenance


def test_points_offers_stay_out_by_default(cards: dict[str, CardObservation], build: Any) -> None:
    b = build(cards[ONE_SLOT], sources(coupon_upcs={"4250208": ONE_SLOT})).built  # "Earn 4X Points on …"
    assert b.record["digital_deals_description"] == "" and RecordFlag.POINTS_OFFER_EXCLUDED in b.flags
    assert "points offer" in b.missing["digital_deals_description"]


# -- volume deals -------------------------------------------------------------------------------------


def test_a_bundle_price_is_kept_with_its_validity(cards: dict[str, CardObservation], build: Any) -> None:
    b = build(cards[POMEGRANATE]).built
    # promo.expirationDate 2026-10-21T03:59:59.999Z is the end of Oct 20 at the store (Chicago).
    assert b.record["volume_deals_description"] == "2 For $4.00 (Exp. 10/20/2026)"
    assert b.record["volume_deals_price"] == "4.00"
    assert b.record["digital_deals_description"] == b.record["digital_deals_price"] == ""


def test_buy_one_get_one_has_no_price_and_volume_stays_apart_from_digital(
    cards: dict[str, CardObservation], build: Any
) -> None:
    b = build(cards[BOGO]).built
    assert b.record["volume_deals_description"] == "Buy 1, Get 1 Free (Exp. 10/20/2026)"
    assert b.record["volume_deals_price"] == ""
    assert "states no final price" in b.missing["volume_deals_price"]
    kinds = {c.kind for c in b.deals.classified}
    assert OfferKind.DIGITAL not in kinds


def test_a_save_when_you_buy_offer_is_text_only_and_the_sale_price_is_kept(
    cards: dict[str, CardObservation], build: Any
) -> None:
    b = build(cards[HERDEZ]).built
    assert b.record["volume_deals_description"] == "Save $1 each when you buy 5 or more (Exp. 10/27/2026)"
    assert b.record["volume_deals_price"] == ""
    assert (b.record["regular_price"], b.record["sale_price"]) == ("8.99", "7.49")


def test_coupon_and_sale_on_the_same_card(cards: dict[str, CardObservation], build: Any) -> None:
    b = build(cards[BEEF]).built
    assert (b.record["regular_price"], b.record["sale_price"]) == ("10.99", "9.99")
    assert b.record["digital_deals_price"] == "7.99"
    assert b.record["digital_deals_description"].startswith("Coupon: $7.99 Pre Ground Beef, 95% Lean — ")


# -- price per measure --------------------------------------------------------------------------------


def test_the_displayed_price_per_measure_is_kept_and_matches_the_sites_own_text(
    cards: dict[str, CardObservation], build: Any
) -> None:
    b = build(cards[BOLTHOUSE]).built
    assert b.record["ppm"] == "$0.29/fl oz"  # on sale: the card shows the sale price's PPM
    assert RecordFlag.PPM_DOM_JSON_MISMATCH not in b.flags
    assert b.source_check["unit_price_text"] == ["$0.29/fl oz", "$0.45/fl oz"]  # promo, regular


def test_a_missing_price_per_measure_stays_empty_with_its_reason(
    cards: dict[str, CardObservation], build: Any
) -> None:
    b = build(cards[ONE_SLOT]).built
    assert b.record["ppm"] == "" and RecordFlag.PPM_NOT_DISPLAYED in b.flags
    assert b.missing["ppm"].endswith("the site's product response has none either")
    b2 = build(cards[ONE_SLOT], sources(products=False)).built
    assert "no product response was captured" in b2.missing["ppm"]


def test_a_product_sold_by_weight_is_kept_with_its_ppm_and_no_fixed_price(
    cards: dict[str, CardObservation], build: Any
) -> None:
    """Release 1.4.0 (client feedback of 2026-10-29): selling by weight is not the approximate-weight
    exclusion. The displayed price per pound is the PPM; the estimated item price is never exported as a
    fixed price, and no weight is invented."""
    b = build(cards[BANANAS]).built
    assert b.status is RecordStatus.ELIGIBLE_UNPRICED and b.exported
    assert not b.reasons and RecordFlag.RELATIVE_PRICE in b.flags
    assert RecordFlag.ESTIMATED_PRICE_ONLY in b.flags and RecordFlag.SOLD_BY_WEIGHT in b.flags
    assert b.record["ppm"] == "$0.69/lb" and b.record["weight"] == ""
    assert b.record["regular_price"] == b.record["sale_price"] == ""
    assert "estimated item price" in b.missing["regular_price"]
    est = b.provenance["_estimated_price"]
    assert est["per_unit_price_displayed"] == "$0.69/lb" and est["estimated_regular"]


def test_a_product_sold_by_weight_whose_weight_is_a_range_is_excluded_as_approximate_weight(
    cards: dict[str, CardObservation], build: Any
) -> None:
    """Release 1.5.0 (the Jennie-O turkeys 1.4.0 retained flagged): the size slot shows the price per pound,
    so no weight is displayed; the product's own data for the store gives its size as "10-14 lb". The weight
    is approximate: excluded (APPROX_WEIGHT) with the wording and its source; the weight stays empty, no
    weight is invented and the PPM is still the displayed one."""

    def turkey_size(doc: dict[str, Any]) -> None:
        for p in doc["data"]["products"]:
            if p["item"]["upc"] == BANANAS:
                p["item"]["customerFacingSize"] = "10-14 lb"

    turkey = replace(cards[BANANAS], title="Frozen Whole Turkey 10-14 lb")
    b = build(turkey, sources(edit=turkey_size)).built
    assert b.status is RecordStatus.EXCLUDED and b.reasons == (RecordFlag.APPROX_WEIGHT,)
    assert b.record["weight"] == "" and b.record["ppm"] == "$0.69/lb"
    assert b.provenance["_approx_weight"]["source"] == "product_data_size"
    assert b.provenance["_approx_weight"]["wording"] == "10-14 lb"
    # Without the product response, the name's range alone is the source.
    b2 = build(turkey, sources(products=False)).built
    assert b2.reasons == (RecordFlag.APPROX_WEIGHT,) and b2.provenance["_approx_weight"]["source"] == "title"
    # Bananas themselves ("1 lb" pricing unit, no range) stay exported.
    assert build(cards[BANANAS]).built.status is RecordStatus.ELIGIBLE_UNPRICED


# -- unavailable products, store and fulfillment ------------------------------------------------------


def test_prices_may_vary_on_a_grid_card_is_an_unavailable_product_kept_for_export(
    cards: dict[str, CardObservation], build: Any
) -> None:
    card = cards[LIMES]
    assert (card.price.kind, card.price.placeholder_text) == (
        PriceDisplayKind.NOT_DISPLAYED,
        "Prices May Vary",
    )
    b = build(card).built
    assert b.status is RecordStatus.ELIGIBLE_UNPRICED and b.exported
    assert b.record["regular_price"] == b.record["sale_price"] == ""
    assert "'Prices May Vary'" in b.missing["regular_price"]
    assert "TEMPORARILY_OUT_OF_STOCK" in b.missing["regular_price"]
    # The stock level comes from the product's own data, not from the missing price.
    assert b.provenance["_availability"]["availability"] == "out_of_stock"


def test_prices_may_vary_alone_is_not_proof_of_out_of_stock(
    cards: dict[str, CardObservation], build: Any
) -> None:
    b = build(cards[LIMES], sources(products=False)).built
    assert b.status is RecordStatus.ELIGIBLE_UNPRICED and b.exported
    assert b.provenance["_availability"]["availability"] == "unknown"


def test_the_stock_level_comes_from_the_inventory_summaries_of_2026_10_23(
    cards: dict[str, CardObservation], build: Any
) -> None:
    """In the live responses of 2026-10-23 (runs 01M5MHSN and 01M5NAQK) some products state their stock
    only per fulfillment type, in ``inventorySummaries[]``, without ``inventory.locations[]``: the In Store
    level of the store counts, not the Pickup one (found in the 1.2.1 review: 93 of the 183 products both runs
    saw had no stock level in their supporting log)."""

    def summaries(doc: dict[str, Any]) -> None:
        for p in doc["data"]["products"]:
            if p["item"]["upc"] == LIMES:
                p.pop("inventory", None)
                p["inventorySummaries"] = [
                    {
                        "modalityType": "PICKUP",
                        "details": [{"sourceId": "53100503", "availableToSell": 9999, "stockLevel": "HIGH"}],
                    },
                    {
                        "modalityType": "IN_STORE",
                        "details": [
                            {
                                "sourceId": "53100503",
                                "availableToSell": 0,
                                "stockLevel": "TEMPORARILY_OUT_OF_STOCK",
                            }
                        ],
                    },
                ]

    b = build(cards[LIMES], sources(edit=summaries)).built
    assert b.source_check["stock_level"] == "TEMPORARILY_OUT_OF_STOCK"
    assert "TEMPORARILY_OUT_OF_STOCK" in b.missing["regular_price"]


def test_a_price_for_another_store_in_the_sites_response_excludes_the_record(
    cards: dict[str, CardObservation], build: Any
) -> None:
    def elsewhere(doc: dict[str, Any]) -> None:
        for p in doc["data"]["products"]:
            if p["item"]["upc"] == POMEGRANATE:
                p["price"]["storePrices"]["sourceLocationId"] = "53100526"

    b = build(cards[POMEGRANATE], sources(edit=elsewhere)).built
    assert b.status is RecordStatus.EXCLUDED and RecordFlag.LOCATION_UNATTESTED in b.reasons
    assert b.source_check["result"] == "FAIL" and b.source_check["location_ok"] is False


def test_a_fulfillment_the_response_does_not_offer_is_flagged(
    cards: dict[str, CardObservation], build: Any
) -> None:
    def pickup_only(doc: dict[str, Any]) -> None:
        for p in doc["data"]["products"]:
            p["fulfillmentOptions"] = ["PICKUP"]

    b = build(cards[POMEGRANATE], sources(edit=pickup_only)).built
    assert RecordFlag.MODALITY_NOT_OFFERED in b.flags and b.source_check["modality_ok"] is False


# -- the 22 fields ------------------------------------------------------------------------------------


def test_every_record_has_the_22_fields_in_order_as_strings(
    cards: dict[str, CardObservation], build: Any
) -> None:
    for card in cards.values():
        b = build(card).built
        assert list(b.record) == list(OUTPUT_FIELDS)
        assert all(isinstance(v, str) for v in b.record.values())
        assert b.record["gupc"] == b.record["unit_price"] == ""
        assert b.record["upc"] == card.upc and len(b.record["upc"]) == 13  # leading zeros kept
        assert b.record["url"] == f"https://www.marianos.com/p/{card.url.split('/p/')[1]}"
        assert b.record["image_url"] == f"https://www.kroger.com/product/images/medium/front/{card.upc}"
        assert set(b.missing) == {f for f, v in b.record.items() if not v}  # every empty field explained


# -- capture ------------------------------------------------------------------------------------------


def test_the_coupon_endpoint_of_the_live_site_is_captured_as_coupons() -> None:
    assert (
        classify_url("https://www.marianos.com/atlas/v1/savings-coupons/v2/coupons?filter.upc=1") == "coupons"
    )
    assert classify_url("https://www.marianos.com/atlas/v1/savings-coupons/v1/products/abc") == "atlas_other"
    assert (
        classify_url("https://www.marianos.com/atlas/v1/product/v2/products?filter.gtin13s=1")
        == "products_v2"
    )


def test_expiry_dates_are_the_stores_local_date() -> None:
    assert expiry_text("2026-10-21T03:59:59.999Z", "America/Chicago") == "Exp. 10/20/2026"
    assert expiry_text("2026-10-20T23:59:59Z", "America/Chicago") == "Exp. 10/20/2026"
    assert expiry_text(None, "America/Chicago") == expiry_text("soon", "America/Chicago") == ""
