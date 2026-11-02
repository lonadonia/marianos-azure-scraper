"""The store's verified products, kept across runs (assortment separate from the current offer).

A product belongs to the store's assortment once a run observed it on a page verified for the store and
its configured fulfillment (every page checked for the store and fulfillment); a
product shown unavailable there ("Prices May Vary", temporarily out of stock) is still the store's, kept
with empty prices. That verification is kept: a later run that does not show the product at all (a partial
run, a listing not read, or a product missing from its listing) carries the last verified observation
forward unchanged, with its own crawl date, as ``historical`` (``CARRIED_FORWARD``), and says why it was not
observed. A product read through a child listing (a listing larger than the site's result window) belongs to
the client's listing it stands for, whichever way a later run reads that listing. Nothing verified is ever
dropped because a later listing was incomplete or the product became unavailable. Since release 1.4.0
no age limit drops one either: a configured ``max_age_days`` only marks an older observation (its age and
``past_age_limit`` in the supporting log) and counts it, so its staleness is visible without losing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from marianos_headless.core.findings import DataMode, RecordFlag
from marianos_headless.core.ids import new_id
from marianos_headless.core.schema import ordered_record
from marianos_headless.core.timeutil import iso
from marianos_headless.db.models import NodeCoverage, ProductObservation, RecordRow, Run
from marianos_headless.publishing.exports import record_sha256

# Statuses of a fresh observation that verifies a product locally (a local offer, priced or not): a
# verified price, no fixed current price, a price differing from the product's own data, or an incomplete
# identity (release 1.4.0 split the first three out of ``exported_not_valid``).
VERIFYING_STATUSES = ("valid", "eligible_unpriced", "price_conflict", "exported_not_valid")
CARRIED_STATUS = "historical"


@dataclass(frozen=True)
class Verified:
    """The latest observation of a product with a local offer of the store."""

    key: str
    run_id: str
    observed_at: datetime
    record: dict[str, Any]
    flags: tuple[str, ...]
    category_source_id: str | None
    listing: str | None
    page_fetch_id: str
    read_through: str | None = None  # the child listing that showed it, when its listing was partitioned
    # The audit trail of a record rebuilt from a stored observation (``reprocess``, release 1.5.0).
    reprocessed: dict[str, Any] | None = None

    def summary(self, now: datetime | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "run_id": self.run_id,
            "observed_at": iso(self.observed_at),
            "crawl_date": str(self.record.get("crawl_date", "")),
            "page_fetch_id": self.page_fetch_id,
            "listing": self.listing,
            "regular_price": str(self.record.get("regular_price", "")),
            "sale_price": str(self.record.get("sale_price", "")),
        }
        if self.read_through:
            out["read_through"] = self.read_through
        if self.reprocessed:
            out["reprocessed"] = self.reprocessed
        if now is not None:
            out["age_days"] = max(0, (now - self.observed_at).days)
        return out


def verified_local(s: Session, store_id: str, exclude_run: str | None = None) -> dict[str, Verified]:
    """Every product a run of the store observed with a local offer, with its latest such observation.
    An observation without a local offer (``NO_LOCAL_OFFER``) and a carried-forward row are not
    verifications."""
    q = (
        select(
            RecordRow,
            ProductObservation.observed_at,
            ProductObservation.provenance,
            ProductObservation.page_fetch_id,
        )
        .join(Run, Run.id == RecordRow.run_id)
        .join(
            ProductObservation,
            (ProductObservation.run_id == RecordRow.run_id) & (ProductObservation.upc == RecordRow.upc),
        )
        .where(
            Run.store_id == store_id,
            Run.mode == DataMode.LIVE.value,
            RecordRow.status.in_(VERIFYING_STATUSES),
        )
        .order_by(ProductObservation.observed_at, RecordRow.id)
    )
    if exclude_run is not None:
        q = q.where(Run.id != exclude_run)
    out: dict[str, Verified] = {}
    for item in s.execute(q).all():
        row, observed_at, prov, fetch_id = cast(
            tuple[RecordRow, datetime, dict[str, Any] | None, str], tuple(item)
        )
        flags = tuple(row.flags or [])
        if RecordFlag.NO_LOCAL_OFFER.value in flags or RecordFlag.CARRIED_FORWARD.value in flags:
            continue
        prov = prov or {}
        parent = prov.get("parent")
        out[row.upc] = Verified(
            row.upc,
            row.run_id,
            observed_at,
            dict(row.record),
            flags,
            row.primary_category_source_id,
            parent or prov.get("listing") or prov.get("node"),
            fetch_id,
            prov.get("node") if parent else None,
            reprocessed_of(row.provenance),
        )
    return out


def reprocessed_of(provenance: dict[str, Any] | None) -> dict[str, Any] | None:
    """The short audit trail a carried-forward record keeps of a record rebuilt from a stored observation."""
    audit = (provenance or {}).get("_reprocessed")
    if not isinstance(audit, dict):
        return None
    return {k: audit.get(k) for k in ("source_run", "source_status", "source_reasons", "rules", "reason")}


def coverage_status(s: Session, run_id: str) -> dict[str, str]:
    """This run's listing (or node) statuses, by listing id."""
    return {
        c.taxonomy_id: c.status for c in s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))
    }


