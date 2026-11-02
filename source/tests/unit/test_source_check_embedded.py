"""The source check's second evidence class: product data embedded in a stored page copy (release 1.2.1).

SYNTHETIC page: a listing page embeds its first page's product data in ``window.__INITIAL_STATE__``
(``calypso.useCases.getProducts.<name>.response.data.products``), the same objects as the product responses
(live shape, 2026-10-23: the Yogurt page whose product responses were not captured).
"""

from __future__ import annotations

import json
from typing import Any

from marianos_headless.checks import source_check

UPC = "0001111010760"


def _product(regular: str, promo: str | None = None, location: str = "53100503") -> dict[str, Any]:
    prices: dict[str, Any] = {"sourceLocationId": location, "regular": {"price": f"USD {regular}"}}
    if promo is not None:
        prices["promo"] = {"price": f"USD {promo}"}
    return {"item": {"upc": UPC}, "price": {"storePrices": prices}}


def _page(products: list[dict[str, Any]]) -> str:
    state = {
        "calypso": {
            "useCases": {"getProducts": {"search-grid": {"response": {"data": {"products": products}}}}}
        }
    }
    literal = json.dumps(state).replace("\\", "\\\\").replace("'", "\\'")
    return f"<html><body><script>window.__INITIAL_STATE__ = JSON.parse('{literal}');</script></body></html>"


RECORD = {"upc": UPC, "regular_price": "4.79", "sale_price": ""}


def test_embedded_page_data_verifies_a_record_and_says_so() -> None:
    page = _page([_product("4.79")])
    assert [p["item"]["upc"] for p in source_check.embedded_products(page)] == [UPC]
    out = source_check.check_records([RECORD], source_check.index([], [page]), "53100503")
    assert out["summary"]["verified"] == 1
    assert out["results"][0]["evidence"] == source_check.EMBEDDED_PAGE_DATA
    assert out["by_evidence"] == {"verified:embedded_page_data": 1}


def test_a_product_response_is_preferred_and_a_price_difference_stays_a_conflict() -> None:
    body = json.dumps({"data": {"products": [_product("4.79")]}}).encode()
    page = _page([_product("4.79")])
    both = source_check.check_records([RECORD], source_check.index([body], [page]), "53100503")
    assert both["results"][0]["evidence"] == source_check.PRODUCT_RESPONSE
    wrong = source_check.check_records(
        [RECORD], source_check.index([], [_page([_product("4.99")])]), "53100503"
    )
    assert wrong["summary"]["mismatch"] == 1 and wrong["results"][0]["mismatched_fields"] == ["regular_price"]
    other_store = source_check.check_records(
        [RECORD], source_check.index([], [_page([_product("4.79", location="53100511")])]), "53100503"
    )
    assert other_store["results"][0]["mismatched_fields"] == ["store"]


def test_a_page_without_embedded_products_adds_nothing() -> None:
    assert source_check.embedded_products("<html><body>no state</body></html>") == []
    out = source_check.check_records([RECORD], source_check.index([], ["<html></html>"]), "53100503")
    assert out["summary"]["unverified"] == 1
