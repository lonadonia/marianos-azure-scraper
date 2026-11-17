"""OR-20 (release 1.10.0rc6): the source check's index of a run's stored sources is built one source at a time
and keeps each distinct price statement once, so its size follows a run's distinct prices, not its pages.

SYNTHETIC pages (the embedded-data shape of ``test_source_check_embedded.py``). Expected to FAIL on 1.10.0rc5,
which has no ``SourceIndex`` (it held every page's text and every product object at once)."""

from __future__ import annotations

from marianos_headless.checks import source_check
from tests.unit.test_source_check_embedded import RECORD, UPC, _page, _product


def test_or20_a_price_stated_on_many_pages_is_kept_once_and_still_decides_the_record() -> None:
    index = source_check.SourceIndex()
    for n in range(500):
        index.add_page(_page([_product("4.79")]), f"page-{n}")
    assert index.statements == 500
    assert len(index) == 1 and len(index.products[UPC]) == 1
    assert index.products[UPC][0]["_source"] == "page-0"
    out = source_check.check_records([RECORD], index.products, "53100503")
    assert (
        out["summary"]["verified"] == 1 and out["results"][0]["evidence"] == source_check.EMBEDDED_PAGE_DATA
    )


def test_or20_distinct_statements_are_all_kept_and_the_best_one_decides() -> None:
    index = source_check.SourceIndex()
    index.add_page(_page([_product("5.29", location="53100511")]), "other-store")
    index.add_page(_page([_product("4.79")]), "this-store")
    index.add_page(_page([_product("4.79")]), "this-store-again")
    assert len(index.products[UPC]) == 2
    out = source_check.check_records([RECORD], index.products, "53100503")
    assert out["summary"]["verified"] == 1
    other = dict(RECORD, regular_price="9.99")
    out = source_check.check_records([other], index.products, "53100503")
    [m] = out["results"]
    assert m["result"] == "mismatch" and m["source"] == "this-store"
    assert m["source_values"] == {"store": "53100503", "regular": "4.79", "promo": None}
