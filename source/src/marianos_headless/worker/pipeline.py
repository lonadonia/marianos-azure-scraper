"""Run pipeline on the task runner: preflight → pages → assemble → validate → export.

The collector (:class:`marianos_headless.collection.live.LiveCollector`) supplies the live handlers;
this module creates runs, executes them under the store lock, and writes the exports.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections import Counter
from collections.abc import Iterator, Sequence
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import RecordStatus
from marianos_headless.collection.reconciliation import coverage_files
from marianos_headless.core.findings import DataMode
from marianos_headless.core.paths import PARSER_VERSION
from marianos_headless.core.schema import ordered_record
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.core.version import source_version
from marianos_headless.db import queue
from marianos_headless.db.locks import StoreRunLock
from marianos_headless.db.models import (
    Artifact,
    CategorySource,
    ListingPage,
    MembershipRow,
    OfferObservationRow,
    PageFetch,
    ProductObservation,
    RecordRow,
    Run,
    Store,
    Task,
)
from marianos_headless.publishing.exports import record_sha256, sort_records, write_exports
from marianos_headless.publishing.supporting_log import EXPORTED_STATUSES, supporting_log
from marianos_headless.storage.base import StorageAdapter
from marianos_headless.worker.runner import Worker
from marianos_headless.worker.runs import create_run, event, register_exports, transition

STAGES = ("preflight", "listing_node", "assemble", "validate", "export")
FINISHED_STATES = frozenset({"validated", "rejected", "published", "cancelled"})
PRIORITY = {"preflight": 10, "listing_node": 50, "assemble": 80, "validate": 90, "export": 95}


def _named_fetches(value: Any) -> Iterator[str]:
    """The page fetch ids a record's provenance names (``fetch_id``, ``page_fetch_id``), at any depth."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("fetch_id", "page_fetch_id") and isinstance(v, str):
                yield v
            else:
                yield from _named_fetches(v)
    elif isinstance(value, list):
        for v in value:
            yield from _named_fetches(v)


