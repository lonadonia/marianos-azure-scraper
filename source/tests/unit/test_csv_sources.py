from __future__ import annotations

import pytest

from marianos_headless.sites.marianos.csv_sources import (
    CategoryCsvError,
    SourceKind,
    load_category_csv,
    parse_category_csv,
)
from tests.conftest import CONFIG


def test_csv_has_28_rows_in_expected_shape() -> None:
    rows, sha = load_category_csv(CONFIG / "Marianos_Category_URLs.csv")
    assert len(rows) == 28
    assert sha == "606133cb12548d3f7f437ea9e0a056d88d0dd7f621ec0e1c210bb2fc20044da4"
    kinds = [r.kind for r in rows]
    assert kinds.count(SourceKind.DEPARTMENT_LANDING) == 22
    assert kinds.count(SourceKind.TAXONOMY_LISTING) == 5
    assert kinds.count(SourceKind.COUPON_CATALOGUE) == 1
    assert rows[0].category_name == "Coupons" and rows[0].is_coupons
    assert all(r.scope == "Category + ALL subcategories" for r in rows)
    assert [r.row_index for r in rows] == list(range(28))
    by_name = {r.category_name: r for r in rows}
    assert by_name["Produce"].landing_slug == "produce"
    assert by_name["Light Bulbs"].taxonomy_id == "26002"
    assert by_name["School Office"].taxonomy_id == "35"


def test_csv_rejects_wrong_columns_and_hosts() -> None:
    with pytest.raises(CategoryCsvError):
        parse_category_csv(b"A,B\n1,2\n")
    bad = (
        b"Retailer,Category (Auto),URL,Scope,Notes\n"
        b"Mariano's,X,https://example.com/d/x,Category + ALL subcategories,\n"
    )
    with pytest.raises(CategoryCsvError):
        parse_category_csv(bad)
