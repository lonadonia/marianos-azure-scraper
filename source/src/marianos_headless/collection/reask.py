"""Listing requests set aside and asked again later in the same logical run (release 1.10.0, change C1).

What was seen (stages of 2026-11-09, store 53100502, Pickup; ``review/TECHNICAL_REPORT_1.9.0.md`` section
3): some answers to a listing's page N list exactly its page 1's products, and some first pages of a listing
above the source's window carry no child listing and no brand to subdivide it by. Such answers came in
clusters in time; minutes later the same address was answered properly. Why is not established, and nothing
here depends on a cause.

What this does. The request is set aside: the listing's task waits, the run's other listings go first, and
the very same request (address, page, listing, filter, store, fulfillment) is asked again once
``reask_min_wait_seconds`` have passed since its previous answer or attempt, at most
``max_reasks_per_request`` more times (never more than two) in the run. An answer is judged as any other:
by its products' identities and its verified context, never by its page number, its ranks, its search ID or
its request ID. A repeat counts no product; when the re-asks are spent the listing stays incomplete with
the reason it had, and nothing says the listing was read to its end.

The ceiling holds across lanes, restarts and a worker killed while a request is out, because it is kept in
the database (:class:`~marianos_headless.db.models.DeferredRequest`): ``reasks_dispatched`` is raised and
committed before each re-ask is sent, the table's own constraints refuse a value above ``max_reasks`` or a
``max_reasks`` above 2, and a re-ask is sent once (no transport retry of its own). Each re-ask is reserved in
the spending ledger and checked against every limit like any other submission.

Every answer is kept (``attempts``), the first one included and unchanged when a later one counts: what was
asked, what the answer states about itself, its stored page's hash, the provider's request ID, the distinct
products before and after, the overlap, the verdict and what followed. What is not available is said so in
words (:func:`unavailable`), never left as an empty value.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from marianos_headless.collection import pagination
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.pagination import Judgement, PageFacts
from marianos_headless.core.settings import StoreConfig
from marianos_headless.core.timeutil import iso
from marianos_headless.db.models import DeferredRequest, ListingPage

MIN_WAIT_S = 300  # five minutes: the shortest wait before a request is asked again
REPEATED_PAGE = "repeated_page"
MISSING_FACETS = "missing_facets"
WAITING, RECOVERED, EXHAUSTED = "waiting", "recovered", "exhausted"
FIRST_ANSWER, REASK, NOT_SENT = "first answer", "re-ask", "re-ask not sent"
NO_FACETS = (
    "the first page names no child listing and no brand: the listing ({total} results, {available} "
    "reachable) cannot be subdivided"
)
NOT_EXHAUSTED = (
    "the re-asks are spent, which says nothing about where the listing ends: its remaining results were "
    "not read"
)


def unavailable(why: str) -> str:
    """Evidence that does not exist, said in words."""
    return f"unavailable: {why}"


@dataclass(frozen=True)
class Policy:
    max_reasks: int = 0
    min_wait_s: int = MIN_WAIT_S

    def __post_init__(self) -> None:
        if not 0 <= self.max_reasks <= 2:
            raise ValueError("a request is asked again at most twice")
        if self.min_wait_s < MIN_WAIT_S:
            raise ValueError(f"a request is asked again after at least {MIN_WAIT_S} seconds")

    @property
    def enabled(self) -> bool:
        return self.max_reasks > 0


@dataclass(frozen=True)
class Key:
    """One logical request of a run: a page of a listing, or of a filtered reading of it."""

    run_id: str
    category_source_id: str
    taxonomy_id: str
    partition_key: str
    page: int


def find(s: Session, key: Key, *, lock: bool = False) -> DeferredRequest | None:
    q = select(DeferredRequest).where(
        DeferredRequest.run_id == key.run_id,
        DeferredRequest.category_source_id == key.category_source_id,
        DeferredRequest.taxonomy_id == key.taxonomy_id,
        DeferredRequest.partition_key == key.partition_key,
        DeferredRequest.requested_page == key.page,
    )
    return s.scalars(q.with_for_update() if lock else q).first()


def of_node(s: Session, run_id: str, node: Node, partition_key: str) -> list[DeferredRequest]:
    return list(
        s.scalars(
            select(DeferredRequest)
            .where(
                DeferredRequest.run_id == run_id,
                DeferredRequest.category_source_id == node.category_source_id,
                DeferredRequest.taxonomy_id == node.taxonomy_id,
                DeferredRequest.partition_key == partition_key,
            )
            .order_by(DeferredRequest.requested_page)
        )
    )


# -- what is asked, and what an answer states --------------------------------------------------------------


def requested(node: Node, page: int, url: str, store: StoreConfig) -> dict[str, Any]:
    """The request, exactly: asked again it is this, unchanged."""
    return {
        "url": url,
        "page": page,
        "offset": (page - 1) * pagination.PAGE_SIZE,
        "listing": pagination.listing_id(node.taxonomy_id),
        "reading": node.taxonomy_id,
        "filter": pagination.node_filter(node.partition_filter) or {},
        "store_id": store.location_id,
        "fulfillment": store.modality.value,
    }


def returned(facts: PageFacts | None, subdivisions: Sequence[Mapping[str, Any]] | None = None) -> Any:
    """What the answer states about itself (its page state), or why that is not available."""
    if facts is None:
        return unavailable("no page was brought")
    if facts.returned_page is None and facts.total is None and not facts.organic:
        return unavailable("the page carries no readable search state")
    page = facts.returned_page
    out: dict[str, Any] = {
        "page": page if page is not None else unavailable("the page states no page number"),
        "offset": (page - 1) * pagination.PAGE_SIZE if page is not None else unavailable("no page number"),
        "loaded_pages": list(facts.loaded_pages),
        "listing": facts.taxonomy_id or unavailable("the page states no listing"),
        "store_id": facts.location_id or unavailable("the page's search states no store"),
        "fulfillment": facts.modality or unavailable("the page's search states no fulfillment"),
        "filters": dict(facts.filters)
        if facts.filters is not None
        else unavailable("the page states no search request"),
        "search_id": facts.search_id or unavailable("the page states no search ID"),
        "total": facts.total if facts.total is not None else unavailable("the page states no result count"),
        "available": facts.available
        if facts.available is not None
        else unavailable("the page states no window (availableCount)"),
        "identities": list(facts.organic),
        "sponsored": list(facts.sponsored),
        "cards": facts.cards,
    }
    if subdivisions is not None:
        out["subdivisions"] = [
            {"id": x.get("id"), "name": x.get("name"), "count": x.get("count"), "filter": x.get("filter", "")}
            for x in subdivisions
        ]
    return out


def answer_entry(
    *,
    ordinal: int,
    asked: Mapping[str, Any],
    facts: PageFacts | None,
    judgement: Judgement | None,
    verdict: str,
    detail: str,
    store_check: str,
    unique_before: int,
    new: int,
    counted: bool,
    observed_at: datetime | None,
    response_sha256: str | None,
    page_fetch_id: str | None,
    listing_page_id: str | None,
    listing_page_attempt: int | None,
    provider_request_id: str | None,
    subdivisions: Sequence[Mapping[str, Any]] | None = None,
    overlap: int | None = None,
    outcome: str = "",
) -> dict[str, Any]:
    """One answer's record. ``new`` and ``overlap`` are counted on identities against the listing's
    completed pages; ``unique_after`` moves only when the answer counts."""
    if overlap is None:
        overlap = len(judgement.duplicates) if judgement is not None else 0
    return {
        "ordinal": ordinal,
        "role": FIRST_ANSWER if ordinal == 0 else REASK,
        "requested": dict(asked),
        "answered": facts is not None,
        "observed_at": iso(observed_at) if observed_at is not None else unavailable("no answer was recorded"),
        "returned": returned(facts, subdivisions),
        "capture": {
            "sha256": response_sha256 or unavailable("no page was stored for this request"),
            "page_fetch_id": page_fetch_id or unavailable("the request left no stored page"),
            "listing_page_id": listing_page_id or unavailable("no listing page row"),
            "listing_page_attempt": listing_page_attempt
            if listing_page_attempt is not None
            else unavailable("no listing page row"),
        },
        "provider_request_id": provider_request_id or unavailable("the answer names no request ID"),
        "store_check": store_check,
        "verdict": verdict,
        "detail": detail,
        "unique_before": unique_before,
        "new": new,
        "overlap": overlap,
        "unique_after": unique_before + (new if counted else 0),
        "counted": counted,
        "outcome": outcome,
    }


def facts_of(row: ListingPage) -> PageFacts:
    """What a stored page row says its answer stated (the row keeps it all but the card count)."""
    binding = dict(row.binding or {})
    stated = binding.get("stated")
    return PageFacts(
        requested_page=row.requested_page,
        returned_page=row.returned_page,
        loaded_pages=tuple(row.loaded_pages or ()),
        taxonomy_id=row.returned_taxonomy_id,
        location_id=row.location_id,
        modality=row.modality,
        total=row.total,
        available=row.available,
        organic=tuple(row.identities or ()),
        sponsored=tuple(row.sponsored or ()),
        cards=len(row.identities or ()) + len(row.sponsored or ()),
        filters=dict(stated) if isinstance(stated, Mapping) and binding else None,
        search_id=binding.get("search_id"),
        latest_search_id=binding.get("latest_search_id"),
        loaded=binding.get("loaded"),
        loading=binding.get("loading"),
        has_error=binding.get("has_error"),
    )


# -- the durable record --------------------------------------------------------------------------------------


def set_aside(
    s: Session,
    *,
    key: Key,
    node: Node,
    url: str,
    kind: str,
    store: StoreConfig,
    policy: Policy,
    now: datetime,
    original_verdict: str,
    original_reason: str,
    original_listing_page_id: str | None,
    first: Mapping[str, Any],
) -> DeferredRequest:
    """The request's record, created with its first answer. The caller commits (in the transaction of the
    answer's own row, so neither exists without the other)."""
    not_before = now + timedelta(seconds=policy.min_wait_s)
    row = DeferredRequest(
        run_id=key.run_id,
        category_source_id=key.category_source_id,
        csv_row_index=node.row_index,
        taxonomy_id=key.taxonomy_id,
        partition_key=key.partition_key,
        requested_page=key.page,
        kind=kind,
        url=url[:4000],
        requested_filter=pagination.node_filter(node.partition_filter) or {},
        store_context={
            "store_key": store.key,
            "store_id": store.location_id,
            "fulfillment": store.modality.value,
        },
        original_listing_page_id=original_listing_page_id,
        original_verdict=original_verdict,
        original_reason=original_reason[:2000],
        max_reasks=policy.max_reasks,
        min_wait_s=policy.min_wait_s,
        reasks_dispatched=0,
        not_before=not_before,
        state=WAITING,
        outcome="",
        attempts=[{**first, "outcome": f"set aside; asked again not before {iso(not_before)}"}],
    )
    s.add(row)
    s.flush()
    return row