class Pipeline:
    def __init__(
        self,
        engine: Engine,
        storage: StorageAdapter,
        settings: Settings,
        store: StoreConfig,
        private_label: PrivateLabelConfig,
    ):
        self.engine = engine
        self.factory = sessionmaker(engine, expire_on_commit=False)
        self.storage = storage
        self.settings = settings
        self.store_cfg = store
        self.detector = PrivateLabelDetector(private_label, settings.records.store_brand_positive_value)

    # -- run setup ---------------------------------------------------------------------------------

    def create_live_run(
        self,
        s: Session,
        nodes: Sequence[Any],
        *,
        trigger: str,
        snapshot: dict[str, Any],
    ) -> str:
        """A LIVE run over planned pages (``marianos_headless.collection.nodes.Node``): a preflight
        (robots.txt and the store check), one listing task per category row, then assemble, validate and
        export. ``snapshot`` (collection settings, plan, who started it, the schedule occurrence, the code)
        is recorded with the run. The caller commits."""
        if not nodes:
            raise ValueError("no page to collect")
        store = s.scalar(select(Store).where(Store.key == self.store_cfg.key))
        if store is None:
            raise ValueError(f"store {self.store_cfg.key} is not in the database (run sync-config)")
        run = create_run(s, store, self.settings, mode=DataMode.LIVE.value, trigger=trigger)
        run.config_snapshot = {**run.config_snapshot, **snapshot}
        queue.enqueue(
            s, run.id, "preflight", f"{run.id}/preflight", priority=PRIORITY["preflight"], cursor={}
        )
        for i, node in enumerate(nodes):
            queue.enqueue(
                s,
                run.id,
                "listing_node",
                f"{run.id}/node/{i:04d}-{node.taxonomy_id}",
                priority=PRIORITY["listing_node"],
                category_source_id=node.category_source_id,
                taxonomy_id=node.taxonomy_id[:10],
                cursor={"node": node.as_dict(), "steps_done": 0, "seen": [], "status": "IN_PROGRESS"},
            )
        for kind in ("assemble", "validate", "export"):
            queue.enqueue(s, run.id, kind, f"{run.id}/{kind}", priority=PRIORITY[kind], cursor={})
        return run.id

    def prefix(self, run_id: str) -> str:
        return f"runs/{self.store_cfg.key}/{run_id}"

    async def execute(self, run_id: str, owner: str, *, collector: Any, resume: bool = False) -> str:
        """Run (or, with ``resume``, continue) a run under the store lock.

        A paused (``interrupted``) run only continues when explicitly resumed, and a finished or
        cancelled run is never restarted. Tasks leased by a worker that died are reclaimed with their
        checkpoints once the lock is held (the lock proves no other worker is alive).

        The collector's ``begin()`` may refuse to start (no key, no credits, a limit already reached): the
        run then waits, ``interrupted``, with the reason. Its ``end()`` always runs, so the provider
        session is closed and the collection segment recorded whatever happens, including a termination
        signal (the run is then left ``interrupted`` with ``TERMINATED``, resumable from its checkpoint).
        """
        with self.factory() as s:
            run = s.get(Run, run_id)
            assert run is not None
            store_id = run.store_id
            if run.status in FINISHED_STATES or (run.status == "interrupted" and not resume):
                return run.status
        lock = StoreRunLock(self.engine, store_id, run_id, owner).acquire()
        try:
            with self.factory() as s:
                run = s.get(Run, run_id)
                assert run is not None
                if run.status in FINISHED_STATES or (run.status == "interrupted" and not resume):
                    return run.status
                if run.status == "queued":
                    transition(s, run_id, "preflight")
                elif run.status == "interrupted":
                    transition(s, run_id, "running")
                run.resume_requested = False
                reclaimed = queue.reclaim_orphans(s, run_id)
                if reclaimed:
                    event(
                        s,
                        run_id,
                        "WARN",
                        "TASK_LEASE_RECLAIMED",
                        f"{reclaimed} task(s) left by a stopped worker resume from their checkpoints",
                    )
                s.commit()
            handlers = collector.handlers()
            try:
                refused = await collector.begin()
                if refused is not None:
                    return self._refuse_start(run_id, *refused)
                worker = Worker(self.factory, run_id, owner, handlers, self.settings, self.storage)
                result = await worker.run()
                # A task waits for its retry time (backoff or a 429 pause): keep the store lock and wait,
                # so an unattended run continues on its own instead of stopping half-way.
                while result.outcome == "waiting" and await self._wait_for_retry(run_id):
                    result = await worker.run()
            except asyncio.CancelledError:
                detail = "the collector received a termination signal during the run"
                await collector.end("TERMINATED", detail)
                self._interrupt(run_id, "TERMINATED", detail)
                raise
            finally:
                await collector.end()
            with self.factory() as s:
                status = s.get(Run, run_id).status  # type: ignore[union-attr]
                if result.outcome in ("aborted",) and status in ("preflight", "running"):
                    transition(s, run_id, "rejected")
                    s.commit()
                elif result.outcome == "idle" and status in ("preflight", "running", "validating"):
                    # Every task is terminal but the run never reached a final state: a task failed
                    # before validation, or exports could not be prepared. Never publishable.
                    transition(s, run_id, "rejected")
                    reason = (
                        "exports could not be prepared"
                        if status == "validating"
                        else "a task failed before the run could be validated"
                    )
                    event(s, run_id, "WARN", "RUN_REJECTED", reason)
                    s.commit()
                return s.get(Run, run_id).status  # type: ignore[union-attr]
        finally:
            lock.release()

    def _refuse_start(self, run_id: str, code: str, detail: str) -> str:
        """The collector would not start (no key, no credits, a limit reached): the run waits."""
        with self.factory() as s:
            run = s.get(Run, run_id)
            assert run is not None
            run.stop_code, run.stop_detail = code, detail[:2000]
            if run.status in ("preflight", "running"):
                transition(s, run_id, "interrupted")
            event(s, run_id, "WARN", "RUN_NOT_STARTED", detail[:500], {"stop_code": code})
            s.commit()
            return run.status

    def _interrupt(self, run_id: str, code: str, detail: str) -> None:
        """Leave a live run resumable when its worker is stopped from outside (a termination signal)."""
        with self.factory() as s:
            run = s.get(Run, run_id)
            if run is None or run.status not in ("preflight", "running"):
                return
            queue.reclaim_orphans(s, run_id)
            run.stop_code, run.stop_detail = code, detail
            run.pause_requested = False
            transition(s, run_id, "interrupted")
            event(s, run_id, "WARN", "RUN_INTERRUPTED", detail, {"stop_code": code})
            s.commit()

    async def _wait_for_retry(self, run_id: str) -> bool:
        """Sleep until the run's earliest ``retry_wait`` task is due; wake early for a stop request.

        Returns False when no task is waiting for a retry (nothing to wait for)."""
        with self.factory() as s:
            due = s.scalar(
                select(func.min(Task.not_before)).where(Task.run_id == run_id, Task.state == "retry_wait")
            )
        if due is None:
            return False
        remaining = (due - utcnow()).total_seconds()
        while remaining > 0:
            with self.factory() as s:
                stop = s.execute(
                    select(Run.cancel_requested, Run.pause_requested).where(Run.id == run_id)
                ).one()
            if stop[0] or stop[1]:
                break  # the worker applies the stop at its loop head
            await asyncio.sleep(min(1.0, remaining))
            remaining -= 1.0
        return True

    # -- helpers -----------------------------------------------------------------------------------

    def integrity(self, s: Session, run_id: str) -> tuple[bool, bool, bool]:
        """(acquisition tasks terminal, artifact hashes verify, record hashes verify) for G13. Every page the
        run stored must match its recorded hash. A request that brought no page (the provider failed it on
        every attempt) stored none: it has nothing to verify, and fails the check only when a product, offer,
        placement or listing-page row of the run, or a record's provenance, names it as a source (release
        1.8.0rc5; 1.8.0rc4 rejected run 01M6E5V6CASQ8F00VC8PE9TFYW for two fetches of a page the provider
        never brought, the fix of the Walmart collector's release 1.4.1)."""
        acq = ("preflight", "listing_node")
        open_task = s.scalars(
            select(Task).where(
                Task.run_id == run_id, Task.kind.in_(acq), Task.state.not_in(tuple(queue.TERMINAL_STATES))
            )
        ).first()
        records = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
        named = {
            *s.scalars(select(ProductObservation.page_fetch_id).where(ProductObservation.run_id == run_id)),
            *s.scalars(select(OfferObservationRow.page_fetch_id).where(OfferObservationRow.run_id == run_id)),
            *s.scalars(select(MembershipRow.page_fetch_id).where(MembershipRow.run_id == run_id)),
            *s.scalars(select(ListingPage.page_fetch_id).where(ListingPage.run_id == run_id)),
            *(f for r in records for f in _named_fetches(r.provenance)),
        }
        artifacts_ok = True
        for pf in s.scalars(select(PageFetch).where(PageFetch.run_id == run_id)):
            if pf.dom_artifact_id is None:
                artifacts_ok = artifacts_ok and pf.id not in named
                continue
            art = s.get(Artifact, pf.dom_artifact_id)
            if art is None:
                artifacts_ok = False
                continue
            try:
                data = self.storage.get_bytes(art.key)
            except KeyError:
                artifacts_ok = False
                continue
            artifacts_ok = artifacts_ok and hashlib.sha256(data).hexdigest() == art.sha256
        records_ok = all(record_sha256(ordered_record(r.record)) == r.record_sha256 for r in records)
        return open_task is None, artifacts_ok, records_ok

    # -- export ------------------------------------------------------------------------------------

    async def h_export(self, ctx: Any) -> dict[str, Any]:
        with ctx.session() as s:
            run = s.get(Run, ctx.run_id)
            assert run is not None
            ex = self.write_run_exports(s, run)
            event(
                s,
                ctx.run_id,
                "INFO",
                "EXPORTS_STAGED",
                ex.manifest.key,
                {"records": ex.manifest_body["record_count"]},
            )
            final = (run.counts or {}).get("outcome", "rejected")
            if run.status == "validating":
                transition(s, ctx.run_id, final)  # records RUN_VALIDATED or RUN_REJECTED itself
            s.commit()
        return {**ctx.cursor, "manifest": ex.manifest.key}

    def dataset_label(self, run: Run) -> str:
        """``complete`` (every planned page collected, checks passed), ``pilot`` (bounded by a limit),
        or ``partial`` (stopped early or checks failed). Only a complete, validated run is published."""
        counts = run.counts or {}
        if (run.config_snapshot or {}).get("pilot"):
            return "pilot"
        if counts.get("collection_complete") and counts.get("outcome") == "validated":
            return "complete"
        return "partial"

    def write_run_exports(self, s: Session, run: Run, prefix: str | None = None) -> Any:
        """The run's export files (products JSON and CSV with the 22 fields, memberships, offers, the
        supporting log, the validation report) and its manifest, under ``runs/<store>/<run>/exports/``
        (or ``prefix``). ``products`` is the store's retained dataset (every exported status, carried-forward
        products included); ``products_fresh`` holds only this run's own ``valid`` records (a verified fixed
        price), so it is a clean dataset with no unpriced, conflicting or carried record (release 1.4.0)."""
        recs = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run.id)))
        retailer = s.scalar(select(Store.retailer).where(Store.id == run.store_id)) or "marianos"
        sources = {
            c.id: c for c in s.scalars(select(CategorySource).where(CategorySource.retailer == retailer))
        }
        csv_order = {c.category_name: c.csv_row_index for c in sources.values()}
        exported = sort_records(
            [ordered_record(r.record) for r in recs if r.status in EXPORTED_STATUSES], csv_order
        )
        # Observed by this run itself (any of its segments) and verified with a fixed price.
        fresh = sort_records(
            [ordered_record(r.record) for r in recs if r.status == RecordStatus.VALID.value], csv_order
        )
        keys = [r.upc for r in recs if r.status in EXPORTED_STATUSES]
        offers = [
            {
                "upc": o.upc,
                "source": o.source,
                "tag": o.tag,
                "text": o.description,
                "expiry_text": o.expiry_text,
                "requires_clip": o.requires_clip,
                "kind": o.kind,
                "explicit_price": o.explicit_price,
                "modalities": o.modalities,
                "flags": o.flags,
            }
            for o in s.scalars(select(OfferObservationRow).where(OfferObservationRow.run_id == run.id))
        ]
        placements = list(
            s.scalars(
                select(MembershipRow)
                .where(MembershipRow.run_id == run.id)
                .order_by(
                    MembershipRow.category_source_id,
                    MembershipRow.taxonomy_id,
                    MembershipRow.page_offset,
                    MembershipRow.position,
                    MembershipRow.id,
                )
            )
        )
        # The placement each fresh record was built from (first placement wins): its page and listing.
        built_from = {
            o.upc: (o.page_fetch_id, (o.provenance or {}).get("node"))
            for o in s.scalars(select(ProductObservation).where(ProductObservation.run_id == run.id))
        }
        recorded_from: dict[str, str] = {}
        for m in sorted(placements, key=lambda m: (m.placement != "organic", m.position, m.id)):
            if built_from.get(m.upc) == (m.page_fetch_id, m.taxonomy_id):
                recorded_from.setdefault(m.upc, m.id)
        report = {
            "run_id": run.id,
            "status": (run.counts or {}).get("outcome", run.status),
            "dataset": self.dataset_label(run),
            "counts": run.counts,
            "excluded_by_reason": dict(Counter(x for r in recs for x in r.reasons)),
            # By product identity (the UPC).
            "duplicates": len(keys) - len(set(keys)),
        }
        ex = write_exports(
            self.storage,
            store_key=self.store_cfg.key,
            run_id=run.id,
            mode=run.mode,
            products=exported,
            memberships=[
                {
                    "key": m.upc,  # product identity (UPC)
                    "store": self.store_cfg.key,
                    "location_id": self.store_cfg.location_id,
                    "fulfillment": self.store_cfg.modality.value,
                    "run_id": run.id,
                    "segment_id": m.segment_id,
                    "csv_row": sources[m.category_source_id].csv_row_index
                    if m.category_source_id in sources
                    else None,
                    "category": sources[m.category_source_id].category_name
                    if m.category_source_id in sources
                    else None,
                    "category_source_id": m.category_source_id,
                    "listing": m.taxonomy_id,
                    "page": m.page_offset,
                    "position": m.position,
                    "via": m.via,
                    # organic | sponsored (release 1.4.0; empty on rows of earlier releases). A sponsored
                    # placement was shown on the listing's page, not as one of its own results.
                    "placement": m.placement,
                    "page_fetch_id": m.page_fetch_id,
                    "observed_at": iso(m.observed_at) if m.observed_at is not None else None,
                    # The record carries this placement's category when it is the product's first one.
                    "recorded_here": recorded_from.get(m.upc) == m.id,
                }
                for m in placements
            ],
            offers=offers,
            provenance=supporting_log(s, run.id),
            validation_report=report,
            config_snapshot=run.config_snapshot,
            versions={"collector": PARSER_VERSION, "source": source_version()},
            site_version=run.site_version,
            dataset=self.dataset_label(run),
            prefix=prefix,
            fresh_products=fresh,
            supporting=coverage_files(s, run.id),
        )
        register_exports(s, run.id, run.mode, ex)
        return ex
