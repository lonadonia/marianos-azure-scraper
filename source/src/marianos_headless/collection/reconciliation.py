"""What a run read of the client's category list, as data (release 1.8.0).

One line per listing of the run's plan, and one per CSV row: the source's reported totals, the pages attempted
and completed, the distinct products, duplicates, exclusions, variants, unavailable products, the gap and why
the listing ended as it did. Nothing here is a threshold: a listing is complete only when its pages' distinct
products reach the highest total the source reported, a listing read through subdivisions only when the
distinct products of all of them do (never a sum of counts, which overlap), and a CSV row only when every
listing of it is.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from marianos_headless.collection import pagination, reask, route_audit
from marianos_headless.core.findings import RecordFlag
from marianos_headless.db.models import (
    CategorySource,
    ListingPage,
    MembershipRow,
    NodeCoverage,
    ProductObservation,
    RecordRow,
    Run,
    Store,
    Task,
)

FINISHED_NODE = ("DONE", "EMPTY", "INCOMPLETE", "SKIPPED", "PARTITIONED")
# The record statuses of an export (publishing/supporting_log.EXPORTED_STATUSES): fresh valid, fresh but not
# valid
# (unpriced, conflicting, incomplete identity) and carried forward. Any other status is excluded.
FRESH_VALID = ("valid",)
FRESH_NOT_VALID = ("eligible_unpriced", "price_conflict", "exported_not_valid")
CARRIED = ("historical",)
EXPORTED = (*FRESH_VALID, *FRESH_NOT_VALID, *CARRIED)


def identity_sets(s: Session, run_id: str) -> dict[str, Any]:
    """Every product count of the export as a set of identities (UPCs), and the relations that must hold
    between them: a product is fresh valid, fresh but not valid, carried forward or excluded, never two of
    a product is fresh valid, fresh but not valid, carried forward or excluded, never two of these, and the
    retained dataset is exactly the first three. Computed from the run's own records, never copied from an
    earlier report."""
    statuses: dict[str, list[str]] = defaultdict(list)
    for upc, status in s.execute(
        select(RecordRow.upc, RecordRow.status).where(RecordRow.run_id == run_id)
    ).all():
        statuses[str(upc)].append(str(status))
    sets = {
        "fresh_valid": {u for u, v in statuses.items() if set(v) & set(FRESH_VALID)},
        "fresh_not_valid": {u for u, v in statuses.items() if set(v) & set(FRESH_NOT_VALID)},
        "carried_forward": {u for u, v in statuses.items() if set(v) & set(CARRIED)},
        "excluded": {u for u, v in statuses.items() if not set(v) & set(EXPORTED)},
    }
    exported = [u for u, v in statuses.items() for st in v if st in EXPORTED]
    retained = set(exported)
    names = list(sets)
    overlaps = {f"{a} & {b}": len(sets[a] & sets[b]) for i, a in enumerate(names) for b in names[i + 1 :]}
    union = sets["fresh_valid"] | sets["fresh_not_valid"] | sets["carried_forward"]
    relations = {
        "no identity is in two classes": not any(overlaps.values()),
        "retained = fresh valid + fresh not valid + carried forward": retained == union
        and len(retained) == sum(len(sets[k]) for k in ("fresh_valid", "fresh_not_valid", "carried_forward")),
        "no exported identity twice": len(exported) == len(retained),
    }
    return {
        "record_rows": sum(len(v) for v in statuses.values()),
        **{k: len(v) for k, v in sets.items()},
        "excluded_rows": sum(1 for v in statuses.values() for st in v if st not in EXPORTED),
        "exported_rows": len(exported),
        "retained_unique": len(retained),
        "duplicates": len(exported) - len(retained),
        "overlaps": overlaps,
        "relations": relations,
        "holds": all(relations.values()),
    }


LISTING_FIELDS = (
    "csv_row",
    "category",
    "sub_category",
    "listing_id",
    "parent_listing",
    "listing_kind",
    "source_url",
    "location_id",
    "fulfillment",
    "route",
    "reported_total",
    "totals_seen",
    "source_window",
    "pages_reachable",
    "pages_attempted",
    "pages_completed",
    "responses_not_counted",
    "unique_identities",
    "sponsored_placements",
    "duplicates",
    "approx_weight_exclusions",
    "other_exclusions",
    "price_conflicts",
    "variant_groups",
    "unavailable",
    "unresolved_gap",
    "status",
    "completion_reason",
    "partition_identity",
    "pages_filter_refused",
    # Release 1.10.0rc7 (route_audit): the products the counted pages list, those the run accounts for (a
    # record placed under the listing), those it does not, placements no counted page lists, and the
    # status the listing's own reading reached before the products were accounted for.
    "expected_identities",
    "accounted_identities",
    "missing_identities",
    "unexpected_identities",
    "cursor_status",
)
ROW_FIELDS = (
    "csv_row",
    "category",
    "source_url",
    "listings_planned",
    "listings_complete",
    "listings_incomplete",
    "listings_not_read",
    "pages_completed",
    "unique_identities",
    "approx_weight_exclusions",
    "unresolved_gap",
    "status",
    "completion_reason",
)


def _pkey(node: dict[str, Any]) -> str:
    desc = pagination.node_filter(node.get("partition_filter") or "")
    return pagination.partition_digest(desc) if desc else ""


def route_evidence(s: Session, run_id: str) -> tuple[list[Task], list[route_audit.RouteEvidence]]:
    """What the run holds about each listing of its plan, as :mod:`route_audit` reads it: the task's own
    outcome, its counted pages, the organic placements of the run under it and whether a page of the store
    stated 0 results (release 1.10.0rc7)."""
    tasks = list(
        s.scalars(
            select(Task).where(Task.run_id == run_id, Task.kind == "listing_node").order_by(Task.idem_key)
        )
    )
    run = s.get(Run, run_id)
    store = s.get(Store, run.store_id) if run is not None else None
    rows: dict[tuple[str, str, str], list[ListingPage]] = defaultdict(list)
    for p in s.scalars(select(ListingPage).where(ListingPage.run_id == run_id)):
        rows[(p.category_source_id, p.taxonomy_id, p.partition_key or "")].append(p)
    placed: dict[str, set[tuple[str, str | None]]] = defaultdict(set)
    paid: dict[str, set[str]] = defaultdict(set)
    for upc, source, tax, fetch, via in s.execute(
        select(
            MembershipRow.upc,
            MembershipRow.category_source_id,
            MembershipRow.taxonomy_id,
            MembershipRow.page_fetch_id,
            MembershipRow.via,
        ).where(MembershipRow.run_id == run_id, MembershipRow.coupon_id.is_(None))
    ).all():
        if via == "organic":
            placed[route_key(source, tax)].add((str(upc), str(fetch) if fetch else None))
        else:
            paid[route_key(source, tax)].add(str(upc))

    def bound(r: ListingPage) -> bool:
        """The page names the run's store and fulfillment and its store check passed."""
        return (
            r.store_check == "PASS"
            and store is not None
            and r.location_id == store.location_id
            and (r.modality or "").upper() == str(store.modality).upper()
        )

    routes: list[route_audit.RouteEvidence] = []
    for t in tasks:
        cur = t.cursor or {}
        node = cur.get("node") or {}
        source, listing = str(node.get("category_source_id") or ""), str(node.get("taxonomy_id") or "")
        key = route_key(source, listing)
        status = str(cur.get("status") or "")
        if t.state != "succeeded":
            status = "NOT_COLLECTED"
        elif status not in FINISHED_NODE:
            status = "INCOMPLETE"
        mine = sorted(
            rows.get((source, listing, _pkey(node)), []), key=lambda r: (r.requested_page, r.attempt)
        )
        stepped = not mine or all(r.route == "search" for r in mine)
        done = pagination.completed_pages(mine)
        totals = tuple(sorted({r.total for r in mine if r.total is not None}))
        total = totals[-1] if totals else cur.get("total")
        zero = any(r.state == "completed" and r.total == 0 and bound(r) for r in mine)
        routes.append(
            route_audit.RouteEvidence(
                key=key,
                listing=listing,
                cursor_status=status,
                parent=route_key(source, node["parent"]) if node.get("parent") else "",
                kind=str(node.get("kind") or ""),
                reason=str(cur.get("reason") or ""),
                total=total if isinstance(total, int) else None,
                totals_seen=totals,
                pages=tuple(
                    route_audit.PageEvidence(
                        page=r.requested_page,
                        identities=tuple(str(u) for u in (r.identities or [])),
                        sponsored=tuple(str(u) for u in (r.sponsored or [])),
                        fetch_id=r.page_fetch_id,
                        sha256=r.response_sha256,
                        observed_at=r.observed_at.isoformat() if r.observed_at else None,
                        total=r.total,
                        location_id=r.location_id,
                        modality=r.modality,
                        url=r.url,
                        attempt=r.attempt,
                        verdict=r.verdict,
                        store_bound=bound(r),
                    )
                    for r in done
                ),
                placements=frozenset(placed.get(key, set())),
                paid=frozenset(paid.get(key, set())),
                fetches=frozenset(r.page_fetch_id for r in mine if r.page_fetch_id),
                zero_result=zero,
                # Browser steps (Load More) keep no page row, and a search page lists no identity of the
                # listing: the cursor lists the members the reading kept (such a listing is never DONE
                # through a search).
                without_page_rows=stepped,
                stepped=tuple(str(u) for u in (cur.get("seen") or [])) if stepped else (),
            )
        )
    return tasks, routes


