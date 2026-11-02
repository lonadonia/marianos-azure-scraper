"""Client findings of the 1.7.0rc2 review, as regressions (release 1.8.0).

The three products are the client's own: the values are copied from the saved R1 pages of 2026-10-29
(run 01M650QGTRZCPNYSYWFTWGX2SB, Marianos Lakeshore East, In Store; development evidence). Other cases are
synthetic and say so by their names.
"""

from __future__ import annotations

from typing import Any

import pytest

from marianos_headless.assembly.offers import (
    OfferKind,
    OfferObservation,
    OfferSource,
    classify,
    derive_deal_fields,
    is_volume_text,
    offer_terms,
    required_quantity,
    restriction_reason,
)
from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import (
    CategoryAssignment,
    ProductEvidence,
    RecordStatus,
    SourceCheck,
    StoreFields,
    build_product_record,
    missing_kinds,
)
from marianos_headless.assembly.size_evidence import (
    Measure,
    SizeResolution,
    assess_size,
    package_weight_measure,
    parse_size,
    price_basis_measure,
    title_measures,
)
from marianos_headless.collection.retention import why_kind
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.schema import OUTPUT_FIELDS
from marianos_headless.core.settings import PrivateLabelConfig, RecordSettings, Settings
from marianos_headless.sites.marianos.dom_parsers import PriceDisplay, PriceDisplayKind

S = RecordSettings()


def zone(text: str, *, clip: bool = False, **kw: object) -> OfferObservation:
    return OfferObservation(OfferSource.ZONE, text, 0, clip_checkbox=clip, **kw)  # type: ignore[arg-type]


# -- promotions: the client's two findings --------------------------------------------------------------


@pytest.mark.parametrize(
    ("upc", "text"),
    [("0081675102373", "Buy 1 Save $1"), ("0086001079386", "Buy 1 Save $2")],
)
def test_client_buy_one_save_is_not_a_volume_deal(upc: str, text: str) -> None:
    """Cutwater Espresso Martini (4 cans) and Finnish Long Drink (12 cans): one retail unit each. The cans
    inside a pack are not the units of the offer."""
    assert upc
    assert required_quantity(text) == 1
    assert not is_volume_text(text)
    offer = zone(text, expiry_text="Exp. 11/03/2026")
    assert classify(offer, "PICKUP").kind is OfferKind.OTHER_PROMO
    deals = derive_deal_fields([offer], S, "PICKUP")
    assert deals.volume_deals_description == deals.volume_deals_price == ""
    assert deals.digital_deals_description == deals.digital_deals_price == ""
    assert RecordFlag.OTHER_PROMO_UNCLASSIFIED in deals.flags


@pytest.mark.parametrize(
    "text",
    [
        "Buy One Save $1",
        "1/$3",
        "1 For $3.00",
        "Must buy 1: $1.99 each",
        "$3.99 each when you buy 1 or more",
        "Save $1 when you buy 1",
        "Family Pack",
        "Value Pack",
        "12 Pack",
        "Save $1 on 12 oz Cans",
        "$2.49 Each, Limit 5",
        "Save 25%",
    ],
)
def test_single_unit_savings_and_pack_labels_are_not_volume(text: str) -> None:
    assert not is_volume_text(text)
    assert classify(zone(text), "PICKUP").kind is not OfferKind.VOLUME


@pytest.mark.parametrize(
    ("text", "units"),
    [
        ("Buy 2 Save $1", 2),
        ("Buy Two Save $3", 2),
        ("2 For $5.00", 2),
        ("4/$10 when you buy 4 or more", 4),
        ("Must buy 4: $1.99 each", 4),
        ("Save $1 each when you buy 5 or more", 5),
        ("Save $1.00 on 2 General Mills Cereals", 2),
    ],
)
def test_conditions_on_several_units_are_volume(text: str, units: int) -> None:
    assert required_quantity(text) == units
    assert is_volume_text(text)


@pytest.mark.parametrize(
    "text",
    ["Buy 1, Get 1 Free", "Buy 2 Get 1 Free", "BOGO", "Mix & Match 5", "Buy 1 Get 1 50% Off"],
)
def test_genuine_bogo_and_mix_and_match_are_volume(text: str) -> None:
    assert is_volume_text(text)
    assert classify(zone(text), "PICKUP").kind is OfferKind.VOLUME


