"""What a server-rendered Mariano's page states about its products and its search (release 1.3.0).

A page fetched without a browser (the Oxylabs Web API) carries in its page state what the browser collector
read from the site's data responses: the product objects of the page (``calypso.domains.products.<upc>.data``,
the same shape as ``/atlas/v1/product/v2/products``) and the search's own summary
(``search.searchAll``: the request's store, modality, query and page; ``productsInfo.totalCount`` and
``availableCount``, the site's 250-result window; the result UPCs and the sponsored ones). Observed on the
probe pages of 2026-10-28 (store 53100503, In Store).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from marianos_headless.sites.marianos.initial_state import dig

PRODUCTS_PATH = ("calypso", "domains", "products")
SEARCH_PATH = ("search", "searchAll")


def state_products(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The page's product objects, in the order the page state holds them."""
    out: list[dict[str, Any]] = []
    for value in (dig(state, *PRODUCTS_PATH, default={}) or {}).values():
        data = value.get("data") if isinstance(value, Mapping) else None
        if isinstance(data, Mapping) and data.get("id"):
            out.append(dict(data))
    return out


@dataclass(frozen=True)
class SearchSummary:
    query: str | None
    page: int | None
    location_id: str | None
    modality: str | None
    total: int | None  # productsInfo.totalCount: the results the site reports
    available: int | None  # productsInfo.availableCount: the results its search lets a page reach
    upcs: tuple[str, ...]  # the result UPCs of this page, in order
    sponsored: tuple[str, ...]  # UPCs placed as sponsored on this page
    sub_commodities: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # upc -> codes
    ways_to_shop: tuple[str, ...] = ()
    # Release 1.8.0: the listing the response is for and its page facts. ``ranks`` holds each product's
    # ``searchEngineRank`` on the page: 1-24 on page 1, 25-48 on page 2; 0 for a sponsored placement.
    taxonomy_id: str | None = None
    loaded_pages: tuple[int, ...] = ()
    ranks: Mapping[str, int] = field(default_factory=dict)
    # Release 1.9.0: what the response states about the search it answers (M2). ``filters``: every
    # ``requestVars`` entry other than the listing, page, store, modality and query (``brandName`` and the
    # site's other facet lists, ``fulfillment`` "all", ``price`` ""), None when the page states no request.
    # ``search_id`` (``productsInfo.searchId``) must be the page's ``latestResponseSearchId``, and the search
    # must be loaded, not loading, without error (``loaded``, ``loading``, ``hasError``). Observed on all 99
    # saved pages of 2026-11-02 (store 53100502, Pickup): BINDING_SCAN.csv in the 1.9.0 evidence.
    filters: Mapping[str, Any] | None = None
    search_id: str | None = None
    latest_search_id: str | None = None
    loaded: bool | None = None
    loading: bool | None = None
    has_error: bool | None = None

    @property
    def organic(self) -> tuple[str, ...]:
        """The results of the listing itself, in rank order."""
        return tuple(sorted((u for u, r in self.ranks.items() if r > 0), key=lambda u: self.ranks[u]))

    @property
    def rank_zero(self) -> tuple[str, ...]:
        return tuple(u for u, r in self.ranks.items() if r == 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "page": self.page,
            "location_id": self.location_id,
            "modality": self.modality,
            "total": self.total,
            "available": self.available,
            "upcs": list(self.upcs),
            "sponsored": list(self.sponsored),
            "ways_to_shop": list(self.ways_to_shop),
        }


def _map(v: Any) -> Mapping[str, Any]:
    return v if isinstance(v, Mapping) else {}


def _int(v: Any) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _bool(v: Any) -> bool | None:
    return v if isinstance(v, bool) else None


# requestVars entries that name the listing, page, store and modality (checked on their own), not filters.
REQUEST_CORE = frozenset({"taxonomyId", "page", "locationId", "activeModalityType", "query"})