def route_key(category_source_id: Any, taxonomy_id: Any) -> str:
    """A listing of the run's plan: the same listing can be planned under two CSV rows (category sources)."""
    return f"{category_source_id or ''}|{taxonomy_id or ''}"


def node_key(node: dict[str, Any]) -> str:
    return route_key(node.get("category_source_id"), node.get("taxonomy_id"))


def record_facts(s: Session, run_id: str) -> dict[str, route_audit.RecordFact]:
    nodes: dict[str, str] = {}
    for upc, prov in s.execute(
        select(ProductObservation.upc, ProductObservation.provenance).where(
            ProductObservation.run_id == run_id
        )
    ).all():
        nodes.setdefault(str(upc), str((prov or {}).get("node") or ""))
    return {
        str(upc): route_audit.RecordFact(str(status), tuple(reasons or ()), nodes.get(str(upc), ""))
        for upc, status, reasons in s.execute(
            select(RecordRow.upc, RecordRow.status, RecordRow.reasons).where(RecordRow.run_id == run_id)
        ).all()
    }


def audited(s: Session, run_id: str) -> tuple[list[Task], dict[str, route_audit.RouteVerdict]]:
    tasks, routes = route_evidence(s, run_id)
    return tasks, route_audit.audit(routes, record_facts(s, run_id))


