"""Audited reprocessing of stored observations (release 1.5.0).

A product an earlier run observed and recorded under a rule since corrected (release 1.3.5 excluded every
product sold by weight; release 1.4.0 withdrew that rule) is rebuilt from what that run stored: its card as
displayed, the page it was on and the site's own product data captured with that page. Nothing is requested
from the site. Every input is checked against the SHA-256 recorded when it was stored, and the product data
used must be the response the original record was built from.

The result is a separate run (trigger ``reprocess``, finished ``rejected``: never published) holding one copy
of each observation and its rebuilt record, flagged ``REPROCESSED``, with the original observation time,
crawl date and page, the original record (status, reasons, SHA-256), the fields that changed and why. The
source run is never modified. A later run carries such a record forward as ``historical`` like any other
earlier verified observation: it is never a fresh observation.
"""

from __future__ import annotations

import gzip
import hashlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from marianos_headless import __version__
from marianos_headless.assembly.record_builder import CategoryAssignment, FieldSource
from marianos_headless.collection.live import build_card, offer_summaries, page_store
from marianos_headless.core.findings import DataMode, RecordFlag
from marianos_headless.core.ids import new_id
from marianos_headless.core.paths import PARSER_VERSION
from marianos_headless.core.settings import Settings, StoreConfig
from marianos_headless.core.timeutil import iso, store_local_date, utcnow
from marianos_headless.core.version import source_version
from marianos_headless.db.models import (
    Artifact,
    ProductObservation,
    RecordRow,
    Run,
    Store,
)
from marianos_headless.db.models import CapturedResponse as CapturedRow
from marianos_headless.db.models import PageFetch as PageFetchRow
from marianos_headless.publishing.exports import record_sha256
from marianos_headless.sites.marianos.observations import store_fields
from marianos_headless.sites.marianos.serialize import card_from_dict
from marianos_headless.sites.marianos.source_json import COUPONS, PRODUCTS, ResponseRef, SourceIndex
from marianos_headless.storage.base import StorageAdapter
from marianos_headless.worker.runs import create_run, event

REPROCESS_TRIGGER = "reprocess"


