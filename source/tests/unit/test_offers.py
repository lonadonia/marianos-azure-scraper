"""Promotion classifier (brief §7). Offer texts are copied from the 2026-10-17 snapshot (FIXTURE)."""

from __future__ import annotations

import pytest

from marianos_headless.assembly.offers import (
    OfferKind,
    OfferObservation,
    OfferSource,
    classify,
    derive_deal_fields,
    extract_explicit_price,
    restriction_reason,
)
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import DealDescriptionFormat, OtherPromoTarget, RecordSettings

S = RecordSettings()


def zone(text: str, clip: bool) -> OfferObservation:
    return OfferObservation(OfferSource.ZONE, text, 0, clip_checkbox=clip)


def drawer(text: str, tag: str, order: int, expiry: str = "", coupon: bool = True) -> OfferObservation:
    src = OfferSource.DRAWER_COUPON if coupon else OfferSource.DRAWER_OFFER
    cta = ("Shop All Items", "Sign In To Clip") if coupon else ("Shop Deal",)
    return OfferObservation(src, text, order, tag=tag, ctas=cta, expiry_text=expiry)


# (zone text, clip checkbox) -> (kind, explicit price)
CARD_LEVEL = [
    ("$5.99 Coca-Cola, 7UP or Pepsi", True, OfferKind.DIGITAL, "5.99"),
    ("Save 33% on Halloween Candy", True, OfferKind.DIGITAL, ""),
    ("$8.99 each when you buy 2 or more", False, OfferKind.VOLUME, "8.99"),
    ("Save $1 each when you buy 5 or more", False, OfferKind.VOLUME, ""),
    ("2 For $5.00", False, OfferKind.VOLUME, "5.00"),
    ("2 For $4.00", False, OfferKind.VOLUME, "4.00"),
    ("3 For $5.00", False, OfferKind.VOLUME, "5.00"),
    ("4/$10 when you buy 4 or more", False, OfferKind.VOLUME, "10.00"),
    ("Buy 1, Get 1 Free", False, OfferKind.VOLUME, ""),
    ("Buy 2 Get 1 Free", False, OfferKind.VOLUME, ""),
    ("Buy 3 Get 3 Free. Limit 12 Packages.", False, OfferKind.VOLUME, ""),
    ("15% off when you Buy 4, Mix or Match Bottles", False, OfferKind.VOLUME, ""),
    ("$3.99 Tillamook Ice Cream", True, OfferKind.DIGITAL, "3.99"),
    ("Save $5.00 on Michelob ULTRA PICKUP OR DELIVERY ONLY", True, OfferKind.DIGITAL, ""),
    (
        "Earn 4X Points on Frozen Food and Dairy Purchases on 10/14 -10/20. Points will load within 24 hrs",
        True,
        OfferKind.POINTS,
        "",
    ),
    ("$2.49 Each, Limit 5, Saturday thru Monday", False, OfferKind.OTHER_PROMO, ""),
    ("$1.99 lb Pork Tenderloin", True, OfferKind.DIGITAL, "1.99"),
    ("$6.99 lb Angus Chuck Roast", True, OfferKind.DIGITAL, "6.99"),
]


@pytest.mark.parametrize(("text", "clip", "kind", "price"), CARD_LEVEL)
def test_card_level_classification(text: str, clip: bool, kind: OfferKind, price: str) -> None:
    c = classify(zone(text, clip), "IN_STORE")
    assert c.kind is kind
    assert c.explicit_price == price


def test_points_offer_tagged_coupon_is_still_points() -> None:
    c = classify(
        drawer(
            "FRI-SUN 2X Points on Purchases 10/16 - 10/18 excluding Gift Cards. Points load within 24 hrs",
            "Coupon",
            0,
        ),
        "IN_STORE",
    )
    assert c.requires_clip and c.kind is OfferKind.POINTS


def test_cash_back_never_digital_price() -> None:
    c = classify(
        drawer("$1.00 Cash Back on 2 Pillsbury™ Refrigerated and Frozen Products", "Cash Back", 0), "IN_STORE"
    )
    assert c.kind is OfferKind.CASHBACK
    assert c.explicit_price == ""


def test_sale_with_shop_deal_is_not_clip() -> None:
    c = classify(drawer("2 For $5.00", "Sale", 0, coupon=False), "IN_STORE")
    assert not c.requires_clip and c.kind is OfferKind.VOLUME and c.explicit_price == "5.00"


def test_word_number_combo_deal_is_volume_without_price() -> None:
    c = classify(
        drawer(
            "Buy One Grab & Go Sandwich, Get One Coke 20 oz for $2 & One Kroger Chips Free",
            "Sale",
            0,
            coupon=False,
        ),
        "IN_STORE",
    )
    assert c.kind is OfferKind.VOLUME and c.explicit_price == ""


@pytest.mark.parametrize(
    ("text", "kind", "price"),
    [
        ("Must buy 4: $1.99 each", OfferKind.VOLUME, "1.99"),
        ("$3.99 each with Digital Coupon", OfferKind.DIGITAL, "3.99"),
        ("$5.00 off your purchase", OfferKind.DIGITAL, ""),
        ("$30 off your first Pickup or Delivery Order of $75 +", OfferKind.DIGITAL, ""),
        ("Save $30.00 When You Spend $75.00", OfferKind.DIGITAL, ""),
        ("20% off with clipped coupon", OfferKind.DIGITAL, ""),
        ("Save $5 when you buy 5 with Digital Coupon", OfferKind.DIGITAL, ""),
    ],
)
def test_explicit_price_patterns(text: str, kind: OfferKind, price: str) -> None:
    assert extract_explicit_price(text, kind)[0] == price