def node_outcomes(s: Session, run_id: str) -> list[dict[str, Any]]:
    """Each listing task's outcome, from the products the run accounts for (release 1.10.0rc7,
    :mod:`route_audit`): a listing read to its last page is DONE only when every product its counted pages
    list has a record of the run placed under it and they reach the source's total; a partitioned listing
    only when every child listing is finished and the union of what they account for reaches the listing's
    total (never a sum of child counts, which overlap); otherwise INCOMPLETE, with the gap. ``seen`` is the
    number of products accounted for (the coverage the gates measure)."""
    tasks, verdicts = audited(s, run_id)
    out = []
    for t in tasks:
        cur = t.cursor or {}
        node = cur.get("node") or {}
        v = verdicts[node_key(node)]
        entry: dict[str, Any] = {
            "node": node,
            "status": v.status,
            "seen": len(v.union_accounted or v.accounted),
            "total": cur.get("total"),
            "available": cur.get("available"),
            "reason": v.reason if v.status != v.cursor_status else (cur.get("reason") or v.reason or ""),
            "cursor_status": v.cursor_status,
            "audit": v.as_dict(lists=False),
            "verdict": v,
        }
        if v.cursor_status == "PARTITIONED":
            entry["partitioned"] = {
                "children": [verdicts[k].listing for k in v.children if k in verdicts],
                "children_status": {
                    verdicts[k].listing: verdicts[k].status for k in v.children if k in verdicts
                },
                "distinct_products": len(v.union_accounted),
                "gap": max(0, (v.total or 0) - len(v.union_accounted)),
            }
        out.append(entry)
    return out