class ReprocessRefused(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class _Inputs:
    """The stored inputs of one product, each checked against its recorded SHA-256."""

    html: str
    page: dict[str, Any]
    sources: SourceIndex
    responses: list[dict[str, Any]] = field(default_factory=list)


def _artifact_bytes(
    s: Session, storage: StorageAdapter, artifact_id: str | None, what: str
) -> tuple[str, bytes]:
    art = s.get(Artifact, artifact_id) if artifact_id else None
    if art is None:
        raise ReprocessRefused(f"{what}: no stored artifact")
    data = storage.get_bytes(art.key)
    if _sha(data) != art.sha256:
        raise ReprocessRefused(f"{what}: stored {art.key} does not match its recorded SHA-256")
    return art.key, data


def _inputs(s: Session, storage: StorageAdapter, obs: ProductObservation, cache: dict[str, Any]) -> _Inputs:
    """The page the product was shown on and the product and coupon responses its record was built from
    (named, with their page, in the stored observation), loaded and checked."""
    pf = s.get(PageFetchRow, obs.page_fetch_id)
    if pf is None:
        raise ReprocessRefused(f"page {obs.page_fetch_id} is not in the database")
    key, raw = _artifact_bytes(s, storage, pf.dom_artifact_id, f"page {pf.id}")
    html = gzip.decompress(raw).decode("utf-8")
    structured = obs.structured or {}
    product = structured.get("product") or {}
    fetches = [pf.id]
    for ref in [
        product.get("response") or {},
        *((c or {}).get("response") or {} for c in structured.get("coupons") or []),
    ]:
        fid = ref.get("fetch_id")
        if fid and fid not in fetches:
            fetches.append(fid)
    sources = SourceIndex()
    responses: list[dict[str, Any]] = []
    rows = s.execute(
        select(CapturedRow)
        .where(CapturedRow.page_fetch_id.in_(fetches), CapturedRow.kind.in_((PRODUCTS, COUPONS)))
        .order_by(CapturedRow.observed_at, CapturedRow.id)
    ).scalars()
    for c in rows:
        if c.status != 200 or not c.artifact_id:
            continue
        if c.id not in cache:
            akey, araw = _artifact_bytes(s, storage, c.artifact_id, f"response {c.id}")
            body = gzip.decompress(araw)
            if _sha(body) != c.body_sha256:
                raise ReprocessRefused(f"response {c.id}: its body does not match its recorded SHA-256")
            cache[c.id] = (akey, body)
        akey, body = cache[c.id]
        sources.add(c.kind, body, ResponseRef(c.kind, c.page_fetch_id, c.body_sha256, iso(c.observed_at)))
        responses.append(
            {"kind": c.kind, "page_fetch_id": c.page_fetch_id, "artifact": akey, "body_sha256": c.body_sha256}
        )
    page = {
        "page_fetch_id": pf.id,
        "url": pf.url,
        "fetched_at": iso(pf.started_at),
        "dom": key,
        "dom_sha256": _sha(raw),
    }
    return _Inputs(html, page, sources, responses)


def _same_inputs(obs: ProductObservation, sources: SourceIndex) -> str | None:
    """Why the product data now indexed is not what the original record was built from, or ``None``."""
    stored = ((obs.structured or {}).get("product") or {}).get("response") or {}
    facts = sources.product(obs.upc)
    if not stored:
        return (
            None if facts is None else "the original record had no product data; a stored response has some"
        )
    if facts is None:
        return "the product response the original record used is not among the stored responses"
    if facts.ref.sha256 != stored.get("sha256") or facts.ref.fetch_id != stored.get("fetch_id"):
        return (
            f"the product data indexed now ({facts.ref.fetch_id}, {facts.ref.sha256}) is not the response "
            f"the original record used ({stored.get('fetch_id')}, {stored.get('sha256')})"
        )
    return None


def reprocess(
    s: Session,
    *,
    storage: StorageAdapter,
    settings: Settings,
    store: StoreConfig,
    detector: Any,  # marianos_headless.assembly.private_label.PrivateLabelDetector
    source_run: str,
    upcs: Iterable[str],
    reason: str,
    actor: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rebuild the records of ``upcs`` from what ``source_run`` stored, with the current rules, into a new
    ``reprocess`` run. All or nothing: any input that fails its check refuses the whole request. With
    ``dry_run`` nothing is written. The caller commits."""
    if not reason.strip():
        raise ReprocessRefused("a reason is required")
    wanted = list(dict.fromkeys(u.strip() for u in upcs if u.strip()))
    if not wanted:
        raise ReprocessRefused("no product named")
    src = s.get(Run, source_run)
    row = s.scalar(select(Store).where(Store.key == store.key))
    if src is None or row is None or src.store_id != row.id or src.mode != DataMode.LIVE.value:
        raise ReprocessRefused(f"{source_run} is not a live run of {store.key}")
    if src.trigger == REPROCESS_TRIGGER:
        raise ReprocessRefused(f"{source_run} is itself a reprocess run: reprocess its own source run")
    records = {
        r.upc: r
        for r in s.scalars(select(RecordRow).where(RecordRow.run_id == src.id, RecordRow.upc.in_(wanted)))
    }
    observations: dict[str, ProductObservation] = {}
    for o in s.scalars(
        select(ProductObservation)
        .where(ProductObservation.run_id == src.id, ProductObservation.upc.in_(wanted))
        .order_by(ProductObservation.observed_at, ProductObservation.id)
    ):
        observations.setdefault(o.upc, o)  # the first placement built the record
    missing = [u for u in wanted if u not in records or u not in observations]
    if missing:
        raise ReprocessRefused(f"not recorded with an observation by {source_run}: {', '.join(missing)}")
    carried = [u for u in wanted if records[u].status == "historical"]
    if carried:
        raise ReprocessRefused(f"carried forward, not observed, by {source_run}: {', '.join(carried)}")

    now = utcnow()
    code = {"version": __version__, "parser_version": PARSER_VERSION, **source_version()}
    cache: dict[str, Any] = {}
    rebuilt: list[tuple[ProductObservation, RecordRow, _Inputs, Any, str, dict[str, Any]]] = []
    for upc in wanted:
        obs, rec = observations[upc], records[upc]
        inputs = _inputs(s, storage, obs, cache)
        mismatch = _same_inputs(obs, inputs.sources)
        if mismatch:
            raise ReprocessRefused(f"{upc}: {mismatch}")
        details, header, _ = page_store(inputs.html, store)
        if details is None:
            raise ReprocessRefused(f"{upc}: no store details on its stored page {obs.page_fetch_id}")
        observed_iso = iso(obs.observed_at)
        crawl_date = str(rec.record.get("crawl_date", ""))
        if crawl_date != store_local_date(obs.observed_at, store.timezone):
            raise ReprocessRefused(f"{upc}: its crawl date {crawl_date} is not its observation's local date")
        state_src = FieldSource(
            "state", "modalityPreferences.storeDetails", obs.page_fetch_id, None, observed_iso
        )
        built = build_card(
            card_from_dict(obs.displayed),
            fetch_id=obs.page_fetch_id,
            observed_at=observed_iso,
            store=store,
            store_values=store_fields(details, header),
            store_provenance={"zipcode": state_src, "store_name": state_src, "store_location": state_src},
            category=CategoryAssignment(
                str(rec.record.get("category", "")), str(rec.record.get("sub_category", ""))
            ),
            crawl_date=crawl_date,
            settings=settings,
            detector=detector,
            sources=inputs.sources,
        ).built
        changes = {
            k: {"before": rec.record.get(k, ""), "after": v}
            for k, v in built.record.items()
            if rec.record.get(k, "") != v
        }
        audit = {
            "source_run": src.id,
            "source_record_id": rec.id,
            "source_status": rec.status,
            "source_reasons": list(rec.reasons or []),
            "source_record_sha256": rec.record_sha256,
            "source_observation_id": obs.id,
            "source_parser_version": obs.parser_version,
            "observed_at": observed_iso,
            "crawl_date": crawl_date,
            "page": inputs.page,
            "responses": inputs.responses,
            "inputs_checked": "page and responses match their recorded SHA-256; the product data is the "
            "response the original record was built from",
            "status": built.status.value,
            "reasons": [r.value for r in built.reasons],
            "changes": changes,
            "rules": code,
            "reason": reason,
            "by": actor,
            "at": iso(now),
            "note": f"not a fresh observation: the page stored on {crawl_date} rebuilt with the rules of "
            f"release {PARSER_VERSION}; nothing was requested from the site",
        }
        rebuilt.append((obs, rec, inputs, built, crawl_date, audit))

    by_status = Counter(b.status.value for _, _, _, b, _, _ in rebuilt)
    products = [
        {
            "upc": obs.upc,
            "title": b.record.get("product_title", ""),
            "before": {"status": rec.status, "reasons": list(rec.reasons or [])},
            "after": {"status": b.status.value, "reasons": [r.value for r in b.reasons]},
            "observed_at": a["observed_at"],
            "crawl_date": cd,
            "page_fetch_id": obs.page_fetch_id,
            "changes": a["changes"],
            "approx_weight": b.provenance.get("_approx_weight"),
        }
        for obs, rec, _, b, cd, a in rebuilt
    ]
    summary: dict[str, Any] = {
        "source_run": src.id,
        "products": len(rebuilt),
        "by_status": dict(sorted(by_status.items())),
        "dry_run": dry_run,
        "rules": code,
        "items": products,
    }
    if dry_run:
        return summary

    run = create_run(s, row, settings, mode=DataMode.LIVE.value, trigger=REPROCESS_TRIGGER)
    run.config_snapshot = {
        **run.config_snapshot,
        "plan": {"nodes": [], "skipped": [], "order": {"policy": "none"}},
        "provider": (src.config_snapshot or {}).get("provider", ""),
        "code": code,
        "started_by": actor,
        "pilot": True,
        "reprocess": {"source_run": src.id, "upcs": wanted, "reason": reason, "by": actor},
        "store": {"key": store.key, "location_id": store.location_id, "modality": store.modality.value},
    }
    run.status, run.started_at, run.finished_at = "rejected", now, now
    run.stop_detail = (
        f"Reprocess of {len(rebuilt)} stored observations of run {src.id} with the rules of release "
        f"{PARSER_VERSION}: no page collected, never published; the records keep their original observation "
        "time and crawl date"
    )
    run.counts = {"reprocess": {k: v for k, v in summary.items() if k != "items"}}
    for obs, rec, _, built, _, audit in rebuilt:
        prov = dict(obs.provenance or {})
        s.add(
            ProductObservation(
                id=new_id(),
                run_id=run.id,
                mode=DataMode.LIVE.value,
                upc=obs.upc,
                page_fetch_id=obs.page_fetch_id,
                source=obs.source,
                displayed=dict(obs.displayed),
                structured=dict(obs.structured or {}),
                provenance={
                    **{
                        k: prov[k]
                        for k in (
                            "node",
                            "parent",
                            "listing",
                            "category",
                            "sub_category",
                            "step",
                            "position",
                            "store_check",
                        )
                        if k in prov
                    },
                    "verified": built.status.value == "valid",
                    "fields": built.provenance,
                    "missing": built.missing,
                    "missing_kind": built.missing_kind,
                    "source_check": built.source_check,
                    "offers": offer_summaries(built, settings),
                    "reprocessed": {k: audit[k] for k in ("source_run", "source_observation_id", "reason")},
                },
                flags=list(obs.flags or []),
                parser_version=PARSER_VERSION,
                observed_at=obs.observed_at,
            )
        )
        s.add(
            RecordRow(
                id=new_id(),
                run_id=run.id,
                mode=DataMode.LIVE.value,
                upc=obs.upc,
                record=built.record,
                record_sha256=record_sha256(built.record),
                primary_category_source_id=rec.primary_category_source_id,
                status=built.status.value,
                reasons=[r.value for r in built.reasons],
                flags=[*(f.value for f in built.flags), RecordFlag.REPROCESSED.value],
                provenance={"_reprocessed": audit},
            )
        )
    event(
        s,
        run.id,
        "INFO",
        "RUN_REPROCESSED",
        f"{len(rebuilt)} stored observations of run {src.id} rebuilt with the rules of release "
        f"{PARSER_VERSION}",
        {k: v for k, v in summary.items() if k != "items"} | {"reason": reason, "by": actor},
    )
    s.flush()
    summary["run_id"] = run.id
    return summary


__all__ = ["REPROCESS_TRIGGER", "ReprocessRefused", "reprocess"]
