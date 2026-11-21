"""Each listing route's verdict from the products actually accounted for (release 1.10.0rc7).

Until 1.10.0rc6 a listing was DONE when its pages had been read to the last one and the identities those pages
listed reached the source's total: the coverage file took the larger of the pages' identities and the cursor's
own count, and G3 the cursor's count, so the two could disagree and neither asked whether a record existed. In
the full run R7 (2026-11-17) two counted pages kept no product (OR-24): Dog Food 27017 page 7 (24 products)
and Cat Treats 27022 page 2 (20); the coverage file said DONE with no gap, G3 said 0.893 and 0.615.

Here a listing's expected identities are the union of the UPCs its counted pages list as the listing's own
results (sponsored placements kept apart), and each of them must be accounted for by this run: a record of the
run (fresh: valid, not valid, or excluded with its reasons) and an organic placement under the listing on one
of those same pages. A product recorded under another listing counts here only through such a placement. What
is left is ``missing``; a placement under the listing for a product none of its counted pages lists is
``unexpected``. A listing is DONE only when its pages were read to their end, nothing is missing or
unexpected, and the products accounted for reach the highest total the source reported; EMPTY only with a page
of the store stating 0 results; a listing read through subdivisions only when every one of them is DONE or
EMPTY and the union of what they account for reaches the listing's total (never a sum of counts, which
overlap). The same functions serve the collector (``reconciliation``), the gates, the export, the publication
and the offline replay of a stored run (``evidence/tools/replay_routes.py``), so every consumer reports one
verdict.

A final page, equal totals, an HTTP 200 answer or a high coverage share never discharges a missing
identity."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Statuses of a record of the run that account for a product shown on a counted page.
FRESH = ("valid", "eligible_unpriced", "price_conflict", "exported_not_valid")
EXCLUDING = ("excluded", "quarantined")
CARRIED = "historical"
FINISHED = ("DONE", "EMPTY")
MISSING_NO_RECORD = "no record of this run"
MISSING_NO_PLACEMENT = "a record of this run, with no placement under this listing on its counted pages"
MISSING_CARRIED = "listed on a counted page of this run, while its record is carried from an earlier run"
MISSING_UNEXPLAINED = "a record of this run excluded without a stated reason"


@dataclass(frozen=True)
class PageEvidence:
    """One counted page of a listing: what the response listed and where it is kept."""

    page: int
    identities: tuple[str, ...]
    sponsored: tuple[str, ...] = ()
    fetch_id: str | None = None
    sha256: str | None = None
    observed_at: str | None = None
    total: int | None = None
    location_id: str | None = None
    modality: str | None = None
    url: str = ""
    attempt: int = 1
    verdict: str = ""
    # The page was shown for the run's store and fulfillment (its store check passed and it names the
    # store's location and modality); None when the evidence does not say.
    store_bound: bool | None = None


@dataclass(frozen=True)
class RouteEvidence:
    """One listing of the run's plan (a listing, a subdivision or a filtered reading of one)."""

    key: str  # unique in the run's plan: the same listing can be planned under two CSV rows
    cursor_status: str
    parent: str = ""  # the parent's key
    kind: str = ""
    listing: str = ""  # the listing's own ID (the key when not given)
    reason: str = ""
    total: int | None = None
    totals_seen: tuple[int, ...] = ()
    pages: tuple[PageEvidence, ...] = ()
    # Organic placements of this run under the listing: (UPC, page fetch); the fetch may be unknown. A
    # placement keeps the first fetch that showed the card (an earlier attempt of the same page, cut short by
    # the product limit, can be it): any placement under the listing links the record to it, while only the
    # listing's counted pages say which products it must account for.
    placements: frozenset[tuple[str, str | None]] = frozenset()
    # Products placed under the listing as sponsored (``paid``): they link a record to the listing as well.
    paid: frozenset[str] = frozenset()
    # Every fetch of the listing's own page rows (any attempt or state): a placement made from another
    # listing's page (a product the run put under its most specific listing) is never "unexpected" here.
    fetches: frozenset[str] = frozenset()
    # A page of the store stating that the listing has 0 results (the only proof of an empty listing).
    zero_result: bool = False
    # Read through browser steps (Load More), which keep no page row, or through a search, whose page lists
    # no identity of the listing: the members the reading kept, in the listing's cursor, are the expected
    # list (neither is ever DONE on a page's count alone).
    without_page_rows: bool = False
    stepped: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecordFact:
    status: str
    reasons: tuple[str, ...] = ()
    node: str = ""  # the listing the record was observed under (a cross-listed product: another one)