def test_clipping_a_multibuy_keeps_the_full_condition_in_the_digital_field_only() -> None:
    """A condition on several units with a clip requirement is a digital offer; the volume field stays empty
    and nothing appears twice, whichever sources showed it."""
    text = "Save $1.00 on 2 General Mills Cereals"
    offers = [
        zone(text, clip=True),
        OfferObservation(
            OfferSource.JSON_COUPONS,
            text,
            0,
            coupon_type="STANDARD",
            terms="Must buy 2. Limit 1 use per household.",
            expiry_text="Exp. 11/09/2026",
            quantity=2,
        ),
    ]
    d = derive_deal_fields(offers, S, "PICKUP")
    assert d.volume_deals_description == ""
    assert d.digital_deals_description == (
        f"{text} — Must buy 2. Limit 1 use per household. (Exp. 11/09/2026)"
    )
    assert d.digital_deals_price == ""


@pytest.mark.parametrize(
    "cta", ["Clip", "Sign In To Clip", "Activate", "Load to Card", "Add Coupon", "Save Coupon"]
)
def test_each_coupon_action_makes_an_offer_digital(cta: str) -> None:
    o = OfferObservation(OfferSource.DRAWER_OFFER, "Save $2.00 on Cottonelle", 0, ctas=(cta,))
    assert classify(o, "PICKUP").kind is OfferKind.DIGITAL


@pytest.mark.parametrize("cta", ["Add to Cart", "Shop Deal", "View Offer", "Save to List"])
def test_other_buttons_do_not_make_an_offer_digital(cta: str) -> None:
    o = OfferObservation(OfferSource.DRAWER_OFFER, "Save $2.00 on Cottonelle", 0, ctas=(cta,))
    assert classify(o, "PICKUP").kind is not OfferKind.DIGITAL


@pytest.mark.parametrize("tag", ["Plus Card", "Member Price", "Rewards Member"])
def test_loyalty_membership_alone_is_not_digital(tag: str) -> None:
    o = OfferObservation(OfferSource.ZONE, "$3.99 with Card", 0, tag=tag, clip_checkbox=False)
    assert classify(o, "PICKUP").kind is OfferKind.OTHER_PROMO


@pytest.mark.parametrize(
    "text",
    [
        "Save $2 In Store Only",
        "Save $2 In-Store Only",
        "Save $2 in store purchases only",
    ],
)
def test_an_in_store_only_offer_never_reaches_a_pickup_record(text: str) -> None:
    for clip in (True, False):
        d = derive_deal_fields([zone(text, clip=clip)], S, "PICKUP")
        assert d.digital_deals_description == d.volume_deals_description == ""
        assert RecordFlag.MODALITY_RESTRICTED_OFFER in d.flags
        assert restriction_reason(d.classified[0]) is not None


def test_a_structured_in_store_modality_never_reaches_a_pickup_record() -> None:
    o = OfferObservation(
        OfferSource.JSON_COUPONS, "2 For $5.00", 0, coupon_type="STANDARD", modalities=("IN_STORE",)
    )
    d = derive_deal_fields([o], S, "PICKUP")
    assert d.digital_deals_description == d.digital_deals_price == ""
    assert d.volume_deals_description == d.volume_deals_price == ""


@pytest.mark.parametrize("text", ["Buy 1 Save $1", "Save $2.00", "Save 25%", "Buy 2 Save $3", "BOGO"])
def test_no_promotional_price_is_ever_calculated(text: str) -> None:
    for clip in (True, False):
        d = derive_deal_fields([zone(text, clip=clip)], S, "PICKUP")
        assert d.volume_deals_price == d.digital_deals_price == ""


def test_the_bundle_price_stays_the_total_the_offer_states() -> None:
    d = derive_deal_fields([zone("3 For $5.00")], S, "PICKUP")
    assert d.volume_deals_price == "5.00"  # never 1.67


# -- size: the client's product -------------------------------------------------------------------------

TITLE = "Avocado Green Goddess Dip & Spread 8 oz."


def test_client_serving_is_not_the_pack_size() -> None:
    a = assess_size(
        "2 tbsp",
        title=TITLE,
        pid_quantity=8,
        pid_unit="OUNCES",
        basis=price_basis_measure("4.99", "62.38", "PER OUNCE"),
        package=package_weight_measure("0.5 [lb_av]"),
    )
    assert a.exported == "8 oz"
    assert a.resolution is SizeResolution.SERVING_REPLACED
    assert a.rule == "R3" and "serving" in a.reason
    assert a.observations["displayed"] == "2 tbsp"
    assert a.observations["product_data"] == "8 OUNCES"
    assert a.observations["title"] == TITLE