def sync_node_coverage(s: Session, run_id: str, outcomes: list[dict[str, Any]]) -> int:
    """The per-listing coverage rows written while collecting (the cursor's view) set to the audited verdict,
    so that what later reads them (the backlog order of a scheduled run, why a product was not observed by
    the run) sees what the export reports. Returns how many rows changed."""
    changed = 0
    by_key = {node_key(o["node"] or {}): o for o in outcomes}
    for row in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id)):
        o = by_key.get(route_key(row.category_source_id, row.taxonomy_id))
        if o is None:
            continue
        status, seen, total = o["status"], int(o["seen"]), o["total"]
        if o["cursor_status"] == "PARTITIONED" and status == "DONE":
            status = "PARTITIONED"  # the collector's own word for a listing read through its subdivisions
        ratio = 1.0 if total == 0 else (min(1.0, seen / total) if total else None)
        if (row.status, row.organic_upcs, row.coverage_ratio) != (status, seen, ratio):
            row.status, row.organic_upcs, row.coverage_ratio = status, seen, ratio
            row.partition = {**(row.partition or {}), "audit": o["audit"], "audited_reason": o["reason"]}
            changed += 1
    return changed


def coverage_problems(s: Session, run_id: str) -> list[str]:
    """Why the run's coverage does not support a full publication (empty: it does): a listing of the plan
    not DONE or EMPTY under the audit, or any product a counted page lists with nothing accounting for it."""
    tasks, verdicts = audited(s, run_id)
    if not tasks:
        return ["the run's plan has no listing"]
    out = []
    for _, v in sorted(verdicts.items()):
        if not v.finished:
            out.append(f"{v.listing} {v.status}: {v.reason}"[:300])
        elif v.missing or v.unexpected:
            out.append(f"{v.listing}: {len(v.missing)} missing, {len(v.unexpected)} unexpected")
    return out


def _reason(outcome: dict[str, Any], completed: int, unique: int) -> str:
    status, total = outcome["status"], outcome["total"]
    if status == "DONE":
        if "partitioned" in outcome:
            return (
                f"{outcome['partitioned']['distinct_products']} distinct products of {total} reported, read "
                f"through {len(outcome['partitioned']['children'])} subdivisions named by the page"
            )
        return f"{unique} distinct products of {total} reported, on {completed} page(s)"
    if status == "EMPTY":
        return "the source reports 0 results"
    if status == "NOT_COLLECTED":
        return f"{pagination.GAP}: the listing was not read to an end by this run"
    return outcome["reason"] or pagination.GAP


