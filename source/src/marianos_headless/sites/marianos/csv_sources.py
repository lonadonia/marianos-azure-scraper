"""Load ``Marianos_Category_URLs.csv`` (the category scope; brief §2)."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from marianos_headless.sites.marianos.taxonomy import taxonomy_id_from_url

EXPECTED_COLUMNS = ("Retailer", "Category (Auto)", "URL", "Scope", "Notes")
EXPECTED_SCOPE = "Category + ALL subcategories"
SITE_HOST = "www.marianos.com"


class SourceKind(StrEnum):
    DEPARTMENT_LANDING = "department_landing"  # /d/<slug>
    TAXONOMY_LISTING = "taxonomy_listing"  # /pl/<slug>/<taxonomyId>
    COUPON_CATALOGUE = "coupon_catalogue"  # /savings/cl/coupons/


@dataclass(frozen=True)
class CategorySource:
    row_index: int  # 0-based position in the CSV; defines CSV order for the primary-category policy
    retailer: str
    category_name: str
    url: str
    scope: str
    notes: str
    kind: SourceKind
    landing_slug: str | None  # for /d/ rows, the path after /d/
    taxonomy_id: str | None  # for /pl/ rows

    @property
    def is_coupons(self) -> bool:
        return self.kind is SourceKind.COUPON_CATALOGUE


class CategoryCsvError(ValueError):
    pass


def _classify(url: str) -> tuple[SourceKind, str | None, str | None]:
    parts = urlsplit(url)
    if parts.netloc != SITE_HOST:
        raise CategoryCsvError(f"unexpected host in {url!r}")
    path = parts.path
    if path.startswith("/savings/cl/coupons"):
        return SourceKind.COUPON_CATALOGUE, None, None
    if path.startswith("/d/"):
        return SourceKind.DEPARTMENT_LANDING, path[len("/d/") :].strip("/"), None
    if path.startswith("/pl/"):
        tid = taxonomy_id_from_url(url)
        if tid is None:
            raise CategoryCsvError(f"no taxonomy id in {url!r}")
        return SourceKind.TAXONOMY_LISTING, None, tid.taxonomy_id
    raise CategoryCsvError(f"unsupported category URL {url!r}")


def parse_category_csv(data: bytes) -> tuple[list[CategorySource], str]:
    """Return the rows in file order and the sha256 of the file bytes."""
    sha = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
        raise CategoryCsvError(f"unexpected columns {reader.fieldnames}; expected {EXPECTED_COLUMNS}")
    rows: list[CategorySource] = []
    seen_names: set[str] = set()
    for i, raw in enumerate(reader):
        name = (raw["Category (Auto)"] or "").strip()
        url = (raw["URL"] or "").strip()
        if not name or not url:
            raise CategoryCsvError(f"row {i}: category and URL are required")
        if name in seen_names:
            raise CategoryCsvError(f"row {i}: duplicate category {name!r}")
        seen_names.add(name)
        kind, slug, tid = _classify(url)
        rows.append(
            CategorySource(
                row_index=i,
                retailer=(raw["Retailer"] or "").strip(),
                category_name=name,
                url=url,
                scope=(raw["Scope"] or "").strip(),
                notes=(raw["Notes"] or "").strip(),
                kind=kind,
                landing_slug=slug,
                taxonomy_id=tid,
            )
        )
    return rows, sha


def load_category_csv(path: Path) -> tuple[list[CategorySource], str]:
    return parse_category_csv(path.read_bytes())