def evidence(size: str, title: str, check: SourceCheck | None) -> ProductEvidence:
    return ProductEvidence(
        upc="0073679800140",
        url="https://www.marianos.com/p/x/0073679800140",
        title=title,
        size_text=size,
        price=PriceDisplay(PriceDisplayKind.REGULAR, "$4.99", "", "$4.99", "", "4.99", ""),
        offers=(),
        image_url="https://www.kroger.com/product/images/medium/front/0073679800140",
        source_check=check,
    )


def record(size: str, title: str, check: SourceCheck | None):  # type: ignore[no-untyped-def]
    return build_product_record(
        evidence(size, title, check),
        store=StoreFields("60061", "Marianos Vernon Hills", "1720 N Milwaukee Ave", "https://logo"),
        category=CategoryAssignment("Deli", "Dips"),
        crawl_date="2026-11-02",
        settings=S,
        detector=PrivateLabelDetector(PrivateLabelConfig(brands=["Kroger"])),
        configured_modality="PICKUP",
    )


def check(**kw: object) -> SourceCheck:
    base: dict[str, object] = {
        "response": {"kind": "products_v2", "fetch_id": "f", "sha256": None, "observed_at": "t"},
        "store": "53100502",
        "modality": "PICKUP",
        "price_location": "53100502",
        "sold_by": "Unit/Unit",
        "regular_price": "4.99",
        "size": "2 tbsp",
    }
    base.update(kw)
    return SourceCheck(**base)  # type: ignore[arg-type]


def test_client_product_through_the_record_keeps_every_observation_out_of_the_schema() -> None:
    b = record("2 tbsp", TITLE, check(size_quantity="8", size_unit="OUNCES", package_weight="0.5 [lb_av]"))
    assert b.record["weight"] == "8 oz"
    assert RecordFlag.SIZE_CONFLICT_RESOLVED in b.flags
    assert b.provenance["_size_evidence"]["observations"]["displayed"] == "2 tbsp"
    assert b.provenance["_size_evidence"]["rule"] == "R3"
    assert tuple(b.record) == OUTPUT_FIELDS and len(OUTPUT_FIELDS) == 22
    assert "_size_evidence" not in b.record and "weight" not in b.missing


def test_an_unresolved_conflict_leaves_the_size_empty_with_its_observations() -> None:
    b = record("12 oz", "Some Salad Kit", check(size_quantity="6", size_unit="OUNCES", size="12 oz"))
    assert b.record["weight"] == ""
    assert RecordFlag.SIZE_CONFLICT_UNRESOLVED in b.flags
    assert b.missing["weight"].startswith("unresolved size conflict")
    assert b.provenance["_size_evidence"]["observations"]["displayed"] == "12 oz"
    assert b.provenance["_size_evidence"]["observations"]["product_data"] == "6 OUNCES"
    assert b.status is RecordStatus.VALID  # the price is verified; only the size is left empty


def test_a_size_that_agrees_changes_nothing() -> None:
    b = record("8 oz", TITLE, check(size_quantity="8", size_unit="OUNCES", size="8 oz"))
    assert b.record["weight"] == "8 oz"
    assert "_size_evidence" not in b.provenance


def test_approximate_weight_rule_still_reads_the_displayed_size() -> None:
    """A range is never exported as a pack size, and the product stays excluded by its wording."""
    b = record("10-14 lb", "Whole Turkey (10-14 Lb)", check(sold_by="Weight/Unit", size="10-14 lb"))
    assert RecordFlag.APPROX_WEIGHT in b.reasons
    assert b.status is RecordStatus.EXCLUDED


# -- size: the other kinds of conflict (synthetic unless a comment gives a product) --------------------


def test_unit_measure_denominator_is_not_a_pack_size() -> None:
    a = assess_size(
        "1 lb", title="Fresh Yellow Nectarine", pid_quantity=1, pid_unit="POUNDS", sold_by_weight=True
    )
    assert a.exported == ""
    assert a.resolution is SizeResolution.UNIT_DENOMINATOR


def test_one_pound_pack_sold_by_the_unit_stays() -> None:
    a = assess_size("1 lb", title="Sliced Mushrooms", pid_quantity=1, pid_unit="POUNDS", sold_by_weight=False)
    assert a.exported == "1 lb"


