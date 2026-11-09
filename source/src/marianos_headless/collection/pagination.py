"""Listing pages of a run: what one response states, whether it counts, and what is left (release 1.8.0).

The durable truth of a listing's progress is the ``listing_pages`` table, not the task's cursor: a page's row
and its products are committed in one transaction, so a worker killed between them leaves neither, and a
worker killed after them leaves a page a resume never asks for again. A page counts only when its row says
``completed``; a repeated, failed, empty, malformed, blocked or wrong-context response leaves a row of its own
and never moves the next page forward.

A retailer page may answer page 2 with page 1 and still say ``page: 2`` and ranks 25-48 (the search route at
store 53100502, Pickup, probe L18, 2026-11-02: the 24 products of page 1, in the same rank order). The page
number and the ranks are therefore checked but never trusted on their own: products are compared with the
listing's earlier pages by identity.

The end of a listing is evidenced by the source's own count, never by the last page: ``DONE`` needs as many
distinct products as the highest total the source reported during the read. There is no percentage below
that, and a window (``availableCount``) that hides results leaves the listing incomplete.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from marianos_headless.db.models import ListingPage
from marianos_headless.sites.marianos.search_state import SearchSummary

PAGE_SIZE = 24  # page.size on the retailer's own request; page 2 asks for offset 24 (probe L6, 2026-11-02)
GAP = "accessible pages exhausted; coverage incomplete"


class PageVerdict(StrEnum):
    NEW = "new"  # every product is new to the listing
    PARTIAL_OVERLAP = "partial_overlap"  # genuine next page that repeats some products of earlier pages
    REPEATED = "repeated"  # nothing new, in the order of an earlier page
    REORDERED_REPEAT = "reordered_repeat"  # nothing new, in another order
    EMPTY = "empty"  # no products where the source's count says there should be
    MALFORMED = "malformed"  # no page state, or no pagination metadata, or a state without its cards
    WRONG_CONTEXT = "wrong_context"  # another store or fulfillment
    WRONG_PAGE = "wrong_page"  # the source answered another page number
    WRONG_LISTING = "wrong_listing"  # the source answered another listing
    BLOCKED = "blocked"  # the site refused
    FAILED = "failed"  # the provider brought no page
    # Release 1.9.0 (M2): the response states other filters than the reading asked for (a brand reading
    # answered unfiltered or for another brand, a base listing answered with a filter applied).
    WRONG_FILTER = "wrong_filter"
    # Release 1.9.0 (M2): the response does not prove it answers the reading asked for: a filtered reading
    # whose page states no filter, a search ID that is not the page's latest, or a search still loading or in
    # error.
    UNBOUND = "unbound"


ACCEPTED = frozenset({PageVerdict.NEW, PageVerdict.PARTIAL_OVERLAP})
REPEATS = frozenset({PageVerdict.REPEATED, PageVerdict.REORDERED_REPEAT})
FILTER_VERDICTS = frozenset({PageVerdict.WRONG_FILTER, PageVerdict.UNBOUND})
# The unfiltered value of the site's scalar facets (every saved page of 2026-11-02 states these).
SCALAR_FACETS_UNFILTERED: Mapping[str, str] = {"fulfillment": "all", "price": ""}


@dataclass(frozen=True)
class PageFacts:
    """What one response states about itself."""

    requested_page: int
    returned_page: int | None
    loaded_pages: tuple[int, ...]
    taxonomy_id: str | None
    location_id: str | None
    modality: str | None
    total: int | None
    available: int | None
    organic: tuple[str, ...]  # the listing's own results, in rank order
    sponsored: tuple[str, ...]  # shown with rank 0
    cards: int  # product cards in the page's grid
    # Release 1.9.0 (M2): the search the response states it answers (see SearchSummary).
    filters: Mapping[str, Any] | None = None
    search_id: str | None = None
    latest_search_id: str | None = None
    loaded: bool | None = None
    loading: bool | None = None
    has_error: bool | None = None


@dataclass(frozen=True)
class Judgement:
    verdict: PageVerdict
    detail: str = ""
    new: tuple[str, ...] = ()
    duplicates: tuple[str, ...] = ()
    # A response that may answer properly when asked again (a search still loading, or in error).
    retry: bool = False
    # Release 1.9.0 (M2): what the response states about its filters and search binding.
    binding: Mapping[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.verdict in ACCEPTED


def page_facts(page: int, summary: SearchSummary | None, cards: int) -> PageFacts:
    if summary is None:
        return PageFacts(page, None, (), None, None, None, None, None, (), (), cards)
    return PageFacts(
        requested_page=page,
        returned_page=summary.page,
        loaded_pages=summary.loaded_pages,
        taxonomy_id=summary.taxonomy_id,
        location_id=summary.location_id,
        modality=summary.modality,
        total=summary.total,
        available=summary.available,
        organic=summary.organic,
        sponsored=summary.rank_zero,
        cards=cards,
        filters=summary.filters,
        search_id=summary.search_id,
        latest_search_id=summary.latest_search_id,
        loaded=summary.loaded,
        loading=summary.loading,
        has_error=summary.has_error,
    )


def filter_binding(
    facts: PageFacts, requested: Mapping[str, Any] | None
) -> tuple[PageVerdict | None, str, bool, dict[str, Any]]:
    """Whether the response proves it answers the reading asked for (release 1.9.0, M2).

    ``requested``: a filtered reading's descriptor (``filter`` and its exact ``value``), or None for the
    listing itself. Returns (verdict or None, detail, retry, the binding as stated). The response must be
    the page's latest search (``productsInfo.searchId`` = ``latestResponseSearchId``), loaded, not loading,
    without error; every facet list it states must be exactly the requested filter's value (``brandName``:
    ``[value]``) or empty, and the scalar facets unfiltered (``fulfillment`` "all", ``price`` ""). A filtered
    reading whose response states no filter at all is never proved; a page of the listing itself that states
    no request makes no claim (pages of earlier releases' fixtures)."""
    stated = dict(facts.filters) if facts.filters is not None else None
    want: dict[str, list[str]] = {}
    if requested:
        want[str(requested["filter"])] = [str(requested["value"])]
    binding: dict[str, Any] = {
        "requested": {k: v[0] for k, v in want.items()},
        "stated": {k: v for k, v in (stated or {}).items() if v not in ([], None)},
        "search_id": facts.search_id,
        "latest_search_id": facts.latest_search_id,
        "loaded": facts.loaded,
        "loading": facts.loading,
        "has_error": facts.has_error,
    }
    if facts.has_error is True or facts.loading is True or facts.loaded is False:
        return (
            PageVerdict.UNBOUND,
            f"the page's search is not a finished answer (loaded {facts.loaded}, loading {facts.loading}, "
            f"error {facts.has_error})",
            True,
            binding,
        )
    if facts.search_id and facts.latest_search_id and facts.search_id != facts.latest_search_id:
        return (
            PageVerdict.UNBOUND,
            f"the results are for search {facts.search_id}, the page's latest search is "
            f"{facts.latest_search_id}",
            True,
            binding,
        )
    if stated is None:
        if requested:
            return (
                PageVerdict.UNBOUND,
                f"the response states no search request: the {requested['filter']} reading "
                f"{requested['value']!r} cannot be proved",
                False,
                binding,
            )
        return None, "", False, binding
    wrong: list[str] = []
    for k, v in sorted(stated.items()):
        if isinstance(v, list):
            got = [str(x) for x in v]
            if got != want.get(k, []):
                wrong.append(f"{k} {got!r} (asked {want.get(k, [])!r})")
        elif k in SCALAR_FACETS_UNFILTERED and v != SCALAR_FACETS_UNFILTERED[k]:
            wrong.append(f"{k} {v!r} (unfiltered: {SCALAR_FACETS_UNFILTERED[k]!r})")
    for k in want:
        if k not in stated:
            return (
                PageVerdict.UNBOUND,
                f"the response does not state {k}: the reading {want[k][0]!r} cannot be proved",
                False,
                binding,
            )
    if wrong:
        return (
            PageVerdict.WRONG_FILTER,
            "the response states other filters: " + "; ".join(wrong),
            False,
            binding,
        )
    return None, "", False, binding


def judge(
    facts: PageFacts,
    *,
    taxonomy: str | None,
    earlier: Sequence[Sequence[str]],
    store_verified: bool,
    store_problem: str = "",
    requested_filter: Mapping[str, Any] | None = None,
) -> Judgement:
    """Whether a response may count as page ``facts.requested_page`` of the listing ``taxonomy`` (read
    through ``requested_filter`` when it is a filtered reading)."""
    page = facts.requested_page
    if not store_verified:
        return Judgement(
            PageVerdict.WRONG_CONTEXT, store_problem or "the page is not for the store and fulfillment"
        )
    if facts.returned_page is None or facts.total is None:
        return Judgement(PageVerdict.MALFORMED, "the response states no page number or no result count")
    if facts.returned_page != page or (facts.loaded_pages and page not in facts.loaded_pages):
        return Judgement(
            PageVerdict.WRONG_PAGE,
            f"page {page} was requested; the response says page {facts.returned_page}, loaded "
            f"{list(facts.loaded_pages)}",
        )
    if taxonomy is not None and facts.taxonomy_id != taxonomy:
        return Judgement(
            PageVerdict.WRONG_LISTING,
            f"listing {taxonomy} was requested; the response is for {facts.taxonomy_id}",
        )
    bad, why, retry, binding = filter_binding(facts, requested_filter)
    if bad is not None:
        return Judgement(bad, why, retry=retry, binding=binding)
    if not facts.organic:
        return Judgement(
            PageVerdict.EMPTY, f"no products on page {page} of {facts.total} results", binding=binding
        )
    seen = {u for rows in earlier for u in rows}
    new = tuple(u for u in facts.organic if u not in seen)
    again = tuple(u for u in facts.organic if u in seen)
    if not new:  # whatever the page shows of them: asking again would not bring anything else
        if any(tuple(rows) == facts.organic for rows in earlier):
            return Judgement(
                PageVerdict.REPEATED,
                f"page {page} repeats an earlier page exactly",
                (),
                again,
                binding=binding,
            )
        return Judgement(
            PageVerdict.REORDERED_REPEAT,
            f"page {page} shows only products of earlier pages, in another order",
            (),
            again,
            binding=binding,
        )
    if facts.cards < len(facts.organic):
        return Judgement(
            PageVerdict.MALFORMED,
            f"the page state lists {len(facts.organic)} products and the grid shows {facts.cards} cards",
            binding=binding,
        )
    if again:
        return Judgement(
            PageVerdict.PARTIAL_OVERLAP,
            f"{len(again)} products of earlier pages again",
            new,
            again,
            binding=binding,
        )
    return Judgement(PageVerdict.NEW, "", new, (), binding=binding)


def last_page(total: int | None, available: int | None) -> int | None:
    """The last page the source lets a reader reach (``None`` when it states no count)."""
    if total is None:
        return None
    reachable = total if available is None else min(total, available)
    return max(1, math.ceil(reachable / PAGE_SIZE))


def outcome(pages: int, totals: Iterable[int], available: int | None, unique: int) -> tuple[str, str]:
    """``DONE`` or ``INCOMPLETE`` with the reason, once the reachable pages were read."""
    seen_totals = sorted(set(totals))
    want = seen_totals[-1] if seen_totals else None
    changed = f" (the source's total changed during the read: {seen_totals})" if len(seen_totals) > 1 else ""
    if want is not None and unique >= want:
        return "DONE", ""
    window = (
        f"; the source lets a reader reach {available} of {want} results (availableCount)"
        if want is not None and available is not None and available < want
        else ""
    )
    return (
        "INCOMPLETE",
        f"{GAP}: {pages} page(s) read, {unique} distinct products of {want if want is not None else '?'} "
        f"reported{window}{changed}",
    )


def page_url(listing_url: str, page: int) -> str:
    """The retailer's own address of a listing's page: the listing as linked, with ``page=N`` from page 2. The
    site menu's ``pzn=relevance`` is left out: every page of a read must use one ordering, and the page test
    (probes L2, L9, L10, L12) was made without it."""
    parts = urlsplit(listing_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in ("pzn", "page")]
    if page > 1:
        query.append(("page", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, quote_via=quote), ""))


