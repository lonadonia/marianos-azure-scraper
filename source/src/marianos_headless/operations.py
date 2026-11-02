"""The collector's operations, one per command. Each runs once and returns an exit code.

Nothing here schedules anything. Azure Container Apps starts the job (one scheduled trigger per store) and
the job exits when its run has finished or stopped. ``run --scheduled`` checks three things:

* the execution is the store's due occurrence, in store-local time, so a daylight-saving change never
  shifts it;
* the store's schedule is not held;
* whether the occurrence already has a run. An Azure retry or the second UTC firing then does nothing
  twice.

Retries are bounded inside one execution: a page is retried as ``settings.retries`` allows, and a run
stopped by a transient provider failure is resumed at most ``max_auto_resumes`` times. A run stopped by a
limit, or by an operator's stop request, is finalized: its records are checked and exported as a pilot or
partial dataset, kept under the run, and never published. Only a complete, validated run is published as
the store's latest dataset.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import socket
import tempfile
from collections import Counter
from collections.abc import Callable
from datetime import datetime, time, timedelta
from enum import IntEnum
from functools import cached_property
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.acquisition import oxylabs
from marianos_headless.checks import contract, source_check
from marianos_headless.collection import control, reprocess, scrapfly_account
from marianos_headless.collection.config import parse_hhmm
from marianos_headless.collection.limits import (
    LIMIT_STOPS,
    SUSPENDS_SCHEDULE,
    StopCode,
    stop_text,
)
from marianos_headless.collection.live import LiveCollector
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.collection.schedule import Occurrence, local_day, next_occurrence, occurrence_on
from marianos_headless.config_file import LoadedConfig, StoreCollection
from marianos_headless.core import logs
from marianos_headless.core.jsonio import dumps_bytes
from marianos_headless.core.settings import BrowserProvider, Settings, StorageSettings
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.db import migrate
from marianos_headless.db.locks import RunLockHeld, worker_alive
from marianos_headless.db.models import (
    Artifact,
    AuditLog,
    CapturedResponse,
    ExportRow,
    PageFetch,
    Publication,
    PublicationPointer,
    RecordRow,
    Run,
    SettingRow,
    Store,
    ValidationFinding,
)
from marianos_headless.db.repo import import_category_sources, sync_stores
from marianos_headless.db.session import make_engine
from marianos_headless.publishing.exports import manifest_files, verify_manifest
from marianos_headless.publishing.publish import (
    NON_BLOCKING_GATES,
    PublicationRefused,
    latest_key,
    publish_run,
    rollback_publication,
)
from marianos_headless.sites.marianos.csv_sources import load_category_csv
from marianos_headless.storage.base import ImmutableWriteError, StorageAdapter
from marianos_headless.storage.factory import make_storage
from marianos_headless.worker.pipeline import FINISHED_STATES, Pipeline
from marianos_headless.worker.runs import event, transition
from marianos_headless.worker.store_selection import base_of


class Exit(IntEnum):
    OK = 0  # finished (validated or published), or nothing was due
    UNEXPECTED = 1
    CONFIG = 2  # configuration or database schema
    CREDENTIALS = 3  # no provider key, or the provider refused it
    CREDITS = 4  # provider credits or a credit budget ran out
    SITE_REFUSAL = 5  # the website refused access (403/429, challenge)
    REJECTED = 6  # the run's checks rejected it, or an export did not verify
    NOT_VERIFIED = 7  # the store, fulfillment or the canary checks failed
    HELD = 8  # the store's collection is held until an operator releases it
    BUSY = 9  # another execution holds the store, or an unfinished run must be resumed or finalized
    INTERRUPTED = 75  # stopped resumably (termination signal, provider failure); resume continues it


STOP_EXIT: dict[str, Exit] = {
    StopCode.NO_API_KEY: Exit.CREDENTIALS,
    StopCode.PROVIDER_AUTH: Exit.CREDENTIALS,
    StopCode.CREDITS_EXHAUSTED: Exit.CREDITS,
    StopCode.SPENDING_CEILING: Exit.CREDITS,
    StopCode.CREDIT_RESERVE: Exit.CREDITS,
    StopCode.RUN_CREDIT_LIMIT: Exit.CREDITS,
    StopCode.DAILY_CREDIT_LIMIT: Exit.CREDITS,
    StopCode.SITE_REFUSAL: Exit.SITE_REFUSAL,
    StopCode.STORE_NOT_VERIFIED: Exit.NOT_VERIFIED,
    StopCode.CANARY_CHECK_FAILED: Exit.NOT_VERIFIED,
    StopCode.ABNORMAL_RESULT: Exit.REJECTED,
    StopCode.TERMINATED: Exit.INTERRUPTED,
}
CREDIT_STOPS = frozenset(
    {
        StopCode.CREDITS_EXHAUSTED,
        StopCode.SPENDING_CEILING,
        StopCode.CREDIT_RESERVE,
        StopCode.RUN_CREDIT_LIMIT,
        StopCode.DAILY_CREDIT_LIMIT,
    }
)
# Stopped by its own bounds or an operator: the run is finalized with what it collected.
FINALIZE_ON = frozenset({*LIMIT_STOPS, StopCode.OPERATOR_STOP, StopCode.SUPERSEDED})
# Stopped by a transient failure: resumed in the same execution, a bounded number of times.
AUTO_RESUME_ON = frozenset({StopCode.PROVIDER_ERROR, StopCode.ACCOUNT_UNAVAILABLE, StopCode.SERVICE_RESTART})
AUTO_RESUME_WAIT_S = 60.0
EARLY_START = timedelta(minutes=5)  # a scheduled execution a little before the start time counts as on time
HOLD_PREFIX = "hold:"
ENV_STORAGE = "MARIANOS_COLLECTOR_STORAGE"
ENV_DATA_DIR = "MARIANOS_COLLECTOR_DATA_DIR"
ENV_BLOB_URL = "MARIANOS_COLLECTOR_BLOB_ACCOUNT_URL"
ENV_BLOB_CONTAINER = "MARIANOS_COLLECTOR_BLOB_CONTAINER"


class CommandError(Exception):
    """A command refused with a reason and an exit code (nothing was changed)."""

    def __init__(self, code: Exit, message: str, **data: Any):
        super().__init__(message)
        self.code = code
        self.data = data


# -- context ------------------------------------------------------------------------------------------


class Context:
    """The configuration, and lazily the database and storage of one command."""

    def __init__(self, config_path: Path, *, environ: dict[str, str] | None = None):
        self.environ = dict(os.environ if environ is None else environ)
        self.config = LoadedConfig(config_path)
        self.owner = f"{socket.gethostname()}:{os.getpid()}"
        self.clock: Callable[[], datetime] = utcnow  # tests replace it to simulate a store-local time
        self._engine: Engine | None = None

    @cached_property
    def storage_settings(self) -> StorageSettings:
        base = self.config.settings.storage
        update: dict[str, Any] = {}
        if self.environ.get(ENV_STORAGE):
            update["backend"] = self.environ[ENV_STORAGE]
        if self.environ.get(ENV_DATA_DIR):
            update["local_root"] = self.environ[ENV_DATA_DIR]
        if self.environ.get(ENV_BLOB_URL):
            update["azure_account_url"] = self.environ[ENV_BLOB_URL]
        if self.environ.get(ENV_BLOB_CONTAINER):
            update["azure_container"] = self.environ[ENV_BLOB_CONTAINER]
        return StorageSettings.model_validate({**base.model_dump(), **update})

    @property
    def site_base(self) -> str:
        """The site the runs collect: scheme and host of the cloud browser's configured target."""
        return base_of(self.settings.acquisition.scrapfly.target_url)

    @cached_property
    def settings(self) -> Settings:
        return self.config.settings.model_copy(update={"storage": self.storage_settings})

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = make_engine()
        return self._engine

    @cached_property
    def factory(self) -> sessionmaker[Session]:
        return sessionmaker(self.engine, expire_on_commit=False)

    @cached_property
    def storage(self) -> StorageAdapter:
        return make_storage(self.storage_settings, base_dir=Path.cwd())

    def pipeline(self, store_key: str) -> Pipeline:
        store = self.config.store(store_key)
        return Pipeline(self.engine, self.storage, self.settings, store, self.config.private_label)

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()

    def require_schema(self) -> None:
        current, head = migrate.state(self.engine)
        if current != head:
            raise CommandError(
                Exit.CONFIG,
                "the database schema is not current: run 'marianos-collector db-upgrade'",
                current=current,
                head=head,
            )


