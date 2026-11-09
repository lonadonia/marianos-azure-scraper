"""The Classic request contract, exactly as Oxylabs documents it (read 2026-10-31; Mariano's read 2026-11-02;
docs/DOCUMENTED_CONTRACT.md).

Only documented parameter names are accepted (:func:`assert_documented`): a payload with any other key is
refused before it can be planned, reserved or sent. There is no ``page`` parameter here: the documented one is
``start_page``, and :func:`next_page_payload` adds it only when the previous response itself says that page
exists.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ENDPOINT = "https://realtime.oxylabs.io/v1/queries"
# 1.7.0 (finding C1): the only place the credentials may go: this scheme, host and port, nothing else.
ENDPOINT_PARTS = ("https", "realtime.oxylabs.io", 443)
ENDPOINT_PATH = "/v1/queries"
RAW_AND_PARSED = "type=raw,parsed"  # each requested type is a separate entry of ``results``

WALMART_SEARCH = "walmart_search"
WALMART_PRODUCT = "walmart_product"
URL_ONLY = "url_only"  # "Any other Walmart page can be scraped by passing its url alone, no source needed."
# Mariano's (1.6.0): "Any other Mariano's page can be scraped by passing its url alone, no source needed."
MARIANOS_SEARCH = "marianos_search"
MARIANOS_PRODUCT = "marianos_product"

# Parameters each documented form accepts (the source's own page; docs/DOCUMENTED_CONTRACT.md gives the file).
DOCUMENTED_PARAMETERS: Mapping[str, frozenset[str]] = {
    WALMART_SEARCH: frozenset(
        {
            "source",
            "query",
            "start_page",
            "parse",
            "domain",
            "store_id",
            "delivery_zip",
            "fulfillment_type",
            "fulfillment_speed",
            "sort_by",
            "min_price",
            "max_price",
        }
    ),
    WALMART_PRODUCT: frozenset(
        {"source", "product_id", "parse", "domain", "store_id", "delivery_zip", "fulfillment_type"}
    ),
    URL_ONLY: frozenset({"url"}),
    # Mariano's page: no parse, domain, start_page or pages parameter is documented for either source.
    MARIANOS_SEARCH: frozenset(
        {"source", "query", "store_id", "delivery_zip", "fulfillment_type", "price_range", "brand"}
    ),
    MARIANOS_PRODUCT: frozenset({"source", "product_id", "store_id", "delivery_zip", "fulfillment_type"}),
}

# General features the source pages also allow ("Besides the parameters listed below, you can include
# additional parameters such as user_agent_type, geo_location, render, and more"): documented, and never used
# by this probe. ``geo_location`` on Walmart is on the forced-render list ("walmart | geo_location;
# search_with_video"), so it would change the billing class; ``render`` is rendered traffic; the others change
# what is requested.
NOT_USED_HERE: Mapping[str, str] = {
    "geo_location": "on Walmart it forces rendering (rendered traffic); the store is set with store_id "
    "instead",
    "render": "rendered traffic, billed as such; the collector's readers need only the served page",
    "user_agent_type": "the probe asks for the default request, as the collector's own readers were "
    "validated on",
    "browser_instructions": "page interaction is not part of this probe",
    "session_id": "the probe makes independent requests only",
    "callback_url": "the probe uses the Realtime method only",
}

MANDATORY: Mapping[str, tuple[str, ...]] = {
    WALMART_SEARCH: ("source", "query"),
    WALMART_PRODUCT: ("source", "product_id"),
    URL_ONLY: ("url",),
    MARIANOS_SEARCH: ("source", "query"),
    MARIANOS_PRODUCT: ("source", "product_id"),
}


class RequestRefused(ValueError):
    """A payload this probe will not plan, reserve or send."""


class UndocumentedRequest(RequestRefused):
    """A payload this probe cannot show to be documented."""


class FeatureNotUsed(RequestRefused):
    """A documented general feature this probe deliberately never uses (:data:`NOT_USED_HERE`)."""


def form_of(payload: Mapping[str, Any]) -> str:
    source = payload.get("source")
    if source is None:
        return URL_ONLY
    if source in (WALMART_SEARCH, WALMART_PRODUCT, MARIANOS_SEARCH, MARIANOS_PRODUCT):
        return str(source)
    raise UndocumentedRequest(f"source {source!r} is not one this probe uses")


def assert_documented(payload: Mapping[str, Any]) -> None:
    form = form_of(payload)
    unused = sorted(k for k in payload if k in NOT_USED_HERE)
    if unused:
        raise FeatureNotUsed(
            "; ".join(f"{k}: documented, but never used here ({NOT_USED_HERE[k]})" for k in unused)
        )
    unknown = set(payload) - DOCUMENTED_PARAMETERS[form]
    if unknown:
        raise UndocumentedRequest(f"parameters not documented for {form}: {sorted(unknown)}")
    missing = [k for k in MANDATORY[form] if not payload.get(k)]
    if missing:
        raise UndocumentedRequest(f"mandatory parameters missing for {form}: {missing}")
    if form != URL_ONLY:
        for key in ("store_id", "product_id"):  # documented as strings
            if key in payload and not isinstance(payload[key], str):
                raise UndocumentedRequest(f"{key} must be a string, as documented")
        if payload.get("fulfillment_type") == "pickup" and not payload.get("store_id"):
            raise UndocumentedRequest("fulfillment_type pickup is documented together with store_id")
        product_id = str(payload.get("product_id") or "")
        if form == MARIANOS_PRODUCT and not (product_id.isdigit() and len(product_id) == 13):
            raise UndocumentedRequest("the Mariano's product_id is documented as the 13-digit product ID")


def walmart_search(query: str, store_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": WALMART_SEARCH,
        "query": query,
        "store_id": store_id,
        "fulfillment_type": "pickup",
        "parse": True,
    }
    assert_documented(payload)
    return payload


def walmart_product(product_id: str, store_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": WALMART_PRODUCT,
        "product_id": product_id,
        "store_id": store_id,
        "fulfillment_type": "pickup",
        "parse": True,
    }
    assert_documented(payload)
    return payload


def marianos_search(query: str, store_id: str) -> dict[str, Any]:
    """The store's Pickup search. ``store_id`` is required with ``pickup`` (documented)."""
    payload: dict[str, Any] = {
        "source": MARIANOS_SEARCH,
        "query": query,
        "store_id": store_id,
        "fulfillment_type": "pickup",
    }
    assert_documented(payload)
    return payload


def marianos_product(product_id: str, store_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": MARIANOS_PRODUCT,
        "product_id": product_id,
        "store_id": store_id,
        "fulfillment_type": "pickup",
    }
    assert_documented(payload)
    return payload


def url_only(url: str) -> dict[str, Any]:
    """A retailer page by URL. The documentation states no store or fulfillment parameter for this form: its
    context can only be read from the page itself, and no store is claimed in advance."""
    payload: dict[str, Any] = {"url": url}
    assert_documented(payload)
    return payload


def next_page_payload(payload: Mapping[str, Any], page: int, last_visible_page: int | None) -> dict[str, Any]:
    """The next result page, only when the previous response says it exists."""
    if form_of(payload) != WALMART_SEARCH:
        raise UndocumentedRequest("start_page is documented for walmart_search only")
    if last_visible_page is None or page > last_visible_page:
        raise UndocumentedRequest(
            f"page {page} is not shown by the previous response (last {last_visible_page})"
        )
    out = {**payload, "start_page": page}
    assert_documented(out)
    return out