def reconciliation(s: Session, run_id: str) -> dict[str, Any]:
    run = s.get(Run, run_id)
    if run is None:
        raise ValueError(f"unknown run {run_id}")
    store = s.get(Store, run.store_id)
    pages: dict[str, list[ListingPage]] = defaultdict(list)
    for p in s.scalars(select(ListingPage).where(ListingPage.run_id == run_id)):
        pages[route_key(p.category_source_id, p.taxonomy_id)].append(p)
    records = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id))}
    placed: dict[str, set[str]] = defaultdict(set)
    variant: dict[str, dict[str, str]] = defaultdict(dict)
    unavailable: dict[str, set[str]] = defaultdict(set)
    for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id)):
        prov = o.provenance or {}
        node = str(prov.get("node") or "")
        placed[node].add(o.upc)
        group = ((o.structured or {}).get("product") or {}).get("variant_group")
        if group:
            variant[node][o.upc] = str(group)
        if (prov.get("source_check") or {}).get("stock_level") == "TEMPORARILY_OUT_OF_STOCK":
            unavailable[node].add(o.upc)

    lines: list[dict[str, Any]] = []
    by_row: dict[int, list[dict[str, Any]]] = defaultdict(list)
    outcomes = node_outcomes(s, run_id)
    for outcome in outcomes:
        node = outcome["node"]
        listing = str(node.get("taxonomy_id") or "")
        rows = sorted(pages.get(node_key(node), []), key=lambda r: (r.requested_page, r.attempt))
        done = pagination.completed_pages(rows)
        unique = len({u for r in done for u in (r.identities or [])})
        totals = sorted({r.total for r in rows if r.total is not None})
        total = totals[-1] if totals else outcome["total"]
        available = next(
            (r.available for r in reversed(rows) if r.available is not None), outcome["available"]
        )
        members = placed.get(listing, set())
        recs = [records[u] for u in members if u in records]
        exclusions = Counter(x for r in recs if r.status == "excluded" for x in (r.reasons or []))
        approx = exclusions.pop(RecordFlag.APPROX_WEIGHT.value, 0)
        verdict: route_audit.RouteVerdict = outcome["verdict"]
        # 1.10.0rc7: the products accounted for (a record of the run placed under the listing), never the
        # larger of the pages' identities and the cursor's count (OR-24: Dog Food 27017 and Cat Treats 27022
        # were DONE with no gap while 44 products of their counted pages had no record).
        distinct = len(verdict.union_accounted or verdict.accounted)
        line = {
            "csv_row": node.get("row_index"),
            "category": node.get("category"),
            "sub_category": node.get("partition_name") or node.get("sub_category") or "",
            "listing_id": listing,
            "parent_listing": node.get("parent") or "",
            "listing_kind": node.get("kind") or "",
            "source_url": node.get("url"),
            "location_id": store.location_id if store is not None else None,
            "fulfillment": store.modality if store is not None else None,
            "route": rows[0].route if rows else "",
            "reported_total": total,
            "totals_seen": totals,
            "source_window": available,
            "pages_reachable": pagination.last_page(total, available),
            "pages_attempted": len({r.requested_page for r in rows}),
            "pages_completed": len(done),
            "responses_not_counted": sum(1 for r in rows if r.state != "completed"),
            "unique_identities": distinct,
            "sponsored_placements": len({u for r in done for u in (r.sponsored or [])}),
            "duplicates": sum(r.duplicates for r in rows),
            "approx_weight_exclusions": approx,
            "other_exclusions": sum(exclusions.values()),
            "price_conflicts": sum(1 for r in recs if r.status == "price_conflict"),
            "variant_groups": len(set(variant.get(listing, {}).values())),
            "unavailable": len(unavailable.get(listing, set())),
            "unresolved_gap": max(0, total - distinct) if isinstance(total, int) else None,
            "status": outcome["status"],
            "completion_reason": _reason(outcome, len(done), unique),
            # 1.9.0 (M1): a filtered reading's full identity; (M2) its responses refused for their filters
            "partition_identity": node.get("partition_filter") or "",
            "pages_filter_refused": sum(
                1
                for r in rows
                if r.verdict in (pagination.PageVerdict.WRONG_FILTER, pagination.PageVerdict.UNBOUND)
            ),
            "expected_identities": len(verdict.union_expected or set(verdict.expected)),
            "accounted_identities": distinct,
            "missing_identities": len(verdict.missing),
            "unexpected_identities": len(verdict.unexpected),
            "cursor_status": verdict.cursor_status,
            # JSON only (the CSV keeps the counts): which products, page by page.
            "missing": dict(sorted(verdict.missing.items())),
            "missing_by_page": {str(k): list(v) for k, v in sorted(verdict.missing_by_page.items())},
            "unexpected": list(verdict.unexpected),
            "excluded_identities": {k: list(v) for k, v in sorted(verdict.excluded.items())},
        }
        lines.append(line)
        if not line["parent_listing"]:
            by_row[int(node.get("row_index") or 0)].append(line)

    sources = list(
        s.scalars(select(CategorySource).where(CategorySource.enabled).order_by(CategorySource.csv_row_index))
    )
    rows_out: list[dict[str, Any]] = []
    coupons = (run.counts or {}).get("coupons_route") if run is not None else None
    for src in sources:
        if isinstance(coupons, dict) and coupons.get("mandatory") and src.url == coupons.get("url"):
            # The run's plan names the Coupons row (release 1.10.0rc6, OR-04): the row is its route's verdict.
            rows_out.append(_route_row(src, coupons))
            continue
        planned = by_row.get(src.csv_row_index, [])
        complete = [x for x in planned if x["status"] in ("DONE", "EMPTY")]
        unread = [x for x in planned if x["status"] == "NOT_COLLECTED"]
        gaps = [x["unresolved_gap"] for x in planned]
        row_done = bool(planned) and len(complete) == len(planned)
        rows_out.append(
            {
                "csv_row": src.csv_row_index,
                "category": src.category_name,
                "source_url": src.url,
                "listings_planned": len(planned),
                "listings_complete": len(complete),
                "listings_incomplete": len(planned) - len(complete) - len(unread),
                "listings_not_read": len(unread),
                "pages_completed": sum(x["pages_completed"] for x in planned),
                "unique_identities": sum(x["unique_identities"] for x in planned),
                "approx_weight_exclusions": sum(x["approx_weight_exclusions"] for x in planned),
                "unresolved_gap": sum(g for g in gaps if isinstance(g, int)) if planned else None,
                "status": "COMPLETE" if row_done else ("NOT_ATTEMPTED" if not planned else "INCOMPLETE"),
                "completion_reason": (
                    "every listing of the row reached the source's reported total"
                    if row_done
                    else "not in this run's scope"
                    if not planned
                    else pagination.GAP
                ),
            }
        )
    return {
        "run_id": run_id,
        "store": {
            "key": store.key if store is not None else None,
            "location_id": store.location_id if store is not None else None,
            "fulfillment": store.modality if store is not None else None,
        },
        "csv_rows": len(rows_out),
        "listings_planned": len(lines),
        "complete_rows": sum(1 for r in rows_out if r["status"] == "COMPLETE"),
        "complete_listings": sum(1 for x in lines if x["status"] in ("DONE", "EMPTY")),
        "route_audit": route_audit.summary({node_key(o["node"]): o["verdict"] for o in outcomes}),
        "identities": identity_sets(s, run_id),
        "rows": rows_out,
        "listings": lines,
    }