@pytest.mark.parametrize(
    "title",
    [
        "Acetaminophen 500 mg Caplets",
        "Round Cake Pan 8 in",
        "Dog Crate up to 22 lb",  # a weight limit: it agrees with neither observation, so it settles nothing
    ],
)
def test_doses_dimensions_and_limits_are_never_pack_measures(title: str) -> None:
    a = assess_size("24 ct", title=title, pid_quantity=1, pid_unit="EACH")
    assert a.exported == "24 ct"
    assert not a.conflict


def test_title_never_reads_a_dose_or_a_dimension() -> None:
    assert title_measures("Acetaminophen 500 mg Caplets") == []
    assert title_measures("Round Cake Pan 8 in") == []
    assert [m.value for m in title_measures("Sauce 8 oz.")] == [8.0]


def test_a_range_in_the_size_is_not_read_as_a_multipack() -> None:
    assert parse_size("10-14 lb") is None


@pytest.mark.parametrize(
    ("displayed", "quantity", "unit"),
    [
        ("4 cans / 12 fl oz", 48, "FLUID OUNCES"),  # Cutwater: 4 cans of 12 fl oz
        ("12 cans / 12 fl oz", 144, "FLUID OUNCES"),  # Finnish Long Drink
        ("6 ct / 2 oz", 12, "OUNCES"),
        ("1/2 gal", 64, "FLUID OUNCES"),
    ],
)
def test_genuine_multipacks_agree_with_their_total(displayed: str, quantity: int, unit: str) -> None:
    a = assess_size(displayed, pid_quantity=quantity, pid_unit=unit)
    assert a.exported == displayed
    assert a.resolution is SizeResolution.AGREE


def test_a_multipack_shown_by_its_unit_keeps_the_displayed_size() -> None:
    a = assess_size(
        "12 fl oz", title="Waterloo Black Cherry Sparkling Water", pid_quantity=96, pid_unit="FLUID OUNCES"
    )
    assert a.exported == "12 fl oz"
    assert a.resolution is SizeResolution.DISPLAYED_KEPT
    assert "multipack" in a.reason


def test_components_of_different_sizes_settle_nothing() -> None:
    """A kit: the name states two component sizes, the product data a third figure."""
    a = assess_size("12 oz", title="Shrimp 8 oz with Sauce 2 oz", pid_quantity=11, pid_unit="OUNCES")
    assert a.exported == ""
    assert a.resolution is SizeResolution.UNRESOLVED


def test_title_card_and_detail_page_conflict_stays_unresolved() -> None:
    a = assess_size("12 oz", title="Coffee 12 oz", pid_quantity=10.5, pid_unit="OUNCES", detail="10.5 oz")
    assert a.exported == ""
    assert a.resolution is SizeResolution.UNRESOLVED


def test_the_detail_page_settles_a_conflict_with_its_own_words() -> None:
    a = assess_size("7 oz", title="Shrimp Tray", pid_quantity=11, pid_unit="OUNCES", detail="11 oz.")
    assert a.exported == "11 oz."
    assert a.resolution is SizeResolution.REPLACED


def test_two_fields_together_settle_a_conflict_but_never_one_alone() -> None:
    one = assess_size("7 ounces", pid_quantity=11, pid_unit="OUNCES", basis=Measure("weight", 11.0, "b"))
    assert one.exported == "" and one.resolution is SizeResolution.UNRESOLVED
    two = assess_size(
        "7 ounces",
        pid_quantity=11,
        pid_unit="OUNCES",
        basis=Measure("weight", 11.0, "b"),
        package=package_weight_measure("0.69 [lb_av]"),
    )
    assert two.exported == "11 oz" and two.resolution is SizeResolution.REPLACED


def test_a_basis_is_never_exported() -> None:
    """Basis and package weight choose between stated sizes: the export is the product data's own figure."""
    a = assess_size(
        "1.11 oz",
        pid_quantity=18.71,
        pid_unit="OUNCES",
        basis=price_basis_measure("6.49", "34.69", "PER OUNCE"),
        package=package_weight_measure("1.17 [lb_av]"),
    )
    assert a.exported == "18.71 oz"


def test_a_serving_alone_leaves_the_size_empty() -> None:
    a = assess_size("2 tbsp", title="Dip")
    assert a.exported == "" and a.resolution is SizeResolution.UNRESOLVED


def test_a_serving_with_a_disagreeing_name_and_data_stays_empty() -> None:
    a = assess_size("2 tbsp", title="Dip 12 oz", pid_quantity=8, pid_unit="OUNCES")
    assert a.exported == "" and a.resolution is SizeResolution.UNRESOLVED