FILTER_MARK = "~"  # a filtered reading of a listing: "<listing ID>~<digest of its full identity>"
PARTITION_SCHEME = 2  # 1: "<listing>~<brand>"[:64] (to 1.8.0rc5); 2: a digest of the full identity (1.9.0)
PARTITION_ID_HEX = 24  # 96 bits of the SHA-256 digest in the ID; the full digest is the page rows' key


def listing_id(taxonomy_id: str) -> str:
    """The retailer's listing ID of a planned listing or of a filtered reading of it."""
    return taxonomy_id.split(FILTER_MARK, 1)[0]


def partition_descriptor(
    *, store_id: str, modality: str, listing: str, filter_name: str, value: str
) -> dict[str, Any]:
    """The full identity of a filtered reading (release 1.9.0, M1): the retailer, the store and fulfillment,
    the listing, the filter and its exact value as the source names it (never trimmed, folded or cut)."""
    return {
        "scheme": PARTITION_SCHEME,
        "retailer": "marianos",
        "store_id": str(store_id),
        "modality": str(modality),
        "listing": str(listing),
        "filter": str(filter_name),
        "value": str(value),
    }


def canonical(descriptor: Mapping[str, Any]) -> str:
    return json.dumps(dict(descriptor), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def partition_digest(descriptor: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(descriptor).encode("utf-8")).hexdigest()


def partition_id(descriptor: Mapping[str, Any]) -> str:
    """``<listing>~<first 24 hex of the digest>``: at most 10 + 1 + 24 characters, so no column cuts it;
    two values that differ anywhere (even past the 64th character) get different IDs."""
    return f"{descriptor['listing']}{FILTER_MARK}{partition_digest(descriptor)[:PARTITION_ID_HEX]}"


def facet_key(name: str) -> str:
    """How a person would read a facet value: NFC, case-folded, spaces collapsed. Only for warnings: the
    reading always uses the exact value."""
    return " ".join(unicodedata.normalize("NFC", name).casefold().split())


def brand_partitions(
    listing_url: str,
    taxonomy_id: str,
    brands: Iterable[Mapping[str, Any]],
    *,
    store_id: str,
    modality: str,
) -> list[dict[str, Any]]:
    """A listing above the window with no child listing, subdivided by the retailer's own brand filter: one
    filtered reading per brand value the page names, by its exact value. Never a search term of ours. Each
    stays incomplete when the source's count is not reached, and the parent stays incomplete when the brands
    do not cover its total.

    Release 1.9.0 (M1): each reading's ID is a digest of its full identity (:func:`partition_descriptor`),
    and the descriptor travels with it (the task's node, the page rows). A value the facet names twice is read
    once (the repeat is noted); values that differ only in case, Unicode form or spacing are distinct values
    of the source, each read, and noted as a group."""
    out: list[dict[str, Any]] = []
    first: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[str]] = {}
    for b in brands:
        name = str(b["name"])
        if name in first:
            first[name].setdefault("notes", []).append(
                f"the brand facet names {name!r} again (count {b.get('count')}): read once"
            )
            continue
        groups.setdefault(facet_key(name), []).append(name)
        parts = urlsplit(listing_url)
        query = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in ("pzn", "page")
        ]
        url = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode([*query, ("brandName", name)], quote_via=quote),
                "",
            )
        )
        desc = partition_descriptor(
            store_id=store_id,
            modality=modality,
            listing=listing_id(taxonomy_id),
            filter_name="brandName",
            value=name,
        )
        entry = {
            "id": partition_id(desc),
            "name": name,
            "slug": "",
            "count": b.get("count"),
            "url": url,
            "filter": "brandName",
            "descriptor": desc,
            "partition_key": partition_digest(desc),
        }
        first[name] = entry
        out.append(entry)
    for names in groups.values():
        if len(names) > 1:
            for n in names:
                first[n].setdefault("notes", []).append(
                    "distinct values of the source that read alike: " + ", ".join(repr(x) for x in names)
                )
    return out


