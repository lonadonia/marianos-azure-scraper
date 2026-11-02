"""The Mariano's part of a campaign (added in 1.6.0): a short fixed sequence of documented requests, each
reserved before it is sent, for Mariano's Vernon Hills (store 53100502, 1720 N Milwaukee Ave, Vernon Hills,
IL 60061), Pickup.

Steps, in order (docs/PAYLOAD_MATRIX.md):

1. ``marianos-search-p1``: ``marianos_search`` for the target's query with ``store_id`` and
   ``fulfillment_type`` ``pickup``. Mariano's documentation names no ``parse`` for its sources and returns
   the page HTML in ``content``, so the request asks for the default output: one result is reserved.
2. ``marianos-product``: ``marianos_product`` for page 1's first ranked product (a sponsored placement is
   never chosen), the same store and Pickup. Mariano's product pages are on the documented forced-rendering
   list.
3. ``marianos-category-url``: a required category page (``/pl/<slug>/<id>``) by its URL alone. The
   documentation states no store or fulfillment parameter for this form, and category pages are also
   force-rendered. A page for another store or fulfillment stops the campaign; it is last for that reason.

Not planned, because the documentation does not provide it: any page after the first. ``marianos_search``
documents no ``start_page`` or ``pages``, and a listing URL with ``page=2`` could only be sent by URL alone,
with no store. Listing pagination through Classic stays an open, stated gap (docs/DOCUMENTED_CONTRACT.md).
Page 1 of a search is never presented as category coverage.

What a page shows is read from its own state (``window.__INITIAL_STATE__``) with the Mariano's collector's
reader (``vendor/marianos_initial_state.py``, unchanged): the shopper's selected modality and store
(``getModalityPreferences``), the search's own ``requestVars`` (``locationId``, ``activeModalityType``,
``page``), and each product's ``price.storePrices.sourceLocationId``. The paths are the ones the collector
reads (``marianos_headless/sites/marianos/search_state.py``), recorded with the saved pages they were
checked on.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from classic_probe import checks, contract
from classic_probe.campaign import Campaign, StepPlan
from classic_probe.stops import Stop
from classic_probe.targets import Target
from classic_probe.vendor.marianos_initial_state import InitialStateNotFound, dig, parse_initial_state

SEARCH_PATH = ("calypso", "useCases", "getProducts", "search-grid", "response", "data")
SEARCH_VARS = ("search", "searchAll", "requestVars")
SEARCH_RESPONSE = (
    "search",
    "searchAll",
    "response",
)  # ranks (searchEngineRank), sponsoredItems, productsInfo
PREFERENCES = (
    "calypso",
    "useCases",
    "getModalityPreferences",
    "default",
    "response",
    "data",
    "modalityPreferences",
)
PRODUCTS_DOMAIN = ("calypso", "domains", "products")
# A refusal page instead of the retailer's page (the collector's challenge markers for Mariano's).
REFUSAL = re.compile(
    r"Access Denied|Reference\s*#\d|/_sec/cp_challenge|px-captcha|Pardon Our Interruption", re.I
)


def search_step(target: Target) -> StepPlan:
    return StepPlan(
        "marianos-search-p1",
        "result page 1 of the store's Pickup search: store, fulfillment, products and their store prices",
        "search",
        contract.MARIANOS_SEARCH,
        contract.marianos_search(target.search_query, target.store_id),
        "",
        1,
    )


def product_step(target: Target, upc: str) -> StepPlan:
    return StepPlan(
        "marianos-product",
        "the product's own page for the store's Pickup: identity, store of its prices, fulfillment",
        "product",
        contract.MARIANOS_PRODUCT,
        contract.marianos_product(upc, target.store_id),
        "",
        1,
    )


def category_step(target: Target) -> StepPlan:
    return StepPlan(
        "marianos-category-url",
        "a required category page by its URL alone: is it served for the store and Pickup at all "
        "(undocumented)",
        "category",
        contract.URL_ONLY,
        contract.url_only(target.category_probe_url),
        "",
        1,
    )


def planned_steps(target: Target) -> list[StepPlan]:
    """The steps as planned before any response (the product depends on page 1)."""
    steps = [search_step(target), product_step(target, "0000000000000")]
    if target.category_probe_url:
        steps.append(category_step(target))
    return steps


NOT_PLANNED = {
    "marianos-search-p2": "marianos_search documents no start_page or pages parameter; a page-2 URL could "
    "only be sent by URL alone, without store_id or fulfillment_type. Not sent: listing pagination through "
    "Classic is an open gap.",
}


# -- reading a response --------------------------------------------------------------------------------------


def _raw(ins: checks.Inspection) -> Mapping[str, Any] | None:
    for r in ins.facts.get("results") or []:
        if isinstance(r, Mapping) and isinstance(r.get("content"), str):
            return r
    ins.fail(Stop.UNSUPPORTED_RESPONSE, "no result holds the page HTML in content")
    return None


def _state(ins: checks.Inspection, raw: Mapping[str, Any], *, product: bool) -> dict[str, Any] | None:
    code = int(raw["status_code"])
    html = str(raw.get("content") or "")
    if code == 404 and product:
        ins.fail(Stop.WRONG_IDENTITY, "the retailer answered 404 for the product")
        return None
    if not 200 <= code < 300:
        ins.fail(Stop.BLOCKED, f"the retailer answered {code}")
        return None
    if not html:
        ins.fail(Stop.UNSUPPORTED_RESPONSE, "the result has no page")
        return None
    try:
        return parse_initial_state(html)
    except (InitialStateNotFound, ValueError):
        if REFUSAL.search(html):
            ins.fail(Stop.BLOCKED, "a refusal page: " + REFUSAL.search(html).group(0))  # type: ignore[union-attr]
        else:
            ins.fail(
                Stop.UNVERIFIED_CONTEXT, "the page holds no state to read the store and fulfillment from"
            )
        return None


def selected_context(state: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """The shopper's selected store and modality, as the page states them."""
    prefs = dig(state, *PREFERENCES, default=None)
    modalities = prefs.get("modalities") if isinstance(prefs, Mapping) else None
    if not isinstance(modalities, list) or not modalities or not isinstance(modalities[0], Mapping):
        return None, None
    first = modalities[0]
    location = dig(first, "destination", "locationId")
    modality = first.get("modalityType")
    return (str(location) if location else None, str(modality) if modality else None)