def close_unanswered(row: DeferredRequest, now: datetime) -> bool:
    """A re-ask that was sent and whose answer was never recorded (the worker stopped while it was out):
    it stays counted, its evidence is marked unavailable, and the wait starts again from when it was sent.
    True when something was closed."""
    changed = False
    attempts = [dict(a) for a in row.attempts or []]
    for a in attempts:
        if a.get("role") == REASK and a.get("answered") is None:
            a.update(
                {
                    "answered": False,
                    "observed_at": unavailable("no answer was recorded"),
                    "returned": unavailable("the worker stopped while the request was out"),
                    "capture": {
                        "sha256": unavailable("no page was stored for this request"),
                        "page_fetch_id": unavailable("the request left no stored page"),
                        "listing_page_id": unavailable("no listing page row"),
                        "listing_page_attempt": unavailable("no listing page row"),
                    },
                    "provider_request_id": unavailable("no answer was recorded"),
                    "store_check": "N/A",
                    "verdict": "unanswered",
                    "detail": "sent; the worker stopped before an answer was processed (its reservation is "
                    "kept as possibly charged)",
                    "new": 0,
                    "overlap": 0,
                    "counted": False,
                    "outcome": "counted among the re-asks; nothing was learnt from it",
                    "closed_at": iso(now),
                }
            )
            changed = True
    if changed:
        row.attempts = attempts
        if row.state == WAITING and row.reasks_dispatched >= row.max_reasks:
            _exhaust(row, now)
    return changed