def node_filter(partition_filter: str) -> dict[str, Any] | None:
    """A node's filtered-reading descriptor (its canonical JSON), or None for a listing itself."""
    return dict(json.loads(partition_filter)) if partition_filter else None


def legacy_partition(taxonomy_id: str, partition_filter: str) -> bool:
    """A filtered reading planned before release 1.9.0: its ID was ``<listing>~<brand>`` cut at 64
    characters (two brands could share it) and no descriptor travelled with it."""
    return FILTER_MARK in taxonomy_id and not partition_filter


# -- the table ----------------------------------------------------------------------------------------------


def rows_of(
    s: Session, run_id: str, category_source_id: str, taxonomy_id: str, partition_key: str = ""
) -> list[ListingPage]:
    return list(
        s.scalars(
            select(ListingPage)
            .where(
                ListingPage.run_id == run_id,
                ListingPage.category_source_id == category_source_id,
                ListingPage.taxonomy_id == taxonomy_id,
                ListingPage.partition_key == partition_key,
            )
            .order_by(ListingPage.requested_page, ListingPage.attempt)
        )
    )


def completed_pages(rows: Iterable[ListingPage]) -> list[ListingPage]:
    """The listing's completed pages from page 1 without a gap: the next page is one past them."""
    by_page = {r.requested_page: r for r in rows if r.state == "completed"}
    out: list[ListingPage] = []
    while (len(out) + 1) in by_page:
        out.append(by_page[len(out) + 1])
    return out


