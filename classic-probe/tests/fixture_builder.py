"""SYNTHETIC Classic responses for the offline tests.

The envelope follows the documented Realtime response (``results[]`` with ``content``, ``status_code``,
``type``, ``job_id``; the parsed ``content`` with ``location``, ``page_details``, ``results``,
``parse_status_code``). The Walmart pages inside are invented, shaped like walmart.com's server-rendered page
data (``__NEXT_DATA__``) as the Walmart collector reads it. Nothing here is a Classic response, a live page or
evidence of what Classic returns.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

STORE = "3891"
OTHER_STORE = "5260"


@dataclass(frozen=True)
class Item:
    item_id: str
    name: str
    price: str = "$3.12"
    seller: str = "Walmart.com"
    pickup: bool = True
    sponsored: bool = False
    upc: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def item_json(it: Item, store: str) -> dict[str, Any]:
    lines = (
        [{"fulfillment": "PICKUP", "storeId": store}]
        if it.pickup
        else [{"fulfillment": "SHIPPING", "storeId": ""}]
    )
    return {
        "__typename": "Product",
        "usItemId": it.item_id,
        "name": it.name,
        "canonicalUrl": f"/ip/{it.name.split(',')[0].replace(' ', '-')}/{it.item_id}",
        "imageInfo": {"thumbnailUrl": f"https://i5.walmartimages.com/seo/synthetic_{it.item_id}.jpeg"},
        "priceInfo": {"currentPrice": {"price": float(it.price.strip("$")), "priceString": it.price}},
        "sellerName": it.seller,
        "fulfillmentSummary": lines,
        "availabilityStatusV2": {"value": "IN_STOCK", "display": "In stock"},
        "isSponsoredFlag": it.sponsored,
        **({"upc": it.upc} if it.upc else {}),
        **it.extra,
    }


def _script(data: dict[str, Any]) -> str:
    return (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(data).replace("<", "\\u003c")
        + "</script>"
    )


def search_html(
    items: Sequence[Item], *, store: str = STORE, intent: str = "PICKUP", page: int = 1, max_page: int = 3
) -> str:
    data = {
        "props": {
            "pageProps": {
                "initialData": {
                    "pageMetadata": {"location": {"storeId": store, "postalCode": "60085", "intent": intent}},
                    "searchResult": {
                        "aggregatedCount": 120,
                        "itemStacks": [
                            {
                                "layoutEnum": "GRID",
                                "count": 120,
                                "items": [item_json(i, store) for i in items],
                            }
                        ],
                        "paginationV2": {"maxPage": max_page, "pageProperties": {"page": page}},
                    },
                }
            }
        },
        "query": {"page": str(page)},
    }
    return _document("SYNTHETIC search", data)


def product_html(
    item_id: str, *, store: str = STORE, upc: str = "012345678905", page_item: str | None = None
) -> str:
    product = {
        **item_json(Item(page_item or item_id, "Synthetic Milk, 128 fl oz", upc=upc), store),
        "location": {
            "storeIds": [store],
            "pickupLocation": {"storeId": store},
            "intent": "PICKUP",
            "postalCode": "60085",
        },
        "sellerType": "INTERNAL",
    }
    data = {"props": {"pageProps": {"initialData": {"data": {"product": product}}}}}
    return _document("SYNTHETIC product", data)


def _document(title: str, data: dict[str, Any]) -> str:
    return f"<!doctype html><html><head><title>{title}</title></head><body>{_script(data)}</body></html>"


CHALLENGE_HTML = (
    "<!doctype html><html><head><title>Robot or human?</title></head><body>"
    '<div id="px-captcha"></div><script src="https://captcha.px-cdn.net/x/captcha.js"></script></body></html>'
)


def envelope(
    raw_html: str | None, parsed: dict[str, Any] | None, *, status_code: int = 200, job: str = "1"
) -> bytes:
    results: list[dict[str, Any]] = []
    if raw_html is not None:
        results.append(
            {
                "content": raw_html,
                "status_code": status_code,
                "type": "raw",
                "job_id": f"job-{job}",
                "is_render_forced": False,
                "page": 1,
            }
        )
    if parsed is not None:
        results.append(
            {
                "content": parsed,
                "status_code": status_code,
                "type": "parsed",
                "job_id": f"job-{job}",
                "is_render_forced": False,
                "page": 1,
                "parser_type": "walmart_search_new",
            }
        )
    return json.dumps({"results": results}).encode("utf-8")


def parsed_search(
    items: Sequence[Item], *, store: str = STORE, page: int = 1, last: int = 3, code: int = 12000
) -> dict[str, Any]:
    return {
        "location": {"city": "Waukegan", "state": "IL", "store_id": store, "zipcode": "60085"},
        "page_details": {"last_visible_page": last, "page": page, "total_results": 120},
        "parse_status_code": code,
        "results": [
            {
                "general": {
                    "product_id": it.item_id,
                    "title": it.name,
                    "sponsored": it.sponsored,
                    "url": f"/ip/x/{it.item_id}",
                },
                "fulfillment": {
                    "pickup": it.pickup,
                    "delivery": False,
                    "shipping": not it.pickup,
                    "free_shipping": False,
                },
                "seller": {"name": it.seller},
                "price": {"currency": "USD", "price": float(it.price.strip("$"))},
            }
            for it in items
        ],
    }


def parsed_product(
    item_id: str, *, store: str = STORE, code: int = 12000, gtin: str = "012345678905"
) -> dict[str, Any]:
    return {
        "location": {"city": "Waukegan", "state": "IL", "store_id": store, "zip_code": "60085"},
        "parse_status_code": code,
        "general": {
            "title": "Synthetic Milk, 128 fl oz",
            "url": f"https://www.walmart.com/ip/x/{item_id}",
            "meta": {"gtin": gtin, "sku": item_id},
        },
        "seller": {"name": "Walmart.com", "official_name": "Walmart.com"},
        "fulfillment": {"pickup": True, "pickup_information": ", Pickup, Today"},
    }


PAGE1 = [
    Item("7101", "Synthetic Milk, 128 fl oz"),
    Item("7102", "Synthetic Cream, 16 fl oz", sponsored=True),
    Item("7103", "Synthetic Butter, 16 oz", seller="Other Seller LLC", pickup=False),
]
PAGE2 = [Item("7201", "Synthetic Yogurt, 32 oz"), Item("7202", "Synthetic Cheese, 8 oz")]


def complete() -> dict[str, list[tuple[int, bytes]]]:
    """Every step answered as a fully working Classic account would have to answer it (SYNTHETIC)."""
    return {
        "walmart-search-p1": [(200, envelope(search_html(PAGE1), parsed_search(PAGE1)))],
        "walmart-search-p2": [(200, envelope(search_html(PAGE2, page=2), parsed_search(PAGE2, page=2)))],
        "walmart-product": [(200, envelope(product_html("7101"), parsed_product("7101")))],
        "walmart-category-url": [(200, envelope(search_html(PAGE1), None))],
    }