def gate(row: DeferredRequest, now: datetime) -> str:
    """``ask`` (a re-ask may be sent now), ``wait`` (not before :attr:`not_before`), or the record's final
    state (``recovered``, ``exhausted``): nothing more is sent for it."""
    if row.state != WAITING:
        return str(row.state)
    if row.reasks_dispatched >= row.max_reasks:
        return EXHAUSTED
    return "wait" if now < row.not_before else "ask"


def reserve(s: Session, row_id: str, *, asked: Mapping[str, Any], now: datetime) -> int:
    """Count one re-ask before it is sent (the caller commits before sending). Raises when the ceiling or
    the wait would be broken: nothing is then sent."""
    row = s.get(DeferredRequest, row_id, with_for_update=True)
    if row is None:
        raise RuntimeError(f"deferred request {row_id} is gone")
    decision = gate(row, now)
    if decision != "ask":
        raise RuntimeError(
            f"deferred request {row_id}: a re-ask is not due ({decision}; {row.reasks_dispatched} of "
            f"{row.max_reasks} sent, not before {iso(row.not_before)})"
        )
    if dict(asked) != dict((row.attempts or [{}])[0].get("requested") or {}):
        raise RuntimeError(f"deferred request {row_id}: the re-ask is not the request that was set aside")
    row.reasks_dispatched += 1
    ordinal = int(row.reasks_dispatched)
    # A worker killed from here on leaves this entry unanswered: the next one waits from this moment.
    row.not_before = now + timedelta(seconds=row.min_wait_s)
    row.attempts = [
        *(row.attempts or []),
        {
            "ordinal": ordinal,
            "role": REASK,
            "requested": dict(asked),
            "dispatched_at": iso(now),
            "answered": None,
            "outcome": "sent; no answer recorded yet",
        },
    ]
    s.flush()
    return ordinal