def next_attempt(
    s: Session, run_id: str, category_source_id: str, taxonomy_id: str, page: int, partition_key: str = ""
) -> int:
    last = s.scalar(
        select(func.max(ListingPage.attempt)).where(
            ListingPage.run_id == run_id,
            ListingPage.category_source_id == category_source_id,
            ListingPage.taxonomy_id == taxonomy_id,
            ListingPage.partition_key == partition_key,
            ListingPage.requested_page == page,
        )
    )
    return int(last or 0) + 1


def row_summary(r: ListingPage) -> dict[str, Any]:
    """One page's line in the reports."""
    return {
        "taxonomy_id": r.taxonomy_id,
        "csv_row": r.csv_row_index,
        "url": r.url,
        "route": r.route,
        "requested_page": r.requested_page,
        "returned_page": r.returned_page,
        "attempt": r.attempt,
        "state": r.state,
        "verdict": r.verdict,
        "detail": r.detail,
        "total": r.total,
        "available": r.available,
        "identities": len(r.identities or []),
        "children": len(r.children or []),
        "new": r.new_count,
        "duplicates": r.duplicates,
        "excluded": r.excluded,
        "conflicts": r.conflicts,
        "sha256": r.response_sha256,
        "provider_request_id": r.provider_request_id,
    }
