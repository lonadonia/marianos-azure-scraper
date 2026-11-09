"""The supporting log of a run: where each value came from and why an empty value is empty.

Product files keep exactly the 22 fields (brief §6); everything else about a record lives here: its
status, exclusion reasons and flags, the page and selector or JSON path of each field, why each empty
field is empty, what the site's own product response says about the product's store, fulfillment and
stock, its offers with their details, the store-assortment decision apart from the current offer, the UPC
outcome of its own product page, and which collection segment saw it.

Two kinds of observation are told apart:

* ``fresh``: observed by this run. A resumed run keeps what an earlier *segment of the same run* observed
  (``observation.earlier_segment`` true) and does not observe it again;
* ``carried_forward``: not observed by this run at all; the store's last verified observation from an
  *earlier run* is kept unchanged (its own run, page and crawl date in ``historical``, with why this run did
  not observe it). Its prices are the ones observed on its crawl date, not verified by this run.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from marianos_headless import __version__
from marianos_headless.core.paths import PARSER_VERSION
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.core.version import source_version
from marianos_headless.db.models import (
    Artifact,
    CollectionSegment,
    PageFetch,
    ProductObservation,
    RecordRow,
    Run,
)

EXPORTED_STATUSES = ("valid", "eligible_unpriced", "price_conflict", "exported_not_valid", "historical")


def _captures(s: Session) -> Any:
    """``capture(page_fetch_id)``: the stored page copy a record was read from (its URL, HTTP status, time,
    storage key and SHA-256), cached per page."""
    seen: dict[str, dict[str, Any] | None] = {}

    def capture(fetch_id: str | None) -> dict[str, Any] | None:
        if not fetch_id:
            return None
        if fetch_id not in seen:
            f = s.get(PageFetch, fetch_id)
            art = s.get(Artifact, f.dom_artifact_id) if f is not None and f.dom_artifact_id else None
            seen[fetch_id] = (
                None
                if f is None
                else {
                    "page_fetch_id": fetch_id,
                    "run_id": f.run_id,
                    "url": f.url,
                    "http_status": f.http_status,
                    "fetched_at": iso(f.started_at),
                    "dom_key": art.key if art is not None else None,
                    "dom_sha256": art.sha256 if art is not None else None,
                }
            )
        return seen[fetch_id]

    return capture


def supporting_log(s: Session, run_id: str) -> dict[str, Any]:
    run = s.get(Run, run_id)
    capture = _captures(s)
    segments = list(
        s.scalars(
            select(CollectionSegment)
            .where(CollectionSegment.run_id == run_id)
            .order_by(CollectionSegment.started_at, CollectionSegment.id)
        )
    )
    last_segment = segments[-1].id if segments else None
    first_seen: dict[str, ProductObservation] = {}
    for seen in s.scalars(
        select(ProductObservation)
        .where(ProductObservation.run_id == run_id)
        .order_by(ProductObservation.observed_at, ProductObservation.id)
    ):
        first_seen.setdefault(seen.upc, seen)

    records: dict[str, Any] = {}
    observed = {"fresh": 0, "fresh_earlier_segment": 0, "carried_forward": 0, "not_recorded": 0}
    upc_outcomes: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in s.scalars(select(RecordRow).where(RecordRow.run_id == run_id).order_by(RecordRow.upc)):
        o = first_seen.get(r.upc)
        prov: dict[str, Any] = dict(o.provenance or {}) if o is not None else {}
        segment = prov.get("segment")
        earlier = None if segment is None or last_segment is None else segment != last_segment
        extra = dict(r.provenance or {})
        historical = extra.get("historical")
        if historical:
            kind = "carried_forward"
        elif o is None:
            kind = "not_recorded"
        else:
            kind = "fresh_earlier_segment" if earlier else "fresh"
        observed[kind] += 1
        by_status[r.status] = by_status.get(r.status, 0) + 1
        detail = extra.get("upc_detail")
        if r.status in EXPORTED_STATUSES and not historical:
            key = str((detail or {}).get("status", "none"))
            upc_outcomes[key] = upc_outcomes.get(key, 0) + 1
        records[r.upc] = {
            "observation_kind": "carried_forward" if historical else "fresh",
            # For a carried-forward product: the earlier run's observation (run, page, date, age, prices) and
            # why this run did not observe it.
            "historical": historical,
            # The product's own page, read for the UPC/GTIN its result page did not state: extracted,
            # absent_in_source, blocked, request_failed, parse_failed, identity_mismatch or not_attempted,
            # with the page fetch, time, HTTP status, body hash and JSON path (or the earlier run reused).
            "upc_detail": detail,
            "upc_source": extra.get("upc_source"),  # the earlier sample of product pages (release 1.0.0)
            # Store assortment apart from the current offer: verified on this page, verified by an earlier
            # run (exported without a local price), unresolved (not exported), or not decided.
            "assortment": prov.get("assortment"),
            "status": r.status,
            "exported": r.status in EXPORTED_STATUSES,
            "reasons": list(r.reasons or []),
            "flags": list(r.flags or []),
            # The stored page copy the exported values were read from: this run's page for a fresh record,
            # the earlier run's page for a carried-forward one (its prices are from that date).
            "capture": capture(
                (historical or {}).get("page_fetch_id") if historical else (o.page_fetch_id if o else None)
            ),
            "observation": {
                "page_fetch_id": o.page_fetch_id if o is not None else None,
                "parser_version": o.parser_version if o is not None else None,
                "observed_at": iso(o.observed_at) if o is not None else None,
                "segment": segment,
                "browser_session": prov.get("session"),
                "node": prov.get("node"),
                "step": prov.get("step"),
                "listing": prov.get("listing"),
                "page": prov.get("page"),
                "position": prov.get("position"),
                "earlier_segment": earlier,
            },
            "fields": prov.get("fields") or {},
            "missing": prov.get("missing") or {},
            # Why each empty field is empty, by kind (when recorded): source_absent (not shown on the page),
            # extraction_failed (shown, not read), context_failed (not the store's local offer), rule.
            "missing_kind": prov.get("missing_kind") or {},
            "local_offer": prov.get("local_offer"),
            "source_check": prov.get("source_check") or {},
            "offers": prov.get("offers") or [],
            "site_data": (o.structured or {}) if o is not None else {},
        }
    return {
        "run_id": run_id,
        "mode": run.mode if run is not None else None,
        "generated_at": iso(utcnow()),
        # The code: what the run was started with (its snapshot) and what wrote this file.
        "collector": {
            "run_code": (run.config_snapshot or {}).get("code") if run is not None else None,
            "export_code": {"version": __version__, "parser_version": PARSER_VERSION, **source_version()},
        },
        "about": (
            "Supporting log of the products file: field sources, missing-value reasons, store and "
            "fulfillment checks against the site's own data, offer details, the store-assortment decision "
            "apart from the current offer, the UPC outcome of each product's own page, and the collection "
            "segment that observed each product. 'observation_kind' is 'fresh' (observed by this run; "
            "'observation.earlier_segment' is true when an earlier segment of this resumed run observed "
            "it) or 'carried_forward' (not observed by this run: an earlier run's verified observation kept "
            "unchanged, with its own crawl date, in 'historical')."
        ),
        "segments": [
            {
                "id": g.id,
                "trigger": g.trigger,
                "started_at": iso(g.started_at),
                "ended_at": iso(g.ended_at) if g.ended_at else None,
                "stop_code": g.stop_code,
                # Release 1.9.0 (T06): how the end is known. ended: closed by its own worker at
                # ``ended_at``. abandoned: its worker stopped without closing it (forced kill): the end is
                # unknown, after ``last_seen_at`` and not after ``ended_not_after`` (when recovery found
                # it). open: still running when this file was written.
                "end_state": g.end_state or "open",
                "last_seen_at": iso(g.heartbeat_at) if g.heartbeat_at else None,
                "ended_not_after": iso(g.recovered_at) if g.recovered_at else None,
            }
            for g in segments
        ],
        "counts": {
            "records": len(records),
            "by_status": by_status,
            "observed": observed,
            "upc_outcomes_of_fresh_exported": upc_outcomes,
        },
        "records": records,
    }