def pending(s: Session, row_id: str, ordinal: int) -> bool:
    """True while re-ask ``ordinal`` is counted as sent and nothing is recorded of its answer."""
    row = s.get(DeferredRequest, row_id)
    return row is not None and any(
        a.get("role") == REASK and a.get("ordinal") == ordinal and a.get("answered") is None
        for a in row.attempts or []
    )


def release(s: Session, row_id: str, ordinal: int, why: str, now: datetime) -> None:
    """The re-ask was not sent after all (the spending ceiling or the account gate refused it before
    anything left): it is not counted, and the record says so."""
    row = s.get(DeferredRequest, row_id, with_for_update=True)
    if row is None:
        return
    attempts = [dict(a) for a in row.attempts or []]
    for a in attempts:
        if a.get("role") == REASK and a.get("ordinal") == ordinal and a.get("answered") is None:
            a.update(
                {
                    "role": NOT_SENT,
                    "ordinal": None,
                    "answered": False,
                    "outcome": f"not sent, not counted: {why}"[:600],
                    "closed_at": iso(now),
                }
            )
            row.reasks_dispatched = max(0, int(row.reasks_dispatched) - 1)
            # Nothing was asked: the wait since the previous answer still stands.
            row.not_before = now
            break
    row.attempts = attempts
    s.flush()


def _exhaust(row: DeferredRequest, now: datetime) -> None:
    row.state, row.resolved_at = EXHAUSTED, now
    row.outcome = final_reason(row)


