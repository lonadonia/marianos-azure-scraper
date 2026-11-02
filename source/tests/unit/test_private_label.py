from __future__ import annotations

import pytest

from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import PrivateLabelConfig


@pytest.fixture
def detector(private_label: PrivateLabelConfig) -> PrivateLabelDetector:
    return PrivateLabelDetector(private_label)


@pytest.mark.parametrize(
    ("title", "upc", "expected"),
    [
        ("Roundy's® Organics Basil", "0001115099400", "yes"),
        ("Private Selection® Petite Gold Gourmet Potatoes", "0001111079542", "yes"),
        ("Kroger® Grade A Large White Eggs", "0001111060933", "yes"),
        ("Simple Truth™ Natural Cage Free Grade A Large Brown Eggs", "0001111079770", "yes"),
        ("Roundy’s® Select Vitamin D Whole Milk", "0001115015953", "yes"),  # curly apostrophe
        ("Kroger® Fresh Natural Pork Tenderloin", "0020335800000", "yes"),  # title only (variable weight)
        ("Diet Coke® Soda Mini Cans", "0004900006722", "no"),
        ("Fresh Bunch of Bananas – 5-7 Bananas", "0000000004011", "no"),
        ("Krogerville Snacks", "0009999999999", "no"),  # prefix must end on a word boundary
    ],
)
def test_title_and_upc_signals(detector: PrivateLabelDetector, title: str, upc: str, expected: str) -> None:
    assert detector.detect(title=title, upc=upc).value == expected


def test_brand_signal_is_primary(detector: PrivateLabelDetector) -> None:
    assert detector.detect(title="Grade A Eggs", upc="0009999999999", brand="Heritage Farm").value == "yes"


def test_conflict_is_no_with_flag(detector: PrivateLabelDetector) -> None:
    r = detector.detect(title="Some Product", upc="0001111000000", brand="Coca-Cola")
    assert r.value == "no"
    assert RecordFlag.PRIVATE_LABEL_SIGNAL_CONFLICT in r.flags


def test_longest_brand_wins(detector: PrivateLabelDetector) -> None:
    assert detector.title_brand("Kroger Mercado® Salsa Verde") == "kroger mercado"