def product_stores(products: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Each product's ``price.storePrices.sourceLocationId`` (the store its prices are for)."""
    out = {}
    for p in products:
        upc = str(p.get("upc") or p.get("id") or "")
        loc = dig(p, "price", "storePrices", "sourceLocationId")
        if upc and loc:
            out[upc] = str(loc)
    return out


def _context(ins: checks.Inspection, state: Mapping[str, Any], store_id: str) -> bool:
    location, modality = selected_context(state)
    ins.facts.update(selected_location_id=location, selected_modality=modality)
    if location is None or modality is None:
        ins.fail(Stop.UNVERIFIED_CONTEXT, "the page states no selected store or modality")
        return False
    if location != store_id:
        ins.fail(Stop.WRONG_CONTEXT, f"the page is for store {location}, not {store_id}")
        return False
    if modality != "PICKUP":
        ins.fail(Stop.WRONG_CONTEXT, f"the page is for {modality}, not PICKUP")
        return False
    return True


def search_page(ins: checks.Inspection, store_id: str) -> checks.Inspection:
    raw = _raw(ins)
    if raw is None:
        return ins
    state = _state(ins, raw, product=False)
    if state is None or not _context(ins, state, store_id):
        return ins
    rv = dig(state, *SEARCH_VARS, default={}) or {}
    resp = dig(state, *SEARCH_RESPONSE, default={}) or {}
    data = dig(state, *SEARCH_PATH, default={}) or {}
    products = [p for p in (data.get("products") or []) if isinstance(p, Mapping)]
    listed = (
        [p for p in (resp.get("products") or []) if isinstance(p, Mapping)]
        if isinstance(resp, Mapping)
        else []
    )
    ranked = sorted(
        (p for p in listed if isinstance(p.get("searchEngineRank"), int) and p["searchEngineRank"] > 0),
        key=lambda p: int(p["searchEngineRank"]),
    )
    stores = product_stores(products)
    info = (resp.get("productsInfo") or {}) if isinstance(resp, Mapping) else {}
    ins.facts.update(
        request_location_id=rv.get("locationId"),
        request_modality=rv.get("activeModalityType"),
        page=rv.get("page"),
        total=info.get("totalCount"),
        available=info.get("availableCount"),
        ranked_upcs=[str(p.get("upc")) for p in ranked],
        sponsored_upcs=[
            str(i.get("upc")) for i in resp.get("sponsoredItems") or [] if isinstance(i, Mapping)
        ],
        product_stores=sorted(set(stores.values())),
    )
    if str(rv.get("locationId") or "") != store_id or str(rv.get("activeModalityType") or "") != "PICKUP":
        return ins.fail(
            Stop.WRONG_CONTEXT,
            f"the search ran for {rv.get('locationId')} {rv.get('activeModalityType')}, "
            f"not {store_id} PICKUP",
        )
    other = sorted({loc for loc in stores.values() if loc != store_id})
    if other:
        return ins.fail(Stop.WRONG_CONTEXT, f"prices on the page are for other stores: {other}")
    if rv.get("page") not in (None, 1):
        return ins.fail(Stop.WRONG_CONTEXT, f"page 1 was asked for; the page says {rv.get('page')}")
    if not ranked:
        return ins.fail(Stop.EMPTY_RESPONSE, "no ranked product on page 1")
    return ins


def product_page(ins: checks.Inspection, store_id: str, upc: str) -> checks.Inspection:
    raw = _raw(ins)
    if raw is None:
        return ins
    state = _state(ins, raw, product=True)
    if state is None or not _context(ins, state, store_id):
        return ins
    domain = dig(state, *PRODUCTS_DOMAIN, default={}) or {}
    held = sorted(str(k) for k in domain) if isinstance(domain, Mapping) else []
    ins.facts["products_in_state"] = held
    entry = dig(domain, upc, "data", default=None) if isinstance(domain, Mapping) else None
    if not isinstance(entry, Mapping):
        return ins.fail(Stop.WRONG_IDENTITY, f"the page holds no product {upc} (it holds {held[:5]})")
    loc = dig(entry, "price", "storePrices", "sourceLocationId")
    ins.facts["product_price_location_id"] = loc
    if loc is None:
        return ins.fail(Stop.UNVERIFIED_CONTEXT, "the product's prices state no store")
    if str(loc) != store_id:
        return ins.fail(Stop.WRONG_CONTEXT, f"the product's prices are for store {loc}, not {store_id}")
    return ins


def category_page(ins: checks.Inspection, store_id: str) -> checks.Inspection:
    raw = _raw(ins)
    if raw is None:
        return ins
    state = _state(ins, raw, product=False)
    if state is None or not _context(ins, state, store_id):
        return ins
    data = dig(state, *SEARCH_PATH, default={}) or {}
    products = [p for p in (data.get("products") or []) if isinstance(p, Mapping)]
    other = sorted({loc for loc in product_stores(products).values() if loc != store_id})
    ins.facts.update(products=len(products), total=(data.get("productsInfo") or {}).get("totalCount"))
    if other:
        return ins.fail(Stop.WRONG_CONTEXT, f"prices on the page are for other stores: {other}")
    if not products:
        return ins.fail(Stop.EMPTY_RESPONSE, "no product on the category page")
    return ins


# -- the sequence --------------------------------------------------------------------------------------------


class MarianosCampaign(Campaign):
    """The Mariano's steps on the campaign's shared ledger: the Walmart steps' limits, never fresh ones."""

    adapter = "marianos"

    def _run(self) -> None:
        problems = self.target.live_problems()
        if problems:
            self._stop(Stop.UNVERIFIED_CONTEXT, "; ".join(problems))
            return
        first = self._dispatch(search_step(self.target), lambda i: search_page(i, self.target.store_id))
        if first is None:
            return
        self.ledger.event("SKIPPED", "marianos-search-p2: " + NOT_PLANNED["marianos-search-p2"])
        ranked = list(first.facts.get("ranked_upcs") or [])
        if ranked:
            upc = ranked[0]
            got = self._dispatch(
                product_step(self.target, upc), lambda i: product_page(i, self.target.store_id, upc)
            )
            if got is None:
                return
        if self.target.category_probe_url:
            self._dispatch(category_step(self.target), lambda i: category_page(i, self.target.store_id))