def why_not_observed(listing: str | None, coverage: dict[str, str], run_complete: bool) -> str:
    if listing is None:
        return "not observed by this run (the earlier observation names no listing)"
    status = coverage.get(listing)
    if status is None:
        return f"its listing {listing} was not read by this run" + (
            "" if run_complete else " (a partial run)"
        )
    if status in ("DONE", "EMPTY"):
        return (
            f"not shown by its listing {listing}, read to its end by this run (unavailable or delisted now)"
        )
    if status == "PARTITIONED":
        return (
            f"not shown by its listing {listing} or the child listings it was read through by this run "
            "(the run's coverage says whether they covered the listing)"
        )
    return f"its listing {listing} was read only in part by this run ({status})"


def why_kind(listing: str | None, coverage: dict[str, str]) -> str:
    """The class of :func:`why_not_observed`: this run did not try, or tried and did not get the page, or read
    the listing to its end and the product was not there."""
    status = coverage.get(listing or "")
    if status is None:
        return "not_attempted"
    if status in ("DONE", "EMPTY", "PARTITIONED"):
        return "not_displayed"
    return "access_failure"


def carry_forward(
    s: Session,
    run_id: str,
    store_id: str,
    now: datetime,
    *,
    max_age_days: int | None,
    run_complete: bool,
) -> dict[str, int]:
    """Products verified by earlier runs of the store and not observed by this one: the latest verified
    observation is added to this run unchanged (status ``historical``, flag ``CARRIED_FORWARD``, its own
    record and crawl date), with where it came from and why this run did not observe it. Idempotent.
    An observation older than ``max_age_days`` is still carried, marked ``past_age_limit`` and counted as
    ``too_old`` (release 1.4.0: nothing verified is deleted by age)."""
    counts = {"carried_forward": 0, "too_old": 0}
    present = set(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))
    complete = run_complete
    coverage = coverage_status(s, run_id)
    for key, v in verified_local(s, store_id, exclude_run=run_id).items():
        if key in present:
            continue
        info = {
            **v.summary(now),
            "why_not_observed": why_not_observed(v.listing, coverage, complete),
            "why_kind": why_kind(v.listing, coverage),
            "note": "an earlier run's verified local observation, carried forward unchanged: its prices are "
            "the ones observed on its crawl date, not verified by this run",
            "kept": True,
        }
        if max_age_days is not None and info["age_days"] > max_age_days:
            info["past_age_limit"] = max_age_days
            counts["too_old"] += 1
        flags = [
            *(f for f in v.flags if f != RecordFlag.CARRIED_FORWARD.value),
            RecordFlag.CARRIED_FORWARD.value,
        ]
        s.add(
            RecordRow(
                id=new_id(),
                run_id=run_id,
                mode=DataMode.LIVE.value,
                upc=key,
                record=dict(v.record),
                record_sha256=record_sha256(ordered_record(v.record)),
                primary_category_source_id=v.category_source_id,
                status=CARRIED_STATUS,
                reasons=[RecordFlag.CARRIED_FORWARD.value],
                flags=flags,
                provenance={"historical": info},
            )
        )
        counts["carried_forward"] += 1
    s.flush()
    return counts
