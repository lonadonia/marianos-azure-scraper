"""The site's result window (live 2026-10-23: every products-search response stated ``availableCount`` 250;
Cereal & Granola reported 328 results and its Load More ended after the page at offset 240)."""

from __future__ import annotations

import gzip
import json

from marianos_headless.acquisition.capture import CapturedResponse
from marianos_headless.collection.live import (
    ListingView,
    click_problem,
    facet_children,
    search_requests,
    window_reason,
)

URL = (
    "https://www.marianos.com/atlas/v1/search/v1/products-search?filter.locationId=53100503"
    "&filter.taxonomies=03001&page.offset=240&page.size=24"
)


def _search(total: int, available: int | None) -> tuple[CapturedResponse, dict[str, bytes]]:
    meta: dict[str, object] = {"totalCount": total, "page": {"offset": 240, "size": 24}}
    if available is not None:
        meta["availableCount"] = available
    body = gzip.compress(
        json.dumps({"data": {"productsSearch": []}, "meta": {"productsSearch": meta}}).encode()
    )
    c = CapturedResponse(
        seq=1,
        fetch_id="f",
        kind="products_search",
        url=URL,
        method="GET",
        status=200,
        request_location_id="53100503",
        request_taxonomies=["03001"],
        request_headers={},
        response_headers={},
        body_sha256="0" * 64,
        body_bytes=len(body),
        artifact_key="raw/x.products_search.json.gz",
        observed_at="2026-10-23T21:56:00Z",
    )
    return c, {"raw/x.products_search.json.gz": body}


def test_the_available_count_is_read_from_the_products_search_response() -> None:
    c, store = _search(328, 250)
    [s] = search_requests([c], store.__getitem__)
    assert (s["offset"], s["total"], s["available"], s["location_id"]) == (240, 328, 250, "53100503")
    view = ListingView(True, [], set(), 328, [s])
    assert view.total == 328 and view.available == 250


def test_a_listing_cut_by_the_window_is_not_complete() -> None:
    reason = window_reason(328, 250, 229)
    assert reason is not None and "250 of the 328" in reason and "229 products were read" in reason
    assert window_reason(254, 250, 244) is not None  # Crackers: 4 or more results beyond the window
    assert window_reason(208, 250, 197) is None  # the whole listing fits: its last page is its end
    assert window_reason(328, None, 229) is None  # no window stated: nothing claimed
    assert window_reason(None, 250, 10) is None


def test_a_click_error_is_summarized_with_what_blocked_it() -> None:
    err = RuntimeError(
        "Locator.click: Timeout 10000ms exceeded.\nCall log:\n  - attempting click action\n"
        '    - <div id="survey"> intercepts pointer events\n'
    )
    text = click_problem(err)
    assert text.startswith("Locator.click: Timeout 10000ms exceeded.") and "intercepts pointer events" in text


# The category facet of the Cereal & Granola search, as the site returned it on 2026-10-23 (shortened).
CEREAL_FACET = [
    {
        "id": "03",
        "name": "Breakfast",
        "count": 328,
        "slug": "breakfast",
        "children": [
            {
                "id": "03001",
                "name": "Cereal & Granola",
                "count": 328,
                "slug": "cereal-granola",
                "children": [
                    {"id": "0300100001", "name": "Cold Cereal", "count": 240, "slug": "cold-cereal"},
                    {"id": "0300100003", "name": "Granola", "count": 71, "slug": "granola"},
                    {"id": "0300100006", "name": "Bag Cereal", "count": 24, "slug": "bag-cereal"},
                    {"id": "0300100007", "name": "On the Go Cereal", "count": 14, "slug": "on-the-go-cereal"},
                ],
            },
            {"id": "03002", "name": "Bars & Toaster Pastries", "count": 1, "slug": "bars-toaster-pastries"},
        ],
    }
]


def test_the_child_listings_come_from_the_sites_category_facet() -> None:
    kids = facet_children(CEREAL_FACET, "03001")
    assert [k["id"] for k in kids] == ["0300100001", "0300100003", "0300100006", "0300100007"]
    assert kids[0] == {"id": "0300100001", "name": "Cold Cereal", "slug": "cold-cereal", "count": 240}
    # The children overlap (240 + 71 + 24 + 14 = 349 > 328): their counts are never added up for coverage.
    assert sum(k["count"] for k in kids) == 349
    assert facet_children(CEREAL_FACET, "03002") == []  # no children named
    assert facet_children(CEREAL_FACET, "99999") == []  # not in the tree
    assert facet_children(None, "03001") == []
    bad = [{"id": "03001", "children": [{"id": "04001", "name": "Elsewhere", "count": 3, "slug": "x"}]}]
    assert facet_children(bad, "03001") == []  # not a descendant of the listing: ignored