def _route_row(src: CategorySource, route: dict[str, Any]) -> dict[str, Any]:
    """The Coupons row (release 1.10.0rc6, OR-04): read as a route of the run, its page's own verdict.
    COMPLETE only when its list loaded (with cards, or stated empty); NOT_READ with why otherwise."""
    status = str(route.get("status") or "")
    attempts = route.get("attempts") or []
    asked = f" ({len(attempts)} answer(s))" if attempts else ""
    if status == "READ":
        reason = f"the Coupons page was read for the store{asked}: {route.get('list_detail') or ''}".rstrip(
            ": "
        )
    else:
        reason = f"the Coupons page was not read{asked}: {status}"
    return {
        "csv_row": src.csv_row_index,
        "category": src.category_name,
        "source_url": src.url,
        "listings_planned": 0,
        "listings_complete": 0,
        "listings_incomplete": 0,
        "listings_not_read": 0,
        "pages_completed": 1 if status == "READ" else 0,
        "unique_identities": 0,
        "approx_weight_exclusions": 0,
        "unresolved_gap": None,
        "status": "COMPLETE" if status == "READ" else "NOT_READ",
        "completion_reason": reason,
    }


def to_csv(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=list(fields), extrasaction="ignore", lineterminator="\r\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    return buf.getvalue().encode("utf-8")


def page_rows(s: Session, run_id: str) -> list[dict[str, Any]]:
    rows = s.scalars(
        select(ListingPage)
        .where(ListingPage.run_id == run_id)
        .order_by(
            ListingPage.csv_row_index,
            ListingPage.taxonomy_id,
            ListingPage.requested_page,
            ListingPage.attempt,
        )
    )
    return [pagination.row_summary(r) for r in rows]


PAGE_FIELDS = (
    "csv_row",
    "taxonomy_id",
    "url",
    "route",
    "requested_page",
    "returned_page",
    "attempt",
    "state",
    "verdict",
    "detail",
    "total",
    "available",
    "identities",
    "children",
    "new",
    "duplicates",
    "excluded",
    "conflicts",
    "sha256",
    "provider_request_id",
)


def coverage_files(s: Session, run_id: str) -> dict[str, bytes]:
    """The supporting files of an export. Release 1.10.0 (C1): ``deferred_requests.json`` when the run set
    a request aside to ask it again (every answer of each, the first one included); absent otherwise."""
    report = reconciliation(s, run_id)
    files = {
        "coverage_reconciliation.json": json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"),
        "coverage_reconciliation.csv": to_csv(report["listings"], LISTING_FIELDS),
        "coverage_by_csv_row.csv": to_csv(report["rows"], ROW_FIELDS),
        "listing_pages.csv": to_csv(page_rows(s, run_id), PAGE_FIELDS),
    }
    deferred = reask.export(s, run_id)
    if deferred:
        files["deferred_requests.json"] = json.dumps(
            {"run_id": run_id, "requests": deferred}, indent=2, ensure_ascii=False
        ).encode("utf-8")
    return files