def search_summary(state: Mapping[str, Any]) -> SearchSummary | None:
    sa = dig(state, *SEARCH_PATH, default=None)
    if not isinstance(sa, Mapping):
        return None
    rv = _map(sa.get("requestVars"))
    resp = _map(sa.get("response"))
    info = _map(resp.get("productsInfo"))
    subs: dict[str, tuple[str, ...]] = {}
    ranks: dict[str, int] = {}
    for p in resp.get("products") or []:
        if isinstance(p, Mapping) and p.get("upc"):
            subs[str(p["upc"])] = tuple(str(c) for c in p.get("subCommodityCode") or [])
            rank = _int(p.get("searchEngineRank"))
            if rank is not None:
                upc = str(p["upc"])
                # A product both placed and ranked counts by its rank.
                ranks[upc] = max(rank, ranks.get(upc, 0))
    return SearchSummary(
        query=str(rv.get("query")) if rv.get("query") is not None else None,
        page=_int(rv.get("page")),
        location_id=str(rv.get("locationId")) if rv.get("locationId") else None,
        modality=str(rv.get("activeModalityType")) if rv.get("activeModalityType") else None,
        total=_int(info.get("totalCount")),
        available=_int(info.get("availableCount")),
        upcs=tuple(str(u) for u in resp.get("upcs") or []),
        sponsored=tuple(
            str(i.get("upc"))
            for i in resp.get("sponsoredItems") or []
            if isinstance(i, Mapping) and i.get("upc")
        ),
        sub_commodities=subs,
        ways_to_shop=tuple(
            str(w.get("slug") or w.get("name"))
            for w in info.get("waysToShop") or []
            if isinstance(w, Mapping)
        ),
        taxonomy_id=str(rv.get("taxonomyId")) if rv.get("taxonomyId") else None,
        loaded_pages=tuple(n for n in (_int(x) for x in resp.get("loadedPages") or []) if n is not None),
        ranks=ranks,
        filters={k: v for k, v in rv.items() if k not in REQUEST_CORE} if rv else None,
        search_id=str(info["searchId"]) if info.get("searchId") else None,
        latest_search_id=str(sa["latestResponseSearchId"]) if sa.get("latestResponseSearchId") else None,
        loaded=_bool(sa.get("loaded")),
        loading=_bool(sa.get("loading")),
        has_error=_bool(sa.get("hasError")),
    )


def listing_children(state: Mapping[str, Any], taxonomy: str) -> list[dict[str, Any]]:
    """The child listings the page's own filter tree names for ``taxonomy`` (``productsInfo.departments``,
    with ``categories`` and their ``subcategories``), with the count the site states for this store and
    fulfillment.
    Observed on the probe pages of 2026-11-02 (store 53100502, Pickup)."""
    info = _map(_map(dig(state, *SEARCH_PATH, default=None)).get("response")).get("productsInfo")
    stack: list[Any] = list(_map(info).get("departments") or [])
    while stack:
        n = stack.pop()
        if not isinstance(n, Mapping):
            continue
        kids = n.get("categories") or n.get("subcategories") or []
        if str(n.get("id")) == taxonomy:
            return [
                {
                    "id": str(c.get("id")),
                    "name": str(c.get("name") or ""),
                    "slug": str(c.get("slug") or ""),
                    "count": _int(c.get("count")),
                }
                for c in kids
                if isinstance(c, Mapping)
                and str(c.get("id", "")).startswith(taxonomy)
                and str(c.get("id")) != taxonomy
                and c.get("slug")
            ]
        stack.extend(kids)
    return []


def brand_facets(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The listing's brand filter (``productsInfo.brands``), with the count the site states for each brand at
    this store and fulfillment. The site filters a listing by it (``?brandName=General%20Mills``, probe L20,
    2026-11-02: 8 of Cold Cereal's 277 results)."""
    info = _map(_map(dig(state, *SEARCH_PATH, default=None)).get("response")).get("productsInfo")
    return [
        {"name": str(b.get("name")), "count": _int(b.get("count"))}
        for b in _map(info).get("brands") or []
        if isinstance(b, Mapping) and b.get("name")
    ]


def taxonomy_ids(product: Mapping[str, Any], sub_commodities: tuple[str, ...] = ()) -> list[str]:
    """The site's listing IDs a product belongs to, most specific first: department + commodity +
    sub-commodity (``0300100001``, the IDs of the menu's ten-digit listings such as Shrimp ``0501000009``),
    department + commodity (``03`` + ``001`` = ``03001``, the ID in ``/pl/cereal-granola/03001``), then the
    department alone (the department-level routes ``/pl/school-office/35``). From the product's own
    ``item.taxonomies`` and the search response's ``subCommodityCode``."""
    levels: list[list[str]] = [[], [], []]
    for t in dig(product, "item", "taxonomies", default=[]) or []:
        if not isinstance(t, Mapping):
            continue
        dept = str(dig(t, "department", "code", default="") or "")
        comm = str(dig(t, "commodity", "code", default="") or "")
        sub = str(dig(t, "subCommodity", "code", default="") or "")
        if dept and comm and sub:
            levels[0].append(dept + comm + sub)
        if dept and comm:
            levels[1].append(dept + comm)
        if dept:
            levels[2].append(dept)
    for code in sub_commodities:
        if code.isdigit() and len(code) == 10:
            levels[0].append(code)
            levels[1].append(code[:5])
            levels[2].append(code[:2])
    return list(dict.fromkeys(levels[0] + levels[1] + levels[2]))


def price_location(product: Mapping[str, Any]) -> str | None:
    """The store the product's displayed prices are for (``price.storePrices.sourceLocationId``)."""
    value = dig(product, "price", "storePrices", "sourceLocationId", default=None)
    return str(value) if value else None