# -- configuration ---------------------------------------------------------------------------------


def masked_key() -> dict[str, Any]:
    return scrapfly_account.key_info()


def oxylabs_key_info() -> dict[str, Any]:
    key = oxylabs.load_key()
    source = None
    if os.environ.get(oxylabs.ENV_KEY):
        source = oxylabs.ENV_KEY
    elif os.environ.get(oxylabs.ENV_KEY_FILE):
        source = oxylabs.ENV_KEY_FILE
    return {
        "configured": key is not None,
        "source": source,
        "fingerprint": f"…{oxylabs.fingerprint(key)[-6:]}" if key is not None else None,
    }


def run_provider(run: Run) -> str:
    """The provider a run collects with, fixed when it was created (runs created before 1.3.0: Scrapfly)."""
    return str((run.config_snapshot or {}).get("provider") or BrowserProvider.SCRAPFLY.value)


def utc_cron(coll: StoreCollection, year: int | None = None) -> dict[str, Any]:
    """The Azure cron expression (UTC) that covers the store-local schedule in standard and daylight time.

    Azure evaluates cron in UTC. The expression fires at the UTC time of the local start for both offsets
    of the timezone; ``run --scheduled`` then acts only on the firing that is the due local occurrence."""
    sched = coll.schedule
    tz = ZoneInfo(coll.timezone)
    year = year or utcnow().year
    hh, mm = (int(x) for x in sched.start_time.split(":"))
    minutes: set[int] = set()
    hours: set[int] = set()
    days: set[int] = set()
    offsets: dict[str, str] = {}
    for label, month in (("january", 1), ("july", 7)):
        local = datetime(year, month, 15, hh, mm, tzinfo=tz)
        utc = local.astimezone(ZoneInfo("UTC"))
        offsets[label] = f"local {sched.start_time} = {utc:%H:%M} UTC (UTC{local:%z})"
        shift = (utc.date() - local.date()).days
        minutes.add(utc.minute)
        hours.add(utc.hour)
        for wd in sched.weekdays:
            days.add(((wd + shift) % 7 + 1) % 7)  # cron: 0 = Sunday
    expr = (
        f"{','.join(map(str, sorted(minutes)))} {','.join(map(str, sorted(hours)))} * * "
        f"{','.join(map(str, sorted(days)))}"
        if sched.weekdays
        else None
    )
    out: dict[str, Any] = {"cron_utc": expr, "offsets": offsets, "timezone": coll.timezone}
    if sched.continue_unfinished:
        # Continuation firings (a run longer than one execution): the job fires every 30 minutes; each firing
        # starts the due occurrence, continues the store's unfinished scheduled run inside the daily window,
        # or exits in seconds. This expression replaces the start-only one above.
        out["cron_utc_with_continuation"] = "*/30 * * * *"
    return out


def describe_config(ctx: Context) -> dict[str, Any]:
    cfg = ctx.config
    sources, csv_sha = load_category_csv(cfg.categories_csv)
    names = {s.row_index: s.category_name for s in sources}
    stores = []
    for st in cfg.stores.stores:
        coll = cfg.collection(st.key)
        unknown = [r for r in coll.categories if r not in names]
        if unknown:
            raise CommandError(Exit.CONFIG, f"{st.key}: category rows not in the CSV: {unknown}")
        tz = ZoneInfo(coll.timezone)
        nxt = next_occurrence(coll.schedule, utcnow(), tz) if coll.schedule.enabled else None
        stores.append(
            {
                "key": st.key,
                "enabled": st.enabled,
                "store_id": st.location_id,
                "zipcode": st.expected.postal_code,
                "name": st.expected.display_name,
                "address": st.expected.address_line1,
                "fulfillment": st.modality.value,
                "categories": [names[r] for r in coll.categories] or "all",
                "limits": coll.limits.model_dump(exclude_none=True),
                "pilot_by_limits": coll.limits.bounded(),
                "schedule": {
                    **coll.schedule.model_dump(mode="json"),
                    **utc_cron(coll),
                    "next_local_start": nxt.start.isoformat() if nxt else None,
                },
            }
        )
    return {
        "config": str(cfg.path),
        "categories_csv": {"path": str(cfg.categories_csv), "rows": len(sources), "sha256": csv_sha},
        "stores": stores,
        "canary": cfg.collector.canary.model_dump(),
        "publish": cfg.collector.publish.model_dump(),
        "storage": {"backend": ctx.storage_settings.backend},
        "environment": {
            "database_url_set": bool(ctx.environ.get("MARIANOS_COLLECTOR_DATABASE_URL")),
            "database_auth": ctx.environ.get("MARIANOS_COLLECTOR_DATABASE_AUTH") or "password",
            "scrapfly_key": masked_key(),
            "oxylabs_key": oxylabs_key_info(),
            "provider": ctx.settings.acquisition.browser_provider.value,
        },
    }


def sync_config(ctx: Context, actor: str) -> dict[str, Any]:
    """Stores and the category CSV into the database (idempotent; rows no longer in the CSV are disabled)."""
    sources, csv_sha = load_category_csv(ctx.config.categories_csv)
    with ctx.factory() as s:
        stores = sync_stores(s, ctx.config.stores, actor)
        cats = import_category_sources(s, sources, csv_sha, actor)
        s.commit()
    return {
        "stores": vars(stores),
        "categories": {**vars(cats), "csv_sha256": csv_sha},
    }


# -- holds ----------------------------------------------------------------------------------------------


def get_hold(s: Session, store_key: str) -> dict[str, Any] | None:
    row = s.get(SettingRow, HOLD_PREFIX + store_key)
    return dict(row.value) if row is not None and row.value.get("held") else None


