"""The canonical 22-field output record (brief §6.1, docx §4).

Every exported item has exactly these keys, in this order, and every value is a ``str``. Missing
values are ``""``; ``gupc`` and ``unit_price`` are always ``""`` at the scraper stage.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

OUTPUT_FIELDS: Final[tuple[str, ...]] = (
    "zipcode",
    "store_name",
    "store_location",
    "store_logo",
    "store_brand",
    "category",
    "sub_category",
    "product_title",
    "weight",
    "regular_price",
    "sale_price",
    "volume_deals_description",
    "volume_deals_price",
    "digital_deals_description",
    "digital_deals_price",
    "image_url",
    "url",
    "upc",
    "gupc",
    "ppm",
    "unit_price",
    "crawl_date",
)

ALWAYS_EMPTY: Final[frozenset[str]] = frozenset({"gupc", "unit_price"})
PRICE_FIELDS: Final[tuple[str, ...]] = (
    "regular_price",
    "sale_price",
    "volume_deals_price",
    "digital_deals_price",
)
FORBIDDEN_KEYS: Final[frozenset[str]] = frozenset({"remarks", "gupc14"})

# G6 formats. PPM and UPC patterns are provisional until Phase 0 records the live displays.
PRICE_RE: Final = re.compile(r"^\d+\.\d{2}$")
# A price per measure as retailers display it: "$0.29/fl oz" (Mariano's), "2.4 ¢/fl oz", "$1.23/lb",
# "$0.12/100 ct" (Walmart).
PPM_RE: Final = re.compile(
    r"^(\$\d+(\.\d{1,3})?|\d+(\.\d{1,3})? ?¢) ?/ ?(\d+(\.\d+)? ?)?[A-Za-z][A-Za-z .]*$"
)
# UPCs are kept exactly as the retailer shows them, in a GTIN length: Mariano's 13 digits, Walmart's UPC-A
# 12 digits, UPC-E/EAN-8 8 digits, GTIN-14.
UPC_RE: Final = re.compile(r"^(?:\d{8}|\d{12,14})$")
CRAWL_DATE_RE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RecordShapeError(ValueError):
    """A record cannot be built without violating the output contract."""


def build_record(values: Mapping[str, str]) -> dict[str, str]:
    """Return a new record in canonical key order.

    Unknown keys are rejected rather than dropped, so a mapping bug cannot silently lose data.
    ``gupc`` and ``unit_price`` must be absent or ``""``.
    """
    unknown = set(values) - set(OUTPUT_FIELDS)
    if unknown:
        raise RecordShapeError(f"unknown output keys: {sorted(unknown)}")
    for key in ALWAYS_EMPTY:
        if values.get(key, ""):
            raise RecordShapeError(f"{key} must be empty at the scraper stage")
    record: dict[str, str] = {}
    for key in OUTPUT_FIELDS:
        value = values.get(key, "")
        if not isinstance(value, str):
            raise RecordShapeError(f"{key} must be a str, got {type(value).__name__}")
        record[key] = value
    return record


def ordered_record(stored: Mapping[str, str]) -> dict[str, str]:
    """Restore canonical key order for a record read back from storage.

    PostgreSQL ``JSONB`` does not keep key order, so every record loaded from the database must pass
    through here before hashing, validation or export. Unknown keys are an error, never dropped.
    """
    unknown = set(stored) - set(OUTPUT_FIELDS)
    if unknown:
        raise RecordShapeError(f"unknown output keys: {sorted(unknown)}")
    return {key: stored.get(key, "") for key in OUTPUT_FIELDS}


def shape_violations(item: Mapping[str, object]) -> list[str]:
    """G5: key order, string types, forbidden keys and always-empty fields."""
    problems: list[str] = []
    keys = list(item.keys())
    if keys != list(OUTPUT_FIELDS):
        problems.append("keys are not exactly OUTPUT_FIELDS in order")
    for key in FORBIDDEN_KEYS & set(keys):
        problems.append(f"forbidden key {key!r}")
    for key, value in item.items():
        if not isinstance(value, str):
            problems.append(f"{key} is {type(value).__name__}, not str")
    for key in ALWAYS_EMPTY:
        if item.get(key, "") != "":
            problems.append(f"{key} must be empty")
    return problems


def format_violations(item: Mapping[str, str]) -> list[str]:
    """G6: field formats after normalisation."""
    problems: list[str] = []
    for key in PRICE_FIELDS:
        value = item.get(key, "")
        if value and not PRICE_RE.match(value):
            problems.append(f"{key}={value!r} is not a two-decimal price")
    ppm = item.get("ppm", "")
    if ppm and not PPM_RE.match(ppm):
        problems.append(f"ppm={ppm!r} does not match the PPM display pattern")
    upc = item.get("upc", "")
    if upc and not UPC_RE.match(upc):
        problems.append(f"upc={upc!r} is not a UPC/GTIN of 8, 12, 13 or 14 digits")
    crawl_date = item.get("crawl_date", "")
    if crawl_date and not CRAWL_DATE_RE.match(crawl_date):
        problems.append(f"crawl_date={crawl_date!r} is not YYYY-MM-DD")
    return problems
