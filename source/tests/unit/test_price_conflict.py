"""A displayed price that differs from the same product's own data on the same page (release 1.3.0).

FIXTURE (tests/fixtures/live_2026-10-23_honey_smacks): Honey Smacks on 2026-10-23, the card "discounted from
$8.78", the page's own product response regular USD 8.79. Release 1.2.x exported 8.78 and counted the record
as verified; both observations are now kept and the record is not verified while they differ."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import (
    CategoryAssignment,
    RecordStatus,
    StoreFields,
    truncation_explains,
)
from marianos_headless.collection.live import build_card, grid_cards
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig
from marianos_headless.sites.marianos.source_json import PRODUCTS, ResponseRef, SourceIndex

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "live_2026-10-23_honey_smacks"
UPC = "0004119211060"
STORE = StoreFields("60601", "Marianos Lakeshore East", "333 E Benton Pl, CHICAGO, IL 60601", "")


def _build(settings: Settings, store: StoreConfig, private_label: PrivateLabelConfig, body: str) -> object:
    _, cards, _, _ = grid_cards((FIX / "grid_card.html").read_text("utf-8"))
    (card,) = cards
    idx = SourceIndex()
    idx.add(
        PRODUCTS,
        body,
        ResponseRef(PRODUCTS, "01M5NC5JY5YSX2A07DEW223TYJ", "2c6b4943", "2026-10-23T21:55:20Z"),
    )
    return build_card(
        card,
        fetch_id="01M5NC5JY5YSX2A07DEW223TYJ",
        observed_at="2026-10-23T21:55:13+00:00",
        store=store,
        store_values=STORE,
        store_provenance={},
        category=CategoryAssignment("Breakfast", "Cereal & Granola"),
        crawl_date="2026-10-23",
        settings=settings,
        detector=PrivateLabelDetector(private_label, settings.records.store_brand_positive_value),
        sources=idx,
    ).built  # type: ignore[attr-defined]


def test_the_honey_smacks_conflict_keeps_both_prices_and_is_not_verified(
    settings: Settings, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> None:
    built = _build(settings, dev_store, private_label, (FIX / "products_v2.json").read_text("utf-8"))
    assert built.upc == UPC  # type: ignore[attr-defined]
    rec = built.record  # type: ignore[attr-defined]
    # Exactly as displayed: never the data's number, never an average.
    assert (rec["regular_price"], rec["sale_price"], rec["ppm"]) == ("8.78", "5.49", "$0.36/oz")
    assert RecordFlag.PRICE_DOM_JSON_MISMATCH in built.flags  # type: ignore[attr-defined]
    # Release 1.4.0: its own status, exported in the retained dataset, never in the clean fresh one.
    assert built.status is RecordStatus.PRICE_CONFLICT  # type: ignore[attr-defined]
    assert built.exported  # type: ignore[attr-defined]
    obs = built.provenance["_price_observations"]  # type: ignore[attr-defined]
    assert obs["conflict"] == {"regular_price": {"displayed": "8.78", "product_data": "8.79"}}
    assert (
        obs["product_data"]["promo_price"] == "5.49" and obs["product_data"]["price_location"] == "53100503"
    )
    assert obs["product_data"]["response"]["fetch_id"] == "01M5NC5JY5YSX2A07DEW223TYJ"
    # Release 1.7.0: the card's "discounted from" value is the data's 8.79 truncated to cents in binary
    # floating point (8.79 * 100 = 878.9999999999999 -> 878). The cause is recorded; export and status stay.
    assert obs["cause"] == {"regular_price": "ONE_CENT_TRUNCATION_PATTERN"}
    assert rec["regular_price"] == "8.78" and built.status is RecordStatus.PRICE_CONFLICT  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("displayed", "stated", "explained"),
    [
        ("8.78", "8.79", True),  # Honey Smacks, 2026-10-23
        ("18.98", "18.99", True),  # MARTINI & ROSSI Rosso Vermouth, 2026-10-29 (1.3.5)
        ("4.38", "4.39", True),  # Private Selection butter chicken sauce, 2026-10-29 (1.4.0 Q3)
        ("4.98", "4.99", False),  # 4.99 * 100 = 499.0: truncation leaves it unchanged
        ("8.77", "8.79", False),  # two cents: not this rule
        ("8.79", "8.79", False),  # no conflict
    ],
)
def test_truncation_explains_only_the_one_cent_floor_of_the_stated_price(
    displayed: str, stated: str, explained: bool
) -> None:
    assert truncation_explains(displayed, stated) is explained


def test_a_conflict_the_rule_does_not_explain_is_recorded_as_unexplained(
    settings: Settings, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> None:
    doc = json.loads((FIX / "products_v2.json").read_text("utf-8"))
    doc["data"]["products"][0]["price"]["storePrices"]["regular"]["price"] = "USD 8.99"
    built = _build(settings, dev_store, private_label, json.dumps(doc))
    assert built.status is RecordStatus.PRICE_CONFLICT  # type: ignore[attr-defined]
    assert built.provenance["_price_observations"]["cause"] == {"regular_price": "UNEXPLAINED"}  # type: ignore[attr-defined]


def test_equal_prices_stay_verified(
    settings: Settings, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> None:
    doc = json.loads((FIX / "products_v2.json").read_text("utf-8"))
    doc["data"]["products"][0]["price"]["storePrices"]["regular"]["price"] = "USD 8.78"
    built = _build(settings, dev_store, private_label, json.dumps(doc))
    assert built.status is RecordStatus.VALID  # type: ignore[attr-defined]
    assert RecordFlag.PRICE_DOM_JSON_MISMATCH not in built.flags  # type: ignore[attr-defined]
    assert "_price_observations" not in built.provenance  # type: ignore[attr-defined]


def test_a_price_for_another_store_is_a_location_failure_not_a_conflict(
    settings: Settings, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> None:
    doc = json.loads((FIX / "products_v2.json").read_text("utf-8"))
    doc["data"]["products"][0]["price"]["storePrices"]["sourceLocationId"] = "53100511"
    built = _build(settings, dev_store, private_label, json.dumps(doc))
    assert built.status is not RecordStatus.VALID  # type: ignore[attr-defined]
    assert "_price_observations" not in built.provenance  # type: ignore[attr-defined]
