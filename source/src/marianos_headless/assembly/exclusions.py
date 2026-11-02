"""Record exclusions (brief §6.3). An excluded record is not exported but is counted per reason."""

from __future__ import annotations

import re
from collections.abc import Iterable

from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import RecordSettings

_PLU = re.compile(r"^0{7,8}\d{4,5}$")  # 13-digit form of a 4/5-digit PLU, e.g. 0000000004011
_PER_UNIT_SIZE = re.compile(r"^\$\d+(?:\.\d{1,2})?\s*/\s*[a-z ]+$", re.I)


def is_plu_code(upc: str | None) -> bool:
    return bool(upc and _PLU.match(upc))


_WEIGHT_RANGE = re.compile(
    r"(?i)\b\d+(\.\d+)?\s*(-|to)\s*\d+(\.\d+)?\s*(lb|lbs|pound|pounds|oz|ounce|ounces|kg|g)\b"
)


def size_slot_is_unit_price(size_text: str) -> bool:
    """For relative-price items the size slot shows "$0.69/lb" instead of a size."""
    return bool(_PER_UNIT_SIZE.match(size_text.strip()))


def is_approx_weight(weight: str, settings: RecordSettings) -> bool:
    """The client's approximate-weight rule, read on the weight (the displayed size) only."""
    return bool(weight and re.search(settings.approx_weight_pattern, weight))


def weight_range_in(text: str) -> str:
    """A weight range a text states ("10-14 Lb"), or ""."""
    m = _WEIGHT_RANGE.search(text or "")
    return m.group(0) if m else ""


def approx_weight_wording(
    *, weight: str, product_data_size: str, title: str, sold_by_weight: bool, settings: RecordSettings
) -> tuple[str, str] | None:
    """Where the product's weight is stated as approximate, and the wording: ("weight", "about 2 lb"),
    ("product_data_size", "10-14 lb") or ("title", "10-14 Lb"); ``None`` when no source the settings name
    states it (release 1.5.0). A whole turkey sold by weight shows "$0.98/lb" in its size slot; its own
    product data and its name give its weight as a range, an approximate weight like "about 12 lb". The name
    counts only for a weight range, only when no weight is displayed and only for a product sold by weight:
    "Baby Diapers Size 4 (22-37 lbs)" states the baby's weight, not the product's."""
    sources = settings.approx_weight_sources
    if "weight" in sources and is_approx_weight(weight, settings):
        return "weight", weight
    if "product_data_size" in sources and is_approx_weight(product_data_size, settings):
        return "product_data_size", product_data_size
    if "title" in sources and not weight and sold_by_weight:
        found = weight_range_in(title)
        if found:
            return "title", found
    return None


def exclusion_reasons(
    *,
    flags: Iterable[RecordFlag],
    weight: str,
    is_ship_only: bool,
    location_attested: bool,
    upc: str | None,
    settings: RecordSettings,
    is_marketplace: bool = False,
    approx_weight: tuple[str, str] | None = None,
) -> list[RecordFlag]:
    """All exclusion reasons that apply, in a stable order. Empty means the record is exported.
    ``upc`` is the product's identity: its UPC, or for a retailer that often shows none its source key.

    Selling by weight is not a reason (release 1.4.0; 1.3.5 and earlier excluded every "about $X each"
    product, setting ``exclude_relative_price_items``): only approximate-weight wording is, in the displayed
    weight or, since release 1.5.0, in another source of the product's weight (``approx_weight``, from
    :func:`approx_weight_wording`)."""
    present = set(flags)
    reasons: list[RecordFlag] = []
    if not upc:
        reasons.append(RecordFlag.NO_UPC)
    if not location_attested:
        reasons.append(RecordFlag.LOCATION_UNATTESTED)
    if is_marketplace:
        reasons.append(RecordFlag.MARKETPLACE_OFFER)
    if is_approx_weight(weight, settings) or approx_weight is not None:
        reasons.append(RecordFlag.APPROX_WEIGHT)
    if is_ship_only and settings.exclude_ship_only:
        reasons.append(RecordFlag.SHIP_ONLY)
    if RecordFlag.SCHEMA_INVALID in present:
        reasons.append(RecordFlag.SCHEMA_INVALID)
    return reasons
