"""The approximate-weight rule of release 1.4.0 (client feedback of 2026-10-29, brief §5A), read since release
1.5.0 on every source of the product's weight (the displayed weight, the product data's size, and a weight
range in the name when no weight is displayed).

Only approximate-weight wording in the product's weight excludes it. A product sold by weight
("about $1.64 each", "$2.39/lb") is kept: its displayed price per unit is the PPM and its estimated item
price is never a fixed price. Marketing uses of "about", fixed multipacks and pack labels are not
approximate weights. The wording below is the kind observed on the site's cards (FIXTURE strings)."""

from __future__ import annotations

import pytest

from marianos_headless.assembly.exclusions import (
    approx_weight_wording,
    exclusion_reasons,
    is_approx_weight,
    weight_range_in,
)
from marianos_headless.core.findings import EXCLUSION_FLAGS, RecordFlag
from marianos_headless.core.settings import RecordSettings

S = RecordSettings()


def reasons(weight: str, flags: tuple[RecordFlag, ...] = ()) -> list[RecordFlag]:
    return exclusion_reasons(
        flags=flags,
        weight=weight,
        is_ship_only=False,
        location_attested=True,
        upc="0004119211060",
        settings=S,
    )


@pytest.mark.parametrize(
    "weight",
    [
        "about 2 lb",
        "approx. 1.5 lb",
        "Approximately 3 lbs",
        "avg. 0.75 lb",
        "~1 lb",
        "10-14 lb",
        "8 to 12 lb",
    ],
)
def test_approximate_weight_wording_excludes(weight: str) -> None:
    assert is_approx_weight(weight, S)
    assert reasons(weight) == [RecordFlag.APPROX_WEIGHT]


@pytest.mark.parametrize(
    "weight",
    ["16 oz", "3 lb", "Family Pack 3 lb", "2-pack", "12 ct", "6 pk / 12 fl oz", "1 Bunch", "5-7 Bananas", ""],
)
def test_fixed_weights_and_packs_are_not_approximate(weight: str) -> None:
    assert not is_approx_weight(weight, S)
    assert reasons(weight) == []


@pytest.mark.parametrize(
    "text", ["All about flavor", "About Time Protein Bar", "$2.39/lb", "about $1.64 each"]
)
def test_marketing_about_and_price_wording_are_not_a_weight(text: str) -> None:
    assert not is_approx_weight(text, S)


def test_selling_by_weight_is_not_an_exclusion() -> None:
    sold_by_weight = (RecordFlag.RELATIVE_PRICE, RecordFlag.SOLD_BY_WEIGHT, RecordFlag.ESTIMATED_PRICE_ONLY)
    assert reasons("", sold_by_weight) == []
    assert not (set(sold_by_weight) & EXCLUSION_FLAGS)


def wording(
    weight: str = "", data: str = "", title: str = "", by_weight: bool = True, settings: RecordSettings = S
) -> object:
    return approx_weight_wording(
        weight=weight, product_data_size=data, title=title, sold_by_weight=by_weight, settings=settings
    )


JENNIE_O = "Jennie-O Frozen Whole Turkey 10-14 lb"  # FIXTURE strings of the kind 1.4.0 retained flagged


def test_a_weight_range_in_the_product_data_or_the_title_is_an_approximate_weight() -> None:
    """Release 1.5.0: a whole turkey sold by weight shows "$0.98/lb" in its size slot (no weight displayed);
    its product data states "10-14 lb" and its name the same range. The range is its weight, approximate:
    excluded, with the wording and its source."""
    assert weight_range_in(JENNIE_O) == "10-14 lb"
    assert wording(data="10-14 lb", title=JENNIE_O) == ("product_data_size", "10-14 lb")
    assert wording(title=JENNIE_O) == ("title", "10-14 lb")
    assert wording(data="about 12 lb") == ("product_data_size", "about 12 lb")
    assert wording(weight="approx. 1.5 lb", data="1.5 lb") == ("weight", "approx. 1.5 lb")
    approx = wording(data="10-14 lb", title=JENNIE_O)
    assert isinstance(approx, tuple)
    assert exclusion_reasons(
        flags=(RecordFlag.WEIGHT_RANGE_IN_TITLE,),
        weight="",
        is_ship_only=False,
        location_attested=True,
        upc="0025006100000",
        settings=S,
        approx_weight=approx,
    ) == [RecordFlag.APPROX_WEIGHT]


@pytest.mark.parametrize("data", ["1 lb", "1 ct", "1 each", "3 lb", "12 oz", "1 Bunch", "Front", ""])
def test_a_pricing_unit_or_a_fixed_size_in_the_product_data_is_not_approximate(data: str) -> None:
    """Bananas sold by weight state "1 lb" (the pricing unit), a single item "1 ct": not approximate."""
    assert wording(data=data, title="Bananas") is None


def test_the_title_is_read_only_for_a_product_sold_by_weight_with_no_weight_displayed() -> None:
    """A displayed fixed weight is the product's weight; a range in the name does not override it. A diaper's
    name states the baby's weight (stored 1.3.5 observations, e.g. UPC 0003600056435 "Huggies Snug & Dry Size
    4 Baby Diapers (22-37 lbs)", displayed "92 count"): never a weight, displayed or not."""
    assert wording(weight="3 lb", title="Mini Potatoes 1-3 lb Size Mix") is None
    assert wording(title="Kroger 2% Milk 1 gal") is None
    diapers = "Huggies Snug & Dry Size 4 Baby Diapers (22-37 lbs)"
    assert wording(weight="92 count", data="92 count", title=diapers, by_weight=False) is None
    assert wording(title=diapers, by_weight=False) is None


def test_the_sources_are_configurable_and_weight_alone_is_the_rule_of_release_1_4_0() -> None:
    only_weight = RecordSettings(approx_weight_sources=("weight",))
    assert wording(data="10-14 lb", title=JENNIE_O, settings=only_weight) is None
    assert wording(weight="about 2 lb", settings=only_weight) == ("weight", "about 2 lb")
    assert RecordFlag.WEIGHT_RANGE_IN_TITLE not in EXCLUSION_FLAGS  # still a report flag, not a reason
    with pytest.raises(ValueError):
        RecordSettings(approx_weight_sources=("weight", "brand"))  # type: ignore[arg-type]