def test_a_count_against_one_each_is_not_a_conflict() -> None:
    a = assess_size("15 CT", pid_quantity=1, pid_unit="EACH")
    assert a.exported == "15 CT" and not a.conflict


def test_size_comes_only_from_the_products_own_observations() -> None:
    """Variants: two sizes of one family are two products. Nothing here reads a sibling, and the function has
    no input through which a sibling's value could arrive."""
    small = assess_size("8 oz", title="Dip", pid_quantity=8, pid_unit="OUNCES")
    large = assess_size("16 oz", title="Dip", pid_quantity=16, pid_unit="OUNCES")
    assert (small.exported, large.exported) == ("8 oz", "16 oz")


# -- the terms of an offer in the supporting files -----------------------------------------------------------


def _terms(text: str, **kw: Any) -> dict[str, Any]:
    c = classify(OfferObservation(OfferSource.JSON_PRODUCTS, text, **kw), "PICKUP")
    return offer_terms(c)


def test_the_terms_of_a_real_offer_keep_its_quantity_dates_and_fulfillment() -> None:
    """Live 2026-11-02, Vernon Hills Pickup: the product's own offer data."""
    t = _terms(
        "Save $2 each when you buy 3 or more",
        starts_at="2026-10-28T00:00:00.000Z",
        ends_at="2026-11-17T23:59:59.000Z",
        modalities=("PICKUP",),
        offer_code="3971f995-aff6-4021-bb0c-955ae9a00d08",
    )
    assert t["required_quantity"] == 3 and t["clipping_required"] is False
    assert (t["valid_from"], t["valid_to"]) == ("2026-10-28T00:00:00.000Z", "2026-11-17T23:59:59.000Z")
    assert t["fulfillment_restriction"] == ["PICKUP"] and t["explicit_price"] == ""


def test_the_terms_keep_every_condition_shown_and_invent_none() -> None:
    t = _terms("$2.00 off Mix & Match any 4 Yogurts with Card. Limit 2 per household.", clip_checkbox=True)
    assert t["mix_and_match"] is True and t["membership"] == "with Card"
    assert t["limit"] == "Limit 2 per household"
    plain = _terms("Buy 1 Save $1")
    assert plain["required_quantity"] == 1 and plain["limit"] == "" and plain["membership"] == ""
    assert plain["explicit_price"] == "" and plain["valid_to"] == ""


@pytest.mark.parametrize("text", ["Save $1.00 with Card", "$1 off for Boost members only"])
def test_membership_alone_is_not_a_digital_offer(text: str) -> None:
    c = classify(OfferObservation(OfferSource.ZONE, text), "PICKUP")
    assert c.kind is OfferKind.OTHER_PROMO and c.requires_clip is False


def test_an_in_store_only_offer_leaves_the_pickup_deal_fields_empty_with_its_reason(
    settings: Settings,
) -> None:
    obs = [OfferObservation(OfferSource.ZONE, "2 For $5.00", extra_tags=("In-Store Only",))]
    d = derive_deal_fields(obs, settings.records, "PICKUP")
    assert d.volume_deals_description == "" and d.volume_deals_price == ""
    assert restriction_reason(d.classified[0]) is not None


# -- why a field is empty ------------------------------------------------------------------------------------


def test_each_class_of_an_empty_field() -> None:
    kinds = missing_kinds(
        {
            "gupc": "always empty (client rule)",
            "weight": "unresolved size conflict: title 8 oz, card 2 tbsp",
            "ppm": "the card shows no price per measure (no product response was captured to compare)",
            "sale_price": "no sale price is displayed",
            "volume_deals_price": "several multi-unit offers state different prices",
        }
    )
    assert kinds == {
        "gupc": "client_rule",
        "weight": "unresolved_conflict",
        "ppm": "not_attempted",
        "sale_price": "not_displayed",
        "volume_deals_price": "unresolved_conflict",
    }
    assert missing_kinds({"weight": "size text unreadable"}, size_problem="size text unreadable") == {
        "weight": "parsing_failure"
    }


def test_a_retained_record_says_why_this_run_did_not_show_it() -> None:
    cov = {"03001": "DONE", "03002": "INCOMPLETE"}
    assert why_kind("03001", cov) == "not_displayed"
    assert why_kind("03002", cov) == "access_failure"
    assert why_kind("03003", cov) == "not_attempted"
