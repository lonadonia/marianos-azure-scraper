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

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
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


ACCEPTED = frozenset({PageVerdict.NEW, PageVerdict.PARTIAL_OVERLAP})
REPEATS = frozenset({PageVerdict.REPEATED, PageVerdict.REORDERED_REPEAT})


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


@dataclass(frozen=True)
class Judgement:
    verdict: PageVerdict
    detail: str = ""
    new: tuple[str, ...] = ()
    duplicates: tuple[str, ...] = ()

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
    )


def judge(
    facts: PageFacts,
    *,
    taxonomy: str | None,
    earlier: Sequence[Sequence[str]],
    store_verified: bool,
    store_problem: str = "",
) -> Judgement:
    """Whether a response may count as page ``facts.requested_page`` of the listing ``taxonomy``."""
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
    if not facts.organic:
        return Judgement(PageVerdict.EMPTY, f"no products on page {page} of {facts.total} results")
    seen = {u for rows in earlier for u in rows}
    new = tuple(u for u in facts.organic if u not in seen)
    again = tuple(u for u in facts.organic if u in seen)
    if not new:  # whatever the page shows of them: asking again would not bring anything else
        if any(tuple(rows) == facts.organic for rows in earlier):
            return Judgement(PageVerdict.REPEATED, f"page {page} repeats an earlier page exactly", (), again)
        return Judgement(
            PageVerdict.REORDERED_REPEAT,
            f"page {page} shows only products of earlier pages, in another order",
            (),
            again,
        )
    if facts.cards < len(facts.organic):
        return Judgement(
            PageVerdict.MALFORMED,
            f"the page state lists {len(facts.organic)} products and the grid shows {facts.cards} cards",
        )
    if again:
        return Judgement(
            PageVerdict.PARTIAL_OVERLAP, f"{len(again)} products of earlier pages again", new, again
        )
    return Judgement(PageVerdict.NEW, "", new, ())


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


FILTER_MARK = "~"  # a filtered reading of a listing: "<listing ID>~<brand>"


def listing_id(taxonomy_id: str) -> str:
    """The retailer's listing ID of a planned listing or of a filtered reading of it."""
    return taxonomy_id.split(FILTER_MARK, 1)[0]


def brand_partitions(
    listing_url: str, taxonomy_id: str, brands: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """A listing above the window with no child listing, subdivided by the retailer's own brand filter: one
    filtered reading per brand the page names. Never a search term of ours. Each stays incomplete when the
    source's count is not reached, and the parent stays incomplete when the brands do not cover its total."""
    out: list[dict[str, Any]] = []
    for b in brands:
        name = str(b["name"])
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
        out.append(
            {
                "id": f"{taxonomy_id}{FILTER_MARK}{name}"[:64],
                "name": name,
                "slug": "",
                "count": b.get("count"),
                "url": url,
                "filter": "brandName",
            }
        )
    return out


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