@dataclass
class RouteVerdict:
    key: str
    status: str
    reason: str
    cursor_status: str
    total: int | None
    expected: tuple[str, ...] = ()
    accounted: frozenset[str] = frozenset()
    fresh: tuple[str, ...] = ()
    fresh_valid: int = 0
    cross_listed: int = 0
    excluded: dict[str, tuple[str, ...]] = field(default_factory=dict)
    missing: dict[str, str] = field(default_factory=dict)
    missing_by_page: dict[int, tuple[str, ...]] = field(default_factory=dict)
    unexpected: tuple[str, ...] = ()
    from_other_listings: int = 0
    sponsored: tuple[str, ...] = ()
    duplicates: int = 0
    pages_counted: int = 0
    children: tuple[str, ...] = ()
    union_expected: frozenset[str] = frozenset()
    union_accounted: frozenset[str] = frozenset()
    listing: str = ""

    @property
    def finished(self) -> bool:
        return self.status in FINISHED

    def as_dict(self, *, lists: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "listing_id": self.listing or self.key,
            "status": self.status,
            "reason": self.reason,
            "cursor_status": self.cursor_status,
            "reported_total": self.total,
            "pages_counted": self.pages_counted,
            "expected_identities": len(self.union_expected or set(self.expected)),
            "accounted_identities": len(self.union_accounted or self.accounted),
            "fresh_records": len(self.fresh),
            "fresh_valid": self.fresh_valid,
            "cross_listed": self.cross_listed,
            "supported_exclusions": len(self.excluded),
            "missing_identities": len(self.missing),
            "unexpected_identities": len(self.unexpected),
            "placed_from_other_listings": self.from_other_listings,
            "sponsored_placements": len(self.sponsored),
            "duplicates": self.duplicates,
            "children": list(self.children),
        }
        if lists:
            out.update(
                {
                    "missing": dict(sorted(self.missing.items())),
                    "missing_by_page": {str(k): list(v) for k, v in sorted(self.missing_by_page.items())},
                    "unexpected": list(self.unexpected),
                    "excluded": {k: list(v) for k, v in sorted(self.excluded.items())},
                }
            )
        return out


def _ordered_union(pages: Iterable[PageEvidence]) -> tuple[tuple[str, ...], int]:
    seen: dict[str, None] = {}
    repeats = 0
    for p in pages:
        for u in p.identities:
            if u in seen:
                repeats += 1
            else:
                seen[u] = None
    return tuple(seen), repeats


def _short(upcs: Sequence[str], n: int = 6) -> str:
    shown = ", ".join(upcs[:n])
    return shown + (f" and {len(upcs) - n} more" if len(upcs) > n else "")