def settle(
    s: Session,
    row_id: str,
    ordinal: int,
    entry: Mapping[str, Any],
    *,
    recovered: bool,
    now: datetime,
    outcome: str = "",
) -> DeferredRequest:
    """A re-ask's answer (or its failure): kept, and the record moved to ``recovered``, back to waiting
    (another re-ask is left), or ``exhausted``. The caller commits."""
    row = s.get(DeferredRequest, row_id, with_for_update=True)
    if row is None:
        raise RuntimeError(f"deferred request {row_id} is gone")
    attempts = [dict(a) for a in row.attempts or []]
    index = next(
        (i for i, a in enumerate(attempts) if a.get("role") == REASK and a.get("ordinal") == ordinal), None
    )
    merged = dict(entry)
    if index is None:
        attempts.append(merged)
        index = len(attempts) - 1
    else:
        merged = {**attempts[index], **merged}  # the time it was sent stays
        attempts[index] = merged
    row.attempts = attempts
    if recovered:
        row.state, row.resolved_at = RECOVERED, now
        row.outcome = outcome or f"answered properly on re-ask {ordinal}"
    elif row.reasks_dispatched >= row.max_reasks:
        _exhaust(row, now)
    else:
        row.not_before = now + timedelta(seconds=row.min_wait_s)
        attempts[index] = {**merged, "outcome": f"not counted; asked again not before {iso(row.not_before)}"}
        row.attempts = list(attempts)
    s.flush()
    return row


def final_reason(row: DeferredRequest) -> str:
    """Why the request ends unanswered: the reason it had before any re-ask, word for word, then what each
    re-ask brought. Never a statement that the listing was read to its end."""
    asks = [a for a in row.attempts or [] if a.get("role") == REASK]
    told = "; ".join(
        f"re-ask {a.get('ordinal')}: {a.get('verdict', 'unanswered')}"
        + (f" ({a['detail']})" if a.get("detail") else "")
        for a in asks
    )
    return (
        f"{row.original_reason}; asked again {len(asks)} time(s), each at least {row.min_wait_s} s after "
        f"the last answer or attempt: {told or 'none was sent'}; {NOT_EXHAUSTED}"
    )[:1900]


def recovered_children(s: Session, row: DeferredRequest) -> list[dict[str, Any]]:
    """The subdivisions the answer that recovered a ``missing_facets`` request named (its own row keeps
    them, so a resume plans the same readings without asking again)."""
    for a in reversed(row.attempts or []):
        ref = (a.get("capture") or {}).get("listing_page_id")
        if a.get("role") == REASK and a.get("counted") is False and isinstance(ref, str) and len(ref) == 26:
            page = s.get(ListingPage, ref)
            if page is not None and page.children:
                return [dict(c) for c in page.children]
    return []


# -- reports -------------------------------------------------------------------------------------------------


def summary(row: DeferredRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "csv_row": row.csv_row_index,
        "listing": pagination.listing_id(row.taxonomy_id),
        "reading": row.taxonomy_id,
        "partition_key": row.partition_key,
        "requested_page": row.requested_page,
        "kind": row.kind,
        "url": row.url,
        "requested_filter": row.requested_filter,
        "store_context": row.store_context,
        "original_listing_page_id": row.original_listing_page_id,
        "original_verdict": row.original_verdict,
        "original_reason": row.original_reason,
        "max_reasks": row.max_reasks,
        "min_wait_s": row.min_wait_s,
        "reasks_dispatched": row.reasks_dispatched,
        "not_before": iso(row.not_before),
        "state": row.state,
        "outcome": row.outcome,
        "resolved_at": iso(row.resolved_at) if row.resolved_at is not None else None,
        "attempts": list(row.attempts or []),
    }


def export(s: Session, run_id: str) -> list[dict[str, Any]]:
    """Every request the run set aside, in listing order. A record still ``waiting`` belongs to a run that
    ended (or is paused) before its next re-ask: the request was not answered properly."""
    rows = s.scalars(
        select(DeferredRequest)
        .where(DeferredRequest.run_id == run_id)
        .order_by(DeferredRequest.csv_row_index, DeferredRequest.taxonomy_id, DeferredRequest.requested_page)
    )
    return [summary(r) for r in rows]
