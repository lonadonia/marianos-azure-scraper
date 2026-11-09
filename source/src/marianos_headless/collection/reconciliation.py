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

from marianos_headless.collection import pagination
from marianos_headless.core.findings import RecordFlag
from marianos_headless.db.models import (
    CategorySource,
    ListingPage,
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


def node_outcomes(s: Session, run_id: str) -> list[dict[str, Any]]:
    """Each listing task's outcome. A partitioned listing is DONE only when every child listing finished and
    the distinct products of the listing and its children reach the total the site reported for it (never a
    sum of
    child counts, which overlap); otherwise INCOMPLETE, with the gap."""
    tasks = list(
        s.scalars(
            select(Task).where(Task.run_id == run_id, Task.kind == "listing_node").order_by(Task.idem_key)
        )
    )
    own: dict[str, str] = {}
    children: dict[str, list[Task]] = {}
    for t in tasks:
        cur = t.cursor or {}
        status = str(cur.get("status") or "")
        if t.state != "succeeded":
            status = "NOT_COLLECTED"
        elif status not in FINISHED_NODE:
            status = "INCOMPLETE"
        own[t.id] = status
        parent = str(((cur.get("node") or {}).get("parent")) or "")
        if parent:
            children.setdefault(f"{t.run_id}|{parent}", []).append(t)

    def kids(t: Task) -> list[Task]:
        return children.get(f"{t.run_id}|{(t.cursor or {}).get('node', {}).get('taxonomy_id', '')}", [])

    def seen(t: Task) -> set[str]:
        out = set((t.cursor or {}).get("seen") or [])
        for k in kids(t):
            out |= seen(k)
        return out

    def status_of(t: Task) -> str:
        if own[t.id] != "PARTITIONED":
            return own[t.id]
        ks = kids(t)
        total = (t.cursor or {}).get("total")
        if not ks or any(status_of(k) not in ("DONE", "EMPTY") for k in ks):
            return "INCOMPLETE"
        return "DONE" if isinstance(total, int) and len(seen(t)) >= total else "INCOMPLETE"

    out = []
    for t in tasks:
        cur = t.cursor or {}
        st = status_of(t)
        entry: dict[str, Any] = {
            "node": cur.get("node") or {},
            "status": st,
            "seen": len(seen(t)),
            "total": cur.get("total"),
            "available": cur.get("available"),
            "reason": cur.get("reason") or "",
        }
        if own[t.id] == "PARTITIONED":
            entry["partitioned"] = {
                "children": [(k.cursor or {}).get("node", {}).get("taxonomy_id") for k in kids(t)],
                "children_status": {
                    (k.cursor or {}).get("node", {}).get("taxonomy_id"): status_of(k) for k in kids(t)
                },
                "distinct_products": len(seen(t)),
                "gap": max(0, (cur.get("total") or 0) - len(seen(t))),
            }
        out.append(entry)
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
        pages[p.taxonomy_id].append(p)
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
    for outcome in node_outcomes(s, run_id):
        node = outcome["node"]
        listing = str(node.get("taxonomy_id") or "")
        rows = sorted(pages.get(listing, []), key=lambda r: (r.requested_page, r.attempt))
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
        distinct = int((outcome.get("partitioned") or {}).get("distinct_products") or 0) or max(
            unique, outcome["seen"]
        )
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
        }
        lines.append(line)
        if not line["parent_listing"]:
            by_row[int(node.get("row_index") or 0)].append(line)

    sources = list(
        s.scalars(select(CategorySource).where(CategorySource.enabled).order_by(CategorySource.csv_row_index))
    )
    rows_out: list[dict[str, Any]] = []
    for src in sources:
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
        "identities": identity_sets(s, run_id),
        "rows": rows_out,
        "listings": lines,
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
    """The supporting files of an export."""
    report = reconciliation(s, run_id)
    return {
        "coverage_reconciliation.json": json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"),
        "coverage_reconciliation.csv": to_csv(report["listings"], LISTING_FIELDS),
        "coverage_by_csv_row.csv": to_csv(report["rows"], ROW_FIELDS),
        "listing_pages.csv": to_csv(page_rows(s, run_id), PAGE_FIELDS),
    }
