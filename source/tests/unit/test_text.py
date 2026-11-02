from __future__ import annotations

import pytest

from marianos_headless.core.text import (
    collapse_ws,
    normalize_amount_str,
    normalize_single_price,
    price_tokens,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$34.99", "34.99"),
        ("$5", "5.00"),
        ("$5.5", "5.50"),
        ("$1,234.50", "1234.50"),
        ("about $1.45 each", "1.45"),
        ("", ""),
        ("Prices May Vary", ""),
    ],
)
def test_normalize_single_price(text: str, expected: str) -> None:
    assert normalize_single_price(text) == expected


def test_normalize_single_price_refuses_to_guess() -> None:
    with pytest.raises(ValueError):
        normalize_single_price("Sale: $34.99 discounted from $39.99")


def test_price_tokens_in_display_order() -> None:
    assert price_tokens("Save $30.00 When You Spend $75.00") == ["30.00", "75.00"]
    assert price_tokens("4/$10 when you buy 4 or more") == ["10.00"]


def test_normalize_amount_str() -> None:
    assert normalize_amount_str("5") == "5.00"
    assert normalize_amount_str("8.99") == "8.99"


def test_collapse_ws_keeps_marks_and_case() -> None:
    assert collapse_ws("  Diet Coke®  Soda\n Mini  Cans ") == "Diet Coke® Soda Mini Cans"
    assert collapse_ws(None) == ""