def test_a_pickup_or_delivery_only_offer_is_left_out_of_in_store_fields_with_its_reason() -> None:
    """Brief §8 (release 1.4.0): excluded from In Store product offers, the reason kept for the log."""
    d = derive_deal_fields(
        [zone("Save $5.00 on Michelob ULTRA PICKUP OR DELIVERY ONLY", True)], S, "IN_STORE"
    )
    assert d.digital_deals_description == d.digital_deals_price == ""
    assert RecordFlag.MODALITY_RESTRICTED_OFFER in d.flags
    (c,) = d.classified
    reason = restriction_reason(c)
    assert reason is not None and "DELIVERY / PICKUP" in reason
    pickup = derive_deal_fields(
        [zone("Save $5.00 on Michelob ULTRA PICKUP OR DELIVERY ONLY", True)], S, "PICKUP"
    )
    assert RecordFlag.MODALITY_RESTRICTED_OFFER not in pickup.flags
    assert pickup.digital_deals_description == "Save $5.00 on Michelob ULTRA PICKUP OR DELIVERY ONLY"
    assert restriction_reason(pickup.classified[0]) is None


@pytest.mark.parametrize("label", ["Family Pack", "Value Pack", "Family Size"])
def test_a_pack_label_is_not_a_volume_deal(label: str) -> None:
    """Brief §8: a family-pack label is a size fact, not a volume deal."""
    d = derive_deal_fields([zone(label, False)], S, "IN_STORE")
    assert d.volume_deals_description == d.volume_deals_price == ""
    assert classify(zone(label, False), "IN_STORE").kind is not OfferKind.VOLUME


@pytest.mark.parametrize("text", ["Save $1.50", "Save 25%", "$1.00 Cash Back on 2", "Buy 1, Get 1 Free"])
def test_no_price_is_calculated_from_savings(text: str) -> None:
    """Brief §8: no price from savings, percentages, BOGO or cash back."""
    for clip in (True, False):
        d = derive_deal_fields([zone(text, clip)], S, "IN_STORE")
        assert d.volume_deals_price == d.digital_deals_price == ""


def test_cottonelle_drawer_golden() -> None:
    """Brief §7.3: the drawer set observed for Cottonelle, in display order, plus the card zone."""
    offers = [
        zone("$8.99 Cottonelle Bath Tissue", True),
        drawer("$8.99 Cottonelle Bath Tissue", "Weekly Digital Deal", 0, "Exp. Oct. 20"),
        drawer("$2.00 Cash Back on Cottonelle", "Cash Back", 1, "Exp. Oct. 24"),
        drawer("Save $2.00 on Cottonelle", "Coupon", 2, "Exp. Oct. 24"),
    ]
    d = derive_deal_fields(offers, S, "IN_STORE")
    assert d.digital_deals_description == (
        "Weekly Digital Deal: $8.99 Cottonelle Bath Tissue (Exp. Oct. 20) | "
        "Coupon: Save $2.00 on Cottonelle (Exp. Oct. 24)"
    )
    assert d.digital_deals_price == "8.99"
    assert d.volume_deals_description == "" and d.volume_deals_price == ""
    assert RecordFlag.CASHBACK_OFFER_EXCLUDED in d.flags
    assert RecordFlag.OFFER_TAG_UNOBSERVED not in d.flags  # the drawer supplied the tag


def test_multiple_digital_prices_leave_price_empty() -> None:
    offers = [
        drawer("$5.99 Coca-Cola, 7UP or Pepsi", "Weekly Digital Deal", 0),
        drawer("$4.99 Coca-Cola 12 pk", "Coupon", 1),
    ]
    d = derive_deal_fields(offers, S, "IN_STORE")
    assert d.digital_deals_price == ""
    assert RecordFlag.MULTIPLE_DIGITAL_PRICES in d.flags


def test_volume_and_digital_coexist() -> None:
    offers = [
        drawer("3 For $5.00", "Sale", 0, "Exp. Nov. 02", coupon=False),
        drawer("Save 33% on Halloween Candy", "Coupon", 1, "Exp. Oct. 20"),
    ]
    d = derive_deal_fields(offers, S, "IN_STORE")
    assert d.volume_deals_description == "Sale: 3 For $5.00 (Exp. Nov. 02)"
    assert d.volume_deals_price == "5.00"
    assert d.digital_deals_description == "Coupon: Save 33% on Halloween Candy (Exp. Oct. 20)"
    assert d.digital_deals_price == ""


def test_text_only_format_and_other_promo_target() -> None:
    s = RecordSettings(
        deal_description_format=DealDescriptionFormat.TEXT_ONLY,
        other_promo_target=OtherPromoTarget.VOLUME_DESCRIPTION,
    )
    d = derive_deal_fields(
        [drawer("$2.49 Each, Limit 5, Saturday thru Monday", "Sale", 0, "Exp. Oct. 19", coupon=False)],
        s,
        "IN_STORE",
    )
    assert d.volume_deals_description == "$2.49 Each, Limit 5, Saturday thru Monday"
    assert d.volume_deals_price == ""  # never priced: no multi-unit condition
    assert RecordFlag.OTHER_PROMO_UNCLASSIFIED in d.flags


def test_per_weight_flag_only_when_that_price_is_used() -> None:
    d = derive_deal_fields([zone("$1.99 lb Pork Tenderloin", True)], S, "IN_STORE")
    assert d.digital_deals_price == "1.99"
    assert RecordFlag.PER_WEIGHT_DEAL_PRICE in d.flags
