"""Display-text normalisation allowed by brief §6.1.

Only whitespace collapsing, entity decoding (done by the HTML parser) and price formatting are
allowed. Capitalisation, ®/™ and punctuation are kept exactly as shown.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_WS = re.compile(r"[\s\u00a0\u2007\u202f\u200b]+")
_PRICE_TOKEN = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?")


def collapse_ws(text: str | None) -> str:
    """Collapse runs of whitespace (incl. NBSP and zero-width space) to one space and strip."""
    if not text:
        return ""
    return _WS.sub(" ", text).strip()


def format_amount(amount: Decimal) -> str:
    """``Decimal('5') -> '5.00'``; never rounds a value with more than two decimals silently."""
    quantized = amount.quantize(Decimal("0.01"))
    if quantized != amount:
        raise ValueError(f"amount {amount} has more than two decimals")
    return f"{quantized:.2f}"


def price_tokens(text: str) -> list[str]:
    """All ``$`` amounts in displayed text, normalised to two decimals, in display order."""
    out: list[str] = []
    for whole, cents in _PRICE_TOKEN.findall(text or ""):
        raw = whole.replace(",", "") + ("." + cents.ljust(2, "0") if cents else "")
        try:
            out.append(format_amount(Decimal(raw)))
        except (InvalidOperation, ValueError):
            continue
    return out


def normalize_single_price(text: str | None) -> str:
    """Normalise a displayed price that must contain exactly one amount (``"$34.99" -> "34.99"``).

    Returns ``""`` when the text has no amount. Raises when it has several, because picking one
    would be a guess.
    """
    tokens = price_tokens(text or "")
    if not tokens:
        return ""
    if len(tokens) > 1:
        raise ValueError(f"ambiguous price text {text!r}: {tokens}")
    return tokens[0]


def normalize_amount_str(raw: str) -> str:
    """Normalise a bare amount captured by a regex group (``"5" -> "5.00"``, ``"8.99" -> "8.99"``)."""
    return format_amount(Decimal(raw.replace(",", "")))