def set_hold(s: Session, store_key: str, run: Run) -> None:
    value = {
        "held": True,
        "stop_code": run.stop_code,
        "reason": f"{stop_text(run.stop_code)}: {run.stop_detail or ''}"[:500],
        "run_id": run.id,
        "at": iso(utcnow()),
    }
    row = s.get(SettingRow, HOLD_PREFIX + store_key)
    if row is None:
        s.add(SettingRow(key=HOLD_PREFIX + store_key, value=value, updated_by="collector"))
    else:
        row.value, row.updated_by = value, "collector"
    s.add(AuditLog(actor="collector", action="collection_held", target=store_key, data=value))
    event(
        s,
        run.id,
        "WARN",
        "COLLECTION_HELD",
        f"{store_key}: collection held until an operator runs release-hold",
        {"stop_code": run.stop_code},
    )


def release_hold(ctx: Context, store_key: str, reason: str, actor: str) -> dict[str, Any]:
    ctx.config.store(store_key)
    if not reason.strip():
        raise CommandError(Exit.CONFIG, "a reason is required to release a hold")
    with ctx.factory() as s:
        hold = get_hold(s, store_key)
        if hold is None:
            return {"store": store_key, "held": False, "released": False}
        row = s.get(SettingRow, HOLD_PREFIX + store_key)
        assert row is not None
        row.value = {
            **hold,
            "held": False,
            "released_at": iso(utcnow()),
            "released_by": actor,
            "reason": reason,
        }
        s.add(AuditLog(actor=actor, action="hold_released", target=store_key, reason=reason, data=hold))
        s.commit()
    logs.log("INFO", "HOLD_RELEASED", store=store_key, reason=reason, previous=hold)
    return {"store": store_key, "held": False, "released": True, "previous": hold}