def audit_one(route: RouteEvidence, records: Mapping[str, RecordFact]) -> RouteVerdict:
    """The verdict of one listing on its own pages (its subdivisions are joined by :func:`audit`)."""
    if route.without_page_rows:
        expected, repeats = tuple(dict.fromkeys(route.stepped)), len(route.stepped) - len(set(route.stepped))
    else:
        expected, repeats = _ordered_union(route.pages)
    own_fetches = set(route.fetches) | {p.fetch_id for p in route.pages if p.fetch_id}
    placed = {u for u, _ in route.placements} | set(route.paid)
    # Placements made while reading this listing (or whose fetch is unknown).
    local = {u for u, f in route.placements if f is None or f in own_fetches}
    accounted: set[str] = set()
    fresh: list[str] = []
    excluded: dict[str, tuple[str, ...]] = {}
    missing: dict[str, str] = {}
    for u in expected:
        rec = records.get(u)
        if rec is None:
            missing[u] = MISSING_NO_RECORD
        elif u not in placed:
            missing[u] = MISSING_NO_PLACEMENT
        elif rec.status == CARRIED:
            missing[u] = MISSING_CARRIED
        elif rec.status in EXCLUDING:
            if not rec.reasons:
                missing[u] = MISSING_UNEXPLAINED
                continue
            excluded[u] = rec.reasons
            accounted.add(u)
        elif rec.status in FRESH:
            fresh.append(u)
            accounted.add(u)
        else:
            missing[u] = f"a record of this run with the status {rec.status!r}"
    unexpected = tuple(sorted(local - set(expected)))
    by_page: dict[int, tuple[str, ...]] = {}
    for p in route.pages:
        gone = tuple(u for u in p.identities if u in missing)
        if gone:
            by_page[p.page] = gone
    sponsored = tuple(dict.fromkeys(u for p in route.pages for u in p.sponsored))
    v = RouteVerdict(
        key=route.key,
        status=route.cursor_status,
        reason=route.reason,
        cursor_status=route.cursor_status,
        total=route.total,
        expected=expected,
        accounted=frozenset(accounted),
        fresh=tuple(fresh),
        fresh_valid=sum(1 for u in fresh if records[u].status == "valid"),
        cross_listed=sum(
            1 for u in accounted if records[u].node and records[u].node != (route.listing or route.key)
        ),
        excluded=excluded,
        missing=missing,
        missing_by_page=by_page,
        unexpected=unexpected,
        from_other_listings=len(({u for u, _ in route.placements} - local) - set(expected)),
        sponsored=sponsored,
        duplicates=repeats,
        pages_counted=len(route.pages),
        listing=route.listing or route.key,
    )
    if route.cursor_status == "DONE":
        v.status, v.reason = _done_or_not(v, route)
    elif route.cursor_status == "EMPTY":
        if not route.zero_result:
            v.status = "INCOMPLETE"
            v.reason = "recorded as empty without a page of the store stating 0 results"
        elif expected or local:  # a stated zero contradicted by the listing's own pages
            v.status = "INCOMPLETE"
            v.reason = (
                f"recorded as empty while {len(set(expected) | local)} product(s) were listed or placed"
            )
    return v


def _gap_text(v: RouteVerdict) -> str:
    parts = []
    if v.missing:
        kinds: dict[str, int] = {}
        for why in v.missing.values():
            kinds[why] = kinds.get(why, 0) + 1
        pages = "; ".join(
            f"page {p}: {len(u)} ({_short(list(u), 3)})" for p, u in sorted(v.missing_by_page.items())
        )
        parts.append(
            f"{len(v.missing)} of the {len(v.expected)} products its counted pages list are not "
            f"accounted for by this run ({'; '.join(f'{n}: {k}' for k, n in sorted(kinds.items()))})"
            + (f" [{pages}]" if pages else "")
        )
    if v.unexpected:
        parts.append(
            f"{len(v.unexpected)} placement(s) under the listing for products none of its counted "
            f"pages lists ({_short(list(v.unexpected), 3)})"
        )
    return "; ".join(parts)