def reprocess_products(
    ctx: Context,
    store_key: str,
    source_run: str,
    upcs_file: Path,
    reason: str,
    actor: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rebuild the products listed in ``upcs_file`` (one UPC per line) from what ``source_run`` stored, with
    the current rules, into a new ``reprocess`` run (release 1.5.0; :mod:`collection.reprocess`). Refused
    while the store has an unfinished run, or when any stored input fails its check."""
    ctx.require_schema()
    pipe = ctx.pipeline(store_key)
    try:
        upcs = [line.strip() for line in upcs_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        raise CommandError(Exit.CONFIG, f"cannot read {upcs_file}: {exc}") from None
    with ctx.factory() as s:
        row = s.scalar(select(Store).where(Store.key == store_key))
        if row is not None and control.open_run(s, row.id) is not None:
            raise CommandError(Exit.BUSY, f"{store_key} has an unfinished run: finish it before reprocessing")
        try:
            data = reprocess.reprocess(
                s,
                storage=ctx.storage,
                settings=ctx.settings,
                store=pipe.store_cfg,
                detector=pipe.detector,
                source_run=source_run,
                upcs=upcs,
                reason=reason,
                actor=actor,
                dry_run=dry_run,
            )
        except reprocess.ReprocessRefused as exc:
            s.rollback()
            raise CommandError(Exit.CONFIG, f"reprocess refused: {exc}") from None
        if dry_run:
            s.rollback()
        else:
            s.add(
                AuditLog(
                    actor=actor,
                    action="reprocess",
                    target=data["run_id"],
                    reason=reason,
                    data={k: v for k, v in data.items() if k != "items"},
                )
            )
            s.commit()
    logs.log(
        "INFO",
        "REPROCESS_DRY_RUN" if dry_run else "REPROCESSED",
        store=store_key,
        source_run=source_run,
        run_id=data.get("run_id"),
        by_status=data["by_status"],
    )
    return data


# -- runs -----------------------------------------------------------------------------------------------


# A bounded (pilot) run fails the coverage check by design: the pages its limits left out were not read.
PILOT_EXPECTED_GATES = frozenset({"G3"})


def failed_gates(s: Session, run_id: str) -> list[str]:
    """The blocking checks that failed (G14, the readiness marker, never blocks)."""
    return sorted(
        {
            f.gate
            for f in s.scalars(
                select(ValidationFinding).where(
                    ValidationFinding.run_id == run_id, ValidationFinding.severity == "FAIL"
                )
            )
            if f.gate not in NON_BLOCKING_GATES
        }
    )


def exit_for(s: Session, run: Run) -> Exit:
    code = run.stop_code
    if run.status in ("validated", "published"):
        return Exit.CREDITS if code in CREDIT_STOPS else Exit.OK
    if run.status == "rejected":
        # A finished run is never "stopped resumably" (75): nothing can continue it any more.
        if code in STOP_EXIT and STOP_EXIT[code] is not Exit.INTERRUPTED:
            return STOP_EXIT[code]
        pilot = bool((run.config_snapshot or {}).get("pilot"))
        if pilot and set(failed_gates(s, run.id)) <= PILOT_EXPECTED_GATES:
            return Exit.OK  # the pilot collected what its limits allowed and every record check passed
        return Exit.REJECTED
    if run.status == "interrupted":
        return STOP_EXIT.get(code or "", Exit.INTERRUPTED)
    if run.status == "cancelled":
        return Exit.OK
    return Exit.UNEXPECTED


def run_summary(pipe: Pipeline | None, run: Run) -> dict[str, Any]:
    counts = run.counts or {}
    snap = run.config_snapshot or {}
    return {
        "run_id": run.id,
        "status": run.status,
        "trigger": run.trigger,
        "dataset": pipe.dataset_label(run) if pipe is not None else None,
        "pilot": bool(snap.get("pilot")),
        "occurrence": (snap.get("occurrence") or {}).get("day"),
        "stop_code": run.stop_code,
        "stop_detail": run.stop_detail,
        "created_at": iso(run.created_at) if run.created_at else None,
        "started_at": iso(run.started_at) if run.started_at else None,
        "finished_at": iso(run.finished_at) if run.finished_at else None,
        "outcome": counts.get("outcome"),
        "records_by_status": counts.get("records_by_status"),
        "collection_complete": counts.get("collection_complete"),
        "canary": counts.get("canary"),
        "historical": counts.get("historical"),
    }


def collection_of(run: Run) -> StoreCollection:
    """The collection settings recorded with the run (a resumed run keeps its limits)."""
    return StoreCollection.model_validate((run.config_snapshot or {}).get("collection") or {})


def check_key(provider: str = BrowserProvider.SCRAPFLY.value) -> None:
    """The key of the provider a run collects with (never another provider's)."""
    if provider == BrowserProvider.OXYLABS.value:
        if oxylabs.load_key() is None:
            raise CommandError(
                Exit.CREDENTIALS,
                f"no Oxylabs Web API key: set {oxylabs.ENV_KEY} or {oxylabs.ENV_KEY_FILE} (a protected file)",
            )
        return
    if scrapfly_account.load_key() is None:
        raise CommandError(
            Exit.CREDENTIALS,
            "no Scrapfly key: set SCRAPFLY_API_KEY or SCRAPFLY_API_KEY_FILE (an Azure secret)",
        )


def _store_row(s: Session, store_key: str) -> Store:
    row = s.scalar(select(Store).where(Store.key == store_key))
    if row is None:
        raise CommandError(Exit.CONFIG, f"store {store_key} is not in the database: run sync-config")
    return row


async def _execute(ctx: Context, store_key: str, run_id: str, *, trigger: str, resume: bool) -> str:
    pipe = ctx.pipeline(store_key)
    with ctx.factory() as s:
        run = s.get(Run, run_id)
        assert run is not None
        cfg = collection_of(run)
        provider = run_provider(run)
    configured = ctx.settings.acquisition.browser_provider.value
    if provider != configured:
        # A run never changes provider: no comparison or resumed run is completed silently by another.
        raise CommandError(
            Exit.CONFIG,
            f"run {run_id} collects with {provider} but the configuration names {configured}: set "
            f"acquisition.browser_provider back to {provider}, or finalize the run",
            run_id=run_id,
        )
    common: dict[str, Any] = {
        "config": cfg,
        "trigger": trigger,
        "clock": ctx.clock,
        "canary": ctx.config.collector.canary,
        "historical": ctx.config.collector.historical,
    }
    collector: LiveCollector
    if provider == BrowserProvider.OXYLABS.value:
        collector = OxylabsCollector(pipe, run_id, api_key=oxylabs.load_key(), **common)
    else:
        collector = LiveCollector(pipe, run_id, api_key=scrapfly_account.load_key(), **common)
    status: str = await pipe.execute(run_id, ctx.owner, collector=collector, resume=resume)
    return status


async def drive(ctx: Context, store_key: str, run_id: str, *, trigger: str, resume: bool) -> Exit:
    """Execute a run to its end in this execution: finalize it after a limit or an operator's stop, resume
    it (bounded) after a transient failure, then hold, publish or keep the partial result."""
    finalized = False
    while True:
        logs.log("INFO", "RUN_EXECUTING", run_id=run_id, store=store_key, trigger=trigger, resume=resume)
        try:
            await _execute(ctx, store_key, run_id, trigger=trigger, resume=resume)
        except RunLockHeld as exc:
            logs.log("WARN", "STORE_BUSY", run_id=run_id, store=store_key, message=str(exc))
            return Exit.BUSY
        resume = True
        with ctx.factory() as s:
            run = s.get(Run, run_id)
            assert run is not None
            code = run.stop_code
            if (
                run.status == "interrupted"
                and not finalized
                and (run.finish_requested or (code in FINALIZE_ON and not continues_later(run, code)))
            ):
                control.prepare_finish(s, run)
                s.commit()
                finalized, trigger = True, "finish"
                continue
            if run.status == "interrupted" and code in AUTO_RESUME_ON:
                counts = dict(run.counts or {})
                attempts = int(counts.get("auto_resumes", 0))
                limit = collection_of(run).max_auto_resumes
                if attempts < limit:
                    counts["auto_resumes"] = attempts + 1
                    run.counts = counts
                    event(
                        s,
                        run_id,
                        "INFO",
                        "RUN_AUTO_RESUMED",
                        f"automatic resume {attempts + 1} of {limit} after: {stop_text(code)}",
                    )
                    s.commit()
                    await asyncio.sleep(AUTO_RESUME_WAIT_S * (attempts + 1))
                    trigger = "auto"
                    continue
        break
    return after_run(ctx, store_key, run_id)


def continues_later(run: Run, code: str | None) -> bool:
    """A run paused at its execution's time limit is continued by the next execution (``resume`` or the
    schedule), never finalized there; a scheduled run that reached its daily window's end is continued on
    a later day when the schedule continues unfinished runs."""
    if code == StopCode.SEGMENT_DURATION_LIMIT.value:
        return True
    if code == StopCode.SCHEDULE_WINDOW_END.value and run.trigger == "schedule":
        return collection_of(run).schedule.continue_unfinished
    return False


def daily_window_open(coll: StoreCollection, now: datetime) -> bool:
    """Inside the schedule's daily window today (any weekday: a continuation day)."""
    tz = ZoneInfo(coll.timezone)
    local = now.astimezone(tz)
    sched = coll.schedule
    start = datetime.combine(local.date(), parse_hhmm(sched.window_start or sched.start_time), tzinfo=tz)
    end = (
        datetime.combine(local.date(), parse_hhmm(sched.window_end), tzinfo=tz)
        if sched.window_end
        else datetime.combine(local.date() + timedelta(days=1), time(0, 0), tzinfo=tz)
    )
    return start <= local < end


async def continue_scheduled(
    ctx: Context, store_key: str, coll: StoreCollection, now: datetime
) -> Exit | None:
    """A firing that is not an occurrence's start: continue the store's unfinished scheduled run (an earlier
    execution paused it at its time limit or the window's end, or it was interrupted) when the schedule
    continues unfinished runs and the daily window is open. ``None``: nothing to continue now."""
    if not coll.schedule.continue_unfinished or not daily_window_open(coll, now):
        return None
    with ctx.factory() as s:
        row = s.scalar(select(Store).where(Store.key == store_key))
        if row is None:  # never synced, so never run: nothing to continue
            return None
        current = control.open_run(s, row.id)
        if current is None or current.trigger != "schedule":
            return None
        if current.status in control.ACTIVE and worker_alive(s, row.id, current.id):
            logs.log("WARN", "STORE_BUSY", store=store_key, run_id=current.id)
            return Exit.BUSY
        if get_hold(s, store_key) is not None:
            logs.log("WARN", "COLLECTION_HELD", store=store_key, run_id=current.id)
            return Exit.HELD
        day = ((current.config_snapshot or {}).get("occurrence") or {}).get("day")
        _recover(s, current)
        s.commit()
        run_id = current.id
        provider = run_provider(current)
    check_key(provider)
    logs.log(
        "INFO", "OCCURRENCE_CONTINUED", store=store_key, occurrence=day, run_id=run_id, continuation=True
    )
    return await drive(ctx, store_key, run_id, trigger="schedule", resume=True)


def after_run(ctx: Context, store_key: str, run_id: str) -> Exit:
    """Hold the store after a refusal or a failed source check; keep a stopped run's records as a partial
    export; publish a complete validated run."""
    pipe = ctx.pipeline(store_key)
    with ctx.factory() as s:
        run = s.get(Run, run_id)
        assert run is not None
        if run.stop_code in {c.value for c in SUSPENDS_SCHEDULE} and get_hold(s, store_key) is None:
            set_hold(s, store_key, run)
        s.commit()
        if (
            run.status == "rejected"
            and s.scalar(select(ExportRow.id).where(ExportRow.run_id == run_id, ExportRow.kind == "manifest"))
            is None
        ):
            try:
                try:
                    ex = pipe.write_run_exports(s, run)
                except ImmutableWriteError:
                    # An export task stopped half-way left files behind: this export goes next to them.
                    stamp = ctx.clock().strftime("%Y%m%dT%H%M%SZ")
                    ex = pipe.write_run_exports(s, run, prefix=f"{pipe.prefix(run_id)}/exports-{stamp}")
                event(
                    s,
                    run_id,
                    "INFO",
                    "PARTIAL_EXPORT",
                    "the stopped run's records are kept as a partial export (never published)",
                    {"manifest": ex.manifest.key, "records": ex.manifest_body["record_count"]},
                )
                s.commit()
            except Exception as exc:  # the run's outcome stands; its records stay in the database
                s.rollback()
                logs.log(
                    "WARN",
                    "PARTIAL_EXPORT_FAILED",
                    run_id=run_id,
                    error=type(exc).__name__,
                    message=str(exc)[:300],
                )
            run = s.get(Run, run_id)
            assert run is not None
        label = pipe.dataset_label(run)
        status = run.status
    if status == "validated" and label == "complete" and ctx.config.collector.publish.auto:
        try:
            pub = publish_run(
                ctx.factory,
                ctx.storage,
                run_id,
                "collector",
                warn_override_reason=ctx.config.collector.publish.accept_warnings_reason,
            )
            logs.log("INFO", "RUN_PUBLISHED", run_id=run_id, store=store_key, version=pub.version)
        except PublicationRefused as exc:
            logs.log("WARN", "PUBLICATION_REFUSED", run_id=run_id, store=store_key, message=str(exc))
    with ctx.factory() as s:
        run = s.get(Run, run_id)
        assert run is not None
        summary = run_summary(pipe, run)
        code = exit_for(s, run)
        summary["failed_checks"] = failed_gates(s, run.id)
    logs.log(
        "INFO" if code is Exit.OK else "WARN", "RUN_FINISHED", store=store_key, exit_code=int(code), **summary
    )
    return code


def _overrides(coll: StoreCollection, overrides: dict[str, Any]) -> StoreCollection:
    if not overrides:
        return coll
    data = coll.model_dump(mode="json")
    limits = dict(data["limits"])
    for key, value in overrides.items():
        if key in ("categories", "subcategories"):
            data[key] = value
        else:
            limits[key] = value
    data["limits"] = limits
    return StoreCollection.model_validate(data)


def _recover(s: Session, run: Run) -> None:
    """A run left active by an execution that ended (its worker no longer holds the store lock)."""
    if run.status in ("preflight", "running") and not worker_alive(s, run.store_id, run.id):
        run.stop_code = StopCode.SERVICE_RESTART.value
        run.stop_detail = "the execution that collected it ended without closing it"
        transition(s, run.id, "interrupted")
        event(s, run.id, "WARN", "RUN_RECOVERED", run.stop_detail)


async def start_run(ctx: Context, store_key: str, overrides: dict[str, Any], actor: str) -> Exit:
    """A manual run (an operator, or the small verification) of one store."""
    ctx.config.store(store_key)
    coll = _overrides(ctx.config.collection(store_key), overrides)
    with ctx.factory() as s:
        hold = get_hold(s, store_key)
    if hold is not None:
        raise CommandError(
            Exit.HELD, f"{store_key} is held: {hold['reason']} (release-hold first)", hold=hold
        )
    check_key(ctx.settings.acquisition.browser_provider.value)
    sync_config(ctx, actor)
    pipe = ctx.pipeline(store_key)
    # Narrowed on the command line (categories or listings) or bounded by a limit: a pilot, never published
    # as the store's dataset.
    pilot = coll.limits.bounded() or bool(overrides.get("categories") or overrides.get("subcategories"))
    with ctx.factory() as s:
        row = _store_row(s, store_key)
        current = control.open_run(s, row.id)
        if current is not None:
            _recover(s, current)
            s.commit()
            raise CommandError(
                Exit.BUSY,
                f"{store_key} has an unfinished run {current.id} ({current.status}): resume or finalize it",
                run_id=current.id,
            )
        try:
            run_id = control.create_run(
                s,
                pipe=pipe,
                store=ctx.config.store(store_key),
                cfg=coll,
                trigger="manual",
                started_by=actor,
                pilot=pilot,
                overrides=overrides,
                seed=ctx.config.seed,
                base=ctx.site_base,
            )
        except control.StartRefused as exc:
            raise CommandError(Exit.CONFIG, str(exc)) from None
        s.commit()
    logs.log(
        "INFO",
        "RUN_CREATED",
        run_id=run_id,
        store=store_key,
        pilot=pilot,
        overrides=overrides,
    )
    return await drive(ctx, store_key, run_id, trigger="manual", resume=False)


def due_occurrence(coll: StoreCollection, now: datetime) -> Occurrence | None:
    """Today's occurrence when ``now`` is its start time (a few minutes early, or up to the tolerance
    late)."""
    tz = ZoneInfo(coll.timezone)
    occ = occurrence_on(coll.schedule, local_day(now + EARLY_START, tz), tz)
    if occ is None:
        return None
    if occ.start - EARLY_START <= now <= occ.start + timedelta(minutes=coll.start_tolerance_minutes):
        return occ
    return None


async def scheduled_run(ctx: Context, store_key: str, now: datetime | None = None) -> Exit:
    """One scheduled execution for a store (Azure's cron fired)."""
    now = now or ctx.clock()
    ctx.config.store(store_key)
    coll = ctx.config.collection(store_key)
    tz = ZoneInfo(coll.timezone)
    if not coll.schedule.enabled:
        logs.log("INFO", "SCHEDULE_OFF", store=store_key)
        return Exit.OK
    occ = due_occurrence(coll, now)
    if occ is None:
        continued = await continue_scheduled(ctx, store_key, coll, now)
        if continued is not None:
            return continued
        nxt = next_occurrence(coll.schedule, now, tz)
        logs.log(
            "INFO",
            "NOT_DUE",
            store=store_key,
            local_now=now.astimezone(tz).isoformat(),
            next_local_start=nxt.start.isoformat() if nxt else None,
        )
        return Exit.OK
    day = occ.day.isoformat()
    with ctx.factory() as s:
        hold = get_hold(s, store_key)
    if hold is not None:
        logs.log("WARN", "COLLECTION_HELD", store=store_key, occurrence=day, hold=hold)
        return Exit.HELD
    check_key(ctx.settings.acquisition.browser_provider.value)
    sync_config(ctx, "schedule")
    pipe = ctx.pipeline(store_key)
    with ctx.factory() as s:
        row = _store_row(s, store_key)
        mine = s.scalars(
            select(Run).where(
                Run.store_id == row.id,
                Run.mode == "LIVE",
                Run.trigger == "schedule",
                Run.config_snapshot["occurrence"]["day"].astext == day,
            )
        ).first()
        if mine is not None:
            if mine.status in FINISHED_STATES:
                logs.log(
                    "INFO", "OCCURRENCE_DONE", store=store_key, occurrence=day, run=run_summary(pipe, mine)
                )
                return exit_for(s, mine)
            if mine.status in control.ACTIVE and worker_alive(s, row.id, mine.id):
                logs.log("WARN", "STORE_BUSY", store=store_key, run_id=mine.id)
                return Exit.BUSY
            _recover(s, mine)
            s.commit()
            logs.log("INFO", "OCCURRENCE_CONTINUED", store=store_key, occurrence=day, run_id=mine.id)
            run_id = mine.id
        else:
            current = control.open_run(s, row.id)
            if (
                current is not None
                and current.status in control.ACTIVE
                and worker_alive(s, row.id, current.id)
            ):
                logs.log("WARN", "STORE_BUSY", store=store_key, run_id=current.id)
                return Exit.BUSY
            if current is not None and current.trigger != "schedule":
                logs.log(
                    "WARN",
                    "MANUAL_RUN_OPEN",
                    store=store_key,
                    run_id=current.id,
                    message="a manual run is unfinished: resume or finalize it; the occurrence is skipped",
                )
                return Exit.BUSY
            superseded = None
            if current is not None:
                _recover(s, current)
                current.stop_code = StopCode.SUPERSEDED.value
                current.stop_detail = (
                    f"the scheduled run of {day} started; it reads first the listings this run did not "
                    "finish (backlog)"
                )
                control.prepare_finish(s, current)
                superseded = current.id
            s.commit()
            if superseded is not None:
                logs.log("INFO", "RUN_SUPERSEDED", store=store_key, run_id=superseded, occurrence=day)
                await drive(ctx, store_key, superseded, trigger="finish", resume=True)
            with ctx.factory() as s2:
                try:
                    run_id = control.create_run(
                        s2,
                        pipe=pipe,
                        store=ctx.config.store(store_key),
                        cfg=coll,
                        trigger="schedule",
                        started_by="schedule",
                        pilot=coll.limits.bounded(),
                        occurrence=occ,
                        seed=ctx.config.seed,
                        base=ctx.site_base,
                    )
                except control.StartRefused as exc:
                    raise CommandError(Exit.CONFIG, str(exc)) from None
                s2.commit()
                created = s2.get(Run, run_id)
                order = (created.config_snapshot or {}).get("plan", {}).get("order", {}) if created else {}
            logs.log(
                "INFO",
                "RUN_CREATED",
                run_id=run_id,
                store=store_key,
                occurrence=day,
                superseded=superseded,
                order=order.get("policy"),
                backlog=len(order.get("backlog") or []),
            )
    return await drive(ctx, store_key, run_id, trigger="schedule", resume=mine is not None)


def _find_run(ctx: Context, run_id: str | None, store_key: str | None) -> tuple[str, str]:
    """(run id, store key) of the named run, or of the store's unfinished run."""
    with ctx.factory() as s:
        if run_id:
            run = s.get(Run, run_id)
            if run is None:
                raise CommandError(Exit.CONFIG, f"unknown run {run_id}")
            store = s.get(Store, run.store_id)
            assert store is not None
            return run.id, store.key
        if not store_key:
            raise CommandError(Exit.CONFIG, "name a run (--run) or a store (--store)")
        row = _store_row(s, store_key)
        current = control.open_run(s, row.id)
        if current is None:
            raise CommandError(Exit.CONFIG, f"{store_key} has no unfinished run")
        return current.id, store_key


async def resume_run(ctx: Context, run_id: str | None, store_key: str | None) -> Exit:
    rid, key = _find_run(ctx, run_id, store_key)
    with ctx.factory() as s:
        hold = get_hold(s, key)
        run = s.get(Run, rid)
        assert run is not None
        _recover(s, run)
        s.commit()
        provider = run_provider(run)
        if run.status != "interrupted":
            raise CommandError(
                Exit.BUSY if run.status in control.ACTIVE else Exit.CONFIG, f"run {rid} is {run.status}"
            )
    if hold is not None:
        raise CommandError(Exit.HELD, f"{key} is held: {hold['reason']} (release-hold first)", hold=hold)
    check_key(provider)
    return await drive(ctx, key, rid, trigger="resume", resume=True)


async def finalize_run(ctx: Context, run_id: str | None, store_key: str | None) -> Exit:
    """Check and export what an unfinished run collected, without collecting more (no provider request)."""
    rid, key = _find_run(ctx, run_id, store_key)
    with ctx.factory() as s:
        run = s.get(Run, rid)
        assert run is not None
        _recover(s, run)
        if run.status in FINISHED_STATES:
            raise CommandError(Exit.CONFIG, f"run {rid} has already finished ({run.status})")
        if run.status in control.ACTIVE and run.status != "queued" and worker_alive(s, run.store_id, rid):
            raise CommandError(Exit.BUSY, f"run {rid} is being collected: use stop")
        if run.stop_code is None:
            run.stop_code, run.stop_detail = StopCode.OPERATOR_STOP.value, "finalized by an operator"
        control.prepare_finish(s, run)
        s.commit()
    return await drive(ctx, key, rid, trigger="finish", resume=True)


def stop_run(
    ctx: Context, run_id: str | None, store_key: str | None, reason: str, actor: str
) -> dict[str, Any]:
    rid, _key = _find_run(ctx, run_id, store_key)
    with ctx.factory() as s:
        run = s.get(Run, rid)
        assert run is not None
        try:
            control.request_stop(s, run, actor, reason or "stop requested")
        except control.StartRefused as exc:
            raise CommandError(Exit.CONFIG, str(exc)) from None
        alive = worker_alive(s, run.store_id, rid)
        s.commit()
    return {
        "run_id": rid,
        "stop_requested": True,
        "worker_running": alive,
        "next": "the running execution stops at its next checkpoint and finalizes"
        if alive
        else "no execution is collecting it: run 'marianos-collector finalize'",
    }


def publish(ctx: Context, run_id: str, reason: str | None, actor: str) -> dict[str, Any]:
    with ctx.factory() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise CommandError(Exit.CONFIG, f"unknown run {run_id}")
        store = s.get(Store, run.store_id)
        assert store is not None
        label = ctx.pipeline(store.key).dataset_label(run)
    if label != "complete":
        raise CommandError(
            Exit.REJECTED, f"run {run_id} is a {label} dataset: only complete runs are published"
        )
    try:
        pub = publish_run(ctx.factory, ctx.storage, run_id, actor, warn_override_reason=reason)
    except PublicationRefused as exc:
        raise CommandError(Exit.REJECTED, str(exc)) from None
    return {"run_id": run_id, "publication_id": pub.publication_id, "version": pub.version}


def rollback(ctx: Context, store_key: str, reason: str, actor: str) -> dict[str, Any]:
    """The store's published dataset back to the publication the current one replaced (audited)."""
    with ctx.factory() as s:
        store = s.scalar(select(Store).where(Store.key == store_key))
        if store is None:
            raise CommandError(Exit.CONFIG, f"unknown store {store_key}")
        store_id = store.id
    try:
        pub = rollback_publication(ctx.factory, ctx.storage, store_id, actor, reason)
    except PublicationRefused as exc:
        raise CommandError(Exit.REJECTED, str(exc)) from None
    return {
        "store": store_key,
        "publication_id": pub.publication_id,
        "version": pub.version,
        "rolled_back_from": pub.previous_publication_id,
    }


# -- status and exports ---------------------------------------------------------------------------


def status(ctx: Context, store_key: str | None, run_id: str | None, limit: int) -> dict[str, Any]:
    out: dict[str, Any] = {"stores": []}
    with ctx.factory() as s:
        if run_id:
            run = s.get(Run, run_id)
            if run is None:
                raise CommandError(Exit.CONFIG, f"unknown run {run_id}")
            store = s.get(Store, run.store_id)
            assert store is not None
            pipe = ctx.pipeline(store.key) if store.key in {x.key for x in ctx.config.stores.stores} else None
            summary = run_summary(pipe, run)
            summary["worker_running"] = worker_alive(s, run.store_id, run.id)
            exports = {
                e.kind: s.get(Artifact, e.artifact_id).key  # type: ignore[union-attr]
                for e in s.scalars(select(ExportRow).where(ExportRow.run_id == run.id))
            }
            return {"run": {**summary, "store": store.key, "exports": exports}}
        for st in ctx.config.stores.stores:
            if store_key and st.key != store_key:
                continue
            row = s.scalar(select(Store).where(Store.key == st.key))
            entry: dict[str, Any] = {
                "store": st.key,
                "in_database": row is not None,
                "hold": get_hold(s, st.key),
            }
            if row is not None:
                pipe = ctx.pipeline(st.key)
                runs = list(
                    s.scalars(
                        select(Run).where(Run.store_id == row.id).order_by(Run.created_at.desc()).limit(limit)
                    )
                )
                entry["runs"] = [
                    {
                        **run_summary(pipe, r),
                        "worker_running": worker_alive(s, row.id, r.id)
                        if r.status in control.ACTIVE
                        else False,
                    }
                    for r in runs
                ]
                pointer = s.get(PublicationPointer, row.id)
                if pointer is not None:
                    pub = s.get(Publication, pointer.publication_id)
                    assert pub is not None
                    entry["published"] = {
                        "run_id": pub.run_id,
                        "version": pointer.version,
                        "published_at": iso(pub.published_at),
                        "latest": latest_key(st.key),
                    }
                else:
                    entry["published"] = None
            out["stores"].append(entry)
        try:
            if ctx.settings.acquisition.browser_provider is BrowserProvider.OXYLABS:
                out["provider"] = oxylabs_ledger(s)
            else:
                account = scrapfly_account.status(s)
                out["provider"] = {"provider": "scrapfly", **account}
        except Exception as exc:  # the status of the runs is still useful
            out["provider"] = {"error": type(exc).__name__}
    return out


def _published_run(ctx: Context, store_key: str) -> str:
    with ctx.factory() as s:
        row = _store_row(s, store_key)
        pointer = s.get(PublicationPointer, row.id)
        if pointer is None:
            raise CommandError(Exit.CONFIG, f"{store_key} has no published dataset yet")
        pub = s.get(Publication, pointer.publication_id)
        assert pub is not None
        return pub.run_id


def export(ctx: Context, run_id: str | None, store_key: str | None, out_dir: Path) -> dict[str, Any]:
    """Copy a run's export files (by default the store's published dataset) to a local folder, after
    verifying every file against its manifest."""
    rid = run_id or _published_run(ctx, store_key or "")
    with ctx.factory() as s:
        run = s.get(Run, rid)
        if run is None:
            raise CommandError(Exit.CONFIG, f"unknown run {rid}")
        manifest = s.scalar(
            select(Artifact)
            .join(ExportRow, ExportRow.artifact_id == Artifact.id)
            .where(ExportRow.run_id == rid, ExportRow.kind == "manifest")
        )
        if manifest is None:
            raise CommandError(Exit.CONFIG, f"run {rid} has no exports ({run.status})")
        mkey, msha = manifest.key, manifest.sha256
    problems = verify_manifest(ctx.storage, mkey, msha)
    if problems:
        raise CommandError(Exit.REJECTED, "the exports do not verify: " + "; ".join(problems))
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = mkey.rsplit("/", 1)[0]
    written = []
    body = json.loads(ctx.storage.get_bytes(mkey))
    for name in (*manifest_files(body), "manifest.json"):
        data = ctx.storage.get_bytes(f"{prefix}/{name}")
        (out_dir / name).write_bytes(data)
        written.append(name)
    return {"run_id": rid, "out": str(out_dir), "files": written, "verified": True}


def validate_export(
    ctx: Context | None, products: Path | None, run_id: str | None
) -> tuple[Exit, dict[str, Any]]:
    """The 22-field contract of a products file; for a run, also its manifest and an independent check of
    every record against the run's stored pages (offline: no provider request)."""
    if run_id is None:
        if products is None:
            raise CommandError(Exit.CONFIG, "name a products file (--file) or a run (--run)")
        report = contract.check(products)
        return (Exit.OK if report["passed"] else Exit.REJECTED), {"contract": report}
    assert ctx is not None
    with ctx.factory() as s:
        run = s.get(Run, run_id)
        if run is None:
            raise CommandError(Exit.CONFIG, f"unknown run {run_id}")
        store = s.get(Store, run.store_id)
        assert store is not None
        manifest = s.scalar(
            select(Artifact)
            .join(ExportRow, ExportRow.artifact_id == Artifact.id)
            .where(ExportRow.run_id == run_id, ExportRow.kind == "manifest")
        )
        rows = list(s.scalars(select(RecordRow).where(RecordRow.run_id == run_id)))
        statuses = Counter(r.status for r in rows)
        # A carried-forward record is checked against the product responses of the run that observed it
        # (its prices are from that day); every other record against this run's own responses.
        carried_from = {
            r.upc: str(((r.provenance or {}).get("historical") or {}).get("run_id") or "")
            for r in rows
            if r.status == "historical"
        }
        # The fresh file's records (release 1.4.0): this run's own ``valid`` records, nothing else.
        valid_keys = {r.upc for r in rows if r.status == "valid"}
        # Records whose displayed price differs from the product's own data, recorded as such by the collector
        # (both values in the supporting log): a recorded conflict, not a parser mismatch (release 1.4.0).
        recorded_conflicts = {
            r.upc
            for r in rows
            if r.status == "price_conflict" or "PRICE_DOM_JSON_MISMATCH" in (r.flags or [])
        }
        # Records whose displayed price the product's own data states for no store, recorded as such by the
        # collector and never valid (1.8.0rc2): their missing store is recorded, any other difference is not.
        recorded_store_not_stated = {
            r.upc for r in rows if r.status != "valid" and "PRICE_STORE_NOT_STATED" in (r.flags or [])
        }
        responses = {
            rid: list(
                s.scalars(
                    select(Artifact.key)
                    .join(CapturedResponse, CapturedResponse.artifact_id == Artifact.id)
                    .where(CapturedResponse.run_id == rid, CapturedResponse.kind == "products_v2")
                )
            )
            for rid in {run_id, *(x for x in carried_from.values() if x)}
        }
        # The listing pages each run stored: their embedded product data is a second source (1.2.1).
        pages = {
            rid: list(
                s.scalars(
                    select(Artifact.key)
                    .join(PageFetch, PageFetch.dom_artifact_id == Artifact.id)
                    .where(
                        PageFetch.run_id == rid,
                        PageFetch.purpose.in_(("listing", "listing_after_selection", "load_more")),
                    )
                )
            )
            for rid in responses
        }
        location_id = store.location_id
    if manifest is None:
        raise CommandError(Exit.CONFIG, f"run {run_id} has no exports")
    problems = verify_manifest(ctx.storage, manifest.key, manifest.sha256)
    prefix = manifest.key.rsplit("/", 1)[0]
    listed = manifest_files(json.loads(ctx.storage.get_bytes(manifest.key)))
    with tempfile.TemporaryDirectory(prefix="marianos-validate-") as tmp:
        root = Path(tmp)
        products_path = root / "products.json"
        products_path.write_bytes(ctx.storage.get_bytes(f"{prefix}/products.json"))
        report = contract.check(products_path)
        records = json.loads(products_path.read_text("utf-8"))
        fresh: dict[str, Any] | None = None
        if "products_fresh.json" in listed:
            fresh_path = root / "products_fresh.json"
            fresh_path.write_bytes(ctx.storage.get_bytes(f"{prefix}/products_fresh.json"))
            fresh_records = json.loads(fresh_path.read_text("utf-8"))
            fresh_keys = [str(r.get("upc")) for r in fresh_records]
            carried_keys = {str(r.get("upc")) for r in records} & set(carried_from)
            fresh = {
                "contract": contract.check(fresh_path),
                "records": len(fresh_records),
                # The fresh file is the run's own valid records, nothing else (release 1.4.0): no carried,
                # unpriced, conflicting or incomplete record.
                "subset_of_products": set(fresh_keys) <= {str(r.get("upc")) for r in records},
                "carried_in_products": len(carried_keys),
                "carried_match_supporting_log": carried_keys == set(carried_from)
                and not (set(fresh_keys) & set(carried_from)),
                "fresh_match_valid_records": set(fresh_keys) == valid_keys
                and len(fresh_keys) == len(valid_keys),
            }
        summary = {
            "records": 0,
            "verified": 0,
            "mismatch": 0,
            "unverified": 0,
            "recorded_conflict": 0,
            "recorded_store_not_stated": 0,
        }
        mismatched: Counter[str] = Counter()
        evidence: Counter[str] = Counter()
        read, pages_read, indexed = 0, 0, 0
        by_run: dict[str, dict[str, int]] = {}
        for rid, keys in sorted(responses.items()):
            bodies = []
            for key in keys:
                data = ctx.storage.get_bytes(key)
                bodies.append(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
            html = []
            for key in pages.get(rid, []):
                data = ctx.storage.get_bytes(key)
                html.append(
                    (gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data).decode("utf-8", "replace")
                )
            mine = [r for r in records if (carried_from.get(str(r.get("upc"))) or run_id) == rid]
            index = source_check.index(bodies, html)
            out = source_check.check_records(mine, index, location_id)
            known = sum(
                1 for x in out["results"] if x["result"] == "mismatch" and str(x["upc"]) in recorded_conflicts
            )
            unattributed = sum(
                1
                for x in out["results"]
                if x["result"] == "mismatch"
                and str(x["upc"]) in recorded_store_not_stated
                and str(x["upc"]) not in recorded_conflicts
                and set(x["mismatched_fields"]) == {"store"}
            )
            out["summary"]["mismatch"] -= known + unattributed
            out["summary"]["recorded_conflict"] = known
            out["summary"]["recorded_store_not_stated"] = unattributed
            read, pages_read, indexed = read + len(bodies), pages_read + len(html), indexed + len(index)
            for k, v in out["summary"].items():
                summary[k] += v
            mismatched.update(out["mismatched_fields"])
            evidence.update(out["by_evidence"])
            by_run[rid] = out["summary"]
    # A record the page requested no product data for is reported "unverified", not a failure: the store
    # of every page was checked by the collector itself.
    ok = (
        not problems
        and report["passed"]
        and summary["mismatch"] == 0
        and (
            fresh is None
            or (
                fresh["contract"]["passed"]
                and fresh["subset_of_products"]
                and fresh["carried_match_supporting_log"]
                and fresh["fresh_match_valid_records"]
            )
        )
    )
    return (Exit.OK if ok else Exit.REJECTED), {
        "run_id": run_id,
        "manifest": {"key": manifest.key, "problems": problems, "files": listed},
        "contract": report,
        "fresh_file": fresh,
        "source_check": {
            "responses_read": read,
            "pages_read": pages_read,
            "products_in_sources": indexed,
            "summary": summary,
            # result:evidence, e.g. verified:product_response, verified:embedded_page_data
            "by_evidence": dict(evidence),
            "mismatched_fields": dict(mismatched),
            # fresh records against this run's responses; carried-forward ones against their own run's
            "by_run": by_run,
        },
        "records_by_status": dict(statuses),
    }


def oxylabs_ledger(s: Session) -> dict[str, Any]:
    left, info = oxylabs.room(s)
    return {
        "provider": "oxylabs",
        "service": "Oxylabs Web API (webapi.oxylabs.io, Bearer key)",
        "balance_api": "none: Oxylabs documents no balance or usage API for this key; the ledger counts "
        "every submission (reserved before it is sent)",
        "room_submissions": left,
        **info,
        "all_time": oxylabs.usage_since(s, None),
    }


def set_ceiling(
    ctx: Context, provider: str, submissions: int, usd: float, reason: str, actor: str
) -> dict[str, Any]:
    """The operator's spending ceiling for a provider without a balance API (Oxylabs Web API): submissions
    and US dollars counted from now. Replaces the previous ceiling (kept in the audit log)."""
    if provider != BrowserProvider.OXYLABS.value:
        raise CommandError(
            Exit.CONFIG, "set-ceiling applies to oxylabs (Scrapfly's balance is read from its account API)"
        )
    if submissions < 0 or usd < 0:
        raise CommandError(Exit.CONFIG, "a ceiling is not negative")
    with ctx.factory() as s:
        before = oxylabs.ceiling(s)
        value = oxylabs.set_ceiling(s, submissions=submissions, usd=usd, actor=actor, reason=reason)
        s.add(
            AuditLog(
                actor=actor,
                action="set_ceiling",
                target=f"provider:{provider}",
                reason=reason[:2000],
                data={"before": before, "after": value},
            )
        )
        s.commit()
        out = oxylabs_ledger(s)
    logs.log("INFO", "CEILING_SET", provider=provider, submissions=submissions, usd=usd)
    return out


def provider_balance(ctx: Context, actor: str) -> tuple[Exit, dict[str, Any]]:
    """The account's balance read from Scrapfly's Account API (free; no browser is opened); for the Oxylabs
    Web API, which has no balance API, the operator's ceiling and the ledger."""
    provider = ctx.settings.acquisition.browser_provider.value
    if provider == BrowserProvider.OXYLABS.value:
        check_key(provider)
        with ctx.factory() as s:
            out = oxylabs_ledger(s)
        return (Exit.OK if (out["room_submissions"] or 0) > 0 else Exit.CREDITS), {
            "key": oxylabs_key_info(),
            **out,
        }
    check_key()
    with ctx.factory() as s:
        out = scrapfly_account.check_account(s, ctx.settings.acquisition.scrapfly, actor)
        s.commit()
    connection = out.get("connection")
    code = Exit.OK
    if connection in ("invalid_key", "suspended"):
        code = Exit.CREDENTIALS
    elif connection == "exhausted":
        code = Exit.CREDITS
    elif connection != "ok":
        code = Exit.UNEXPECTED
    return code, {"provider": "scrapfly", "key": scrapfly_account.key_info(), **out}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps_bytes(data))