def _done_or_not(v: RouteVerdict, route: RouteEvidence) -> tuple[str, str]:
    unbound = [p.page for p in route.pages if p.store_bound is False]
    if unbound:
        return (
            "INCOMPLETE",
            "read to its last page, but page(s) "
            + ", ".join(str(n) for n in unbound)
            + " were not shown for the run's store and fulfillment",
        )
    gap = _gap_text(v)
    if gap:
        return "INCOMPLETE", f"read to its last page, but {gap}"
    total = route.total
    if not isinstance(total, int):
        return "INCOMPLETE", "read to its last page, but no page states the listing's total"
    if len(v.accounted) < total:
        changed = (
            f" (the source's total changed while reading: {', '.join(str(n) for n in route.totals_seen)})"
            if len(route.totals_seen) > 1
            else ""
        )
        return (
            "INCOMPLETE",
            f"read to its last page, but {len(v.accounted)} distinct products are accounted for of the "
            f"{total} the source reported{changed}",
        )
    return (
        "DONE",
        f"{len(v.accounted)} distinct products of {total} reported, on {v.pages_counted} page(s), each "
        "accounted for",
    )


def audit(routes: Sequence[RouteEvidence], records: Mapping[str, RecordFact]) -> dict[str, RouteVerdict]:
    """Every listing's verdict; a listing read through subdivisions joined with them (set union)."""
    own = {r.key: audit_one(r, records) for r in routes}
    by_key = {r.key: r for r in routes}
    kids: dict[str, list[str]] = {}
    for r in routes:
        if r.parent:
            kids.setdefault(r.parent, []).append(r.key)

    done: dict[str, RouteVerdict] = {}

    def resolve(key: str, depth: int = 0) -> RouteVerdict:
        if key in done:
            return done[key]
        v = own[key]
        route = by_key[key]
        children = [k for k in kids.get(key, []) if k != key]
        if depth > 20:
            raise ValueError(f"subdivisions of {key} nest too deep")
        sub = [resolve(k, depth + 1) for k in children]
        union_e = set(v.expected)
        union_a = set(v.accounted)
        for c in sub:
            union_e |= c.union_expected or set(c.expected)
            union_a |= c.union_accounted or set(c.accounted)
        v.children = tuple(children)
        v.union_expected = frozenset(union_e)
        v.union_accounted = frozenset(union_a)
        if route.cursor_status == "PARTITIONED":
            not_finished = [c for c in sub if not c.finished]
            own_gap = _gap_text(v)
            total = route.total
            if not sub:
                v.status, v.reason = "INCOMPLETE", "read through subdivisions, but none of them was planned"
            elif not_finished:
                v.status = "INCOMPLETE"
                v.reason = f"{len(not_finished)} of its {len(sub)} subdivisions not complete: " + "; ".join(
                    f"{c.listing or c.key} {c.status}" for c in not_finished[:8]
                )
            elif own_gap:
                v.status, v.reason = "INCOMPLETE", f"its own pages: {own_gap}"
            elif not isinstance(total, int):
                v.status, v.reason = "INCOMPLETE", "read through subdivisions, but no page states its total"
            elif len(union_a) < total:
                v.status = "INCOMPLETE"
                v.reason = (
                    f"its {len(sub)} subdivisions account for {len(union_a)} distinct products (their union) "
                    f"of the {total} the source reported for the listing"
                )
            else:
                v.status = "DONE"
                v.reason = (
                    f"{len(union_a)} distinct products of {total} reported, read through {len(sub)} "
                    "subdivisions named by the page, each accounted for (their union)"
                )
        done[key] = v
        return v

    for key in own:
        resolve(key)
    return done


def summary(verdicts: Mapping[str, RouteVerdict]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for v in verdicts.values():
        by_status[v.status] = by_status.get(v.status, 0) + 1
    gaps = {k: len(v.missing) for k, v in verdicts.items() if v.missing}
    unexpected = {k: len(v.unexpected) for k, v in verdicts.items() if v.unexpected}
    downgraded = sorted(k for k, v in verdicts.items() if v.cursor_status in FINISHED and not v.finished)
    return {
        "listings": len(verdicts),
        "by_status": dict(sorted(by_status.items())),
        "missing_identities": sum(gaps.values()),
        "listings_with_missing": dict(sorted(gaps.items())),
        "listings_with_unexpected": dict(sorted(unexpected.items())),
        "read_to_end_but_not_accounted": downgraded,
    }
