"""Runner: crash mid-listing + resume, cancellation, challenge abort, retries, circuit breaker.

Pages are SYNTHETIC in-memory lists; no browser and no retailer traffic.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.core.schema import build_record
from marianos_headless.core.settings import Settings
from marianos_headless.db import queue
from marianos_headless.db.models import CategorySource, Event, MembershipRow, Run, Task
from marianos_headless.db.observations import insert_memberships
from marianos_headless.publishing.exports import record_sha256
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.retry import FailureKind, TaskFailure
from marianos_headless.worker.runner import CancelledByOperator, TaskContext, Worker
from marianos_headless.worker.runs import request_cancel
from tests.integration.helpers import new_run, seed

pytestmark = pytest.mark.postgres

PAGES = {
    "26003": [
        ["0000000000001", "0000000000002", "0000000000003"],
        ["0000000000004", "0000000000005"],
        ["0000000000006"],
    ],
    "26002": [["0000000000007", "0000000000002"]],  # 2 is cross-listed
}


class SimulatedCrash(BaseException):
    """Stands in for the worker process being killed (not caught by the runner)."""


def listing_handler(crash_at: tuple[str, int] | None = None, cancel_after_page: int | None = None) -> Any:
    async def handle(ctx: TaskContext) -> dict[str, Any]:
        tid = ctx.lease.taxonomy_id or ""
        page = int(ctx.cursor.get("next_page", 0))
        while page < len(PAGES[tid]):
            if ctx.cancelled():
                raise CancelledByOperator()
            with ctx.session() as s:
                insert_memberships(
                    s,
                    [
                        {
                            "run_id": ctx.run_id,
                            "mode": "LIVE",
                            "upc": upc,
                            "category_source_id": ctx.lease.category_source_id,
                            "taxonomy_id": tid,
                            "coupon_id": None,
                            "page_offset": page * 48,
                            "position": i,
                            "via": "organic",
                        }
                        for i, upc in enumerate(PAGES[tid][page])
                    ],
                )
                s.commit()
            if crash_at == (tid, page):
                raise SimulatedCrash()  # after the page's writes, before its checkpoint
            page += 1
            ctx.checkpoint({"next_page": page})
            if cancel_after_page is not None and page == cancel_after_page:
                with ctx.session() as s:
                    request_cancel(s, ctx.run_id)
                    s.commit()
        return {"next_page": page, "done": True}

    return handle


def start(factory: sessionmaker[Session], store: Any) -> str:
    run = new_run(factory, store, status="running")
    with factory() as s:
        produce = s.scalar(select(CategorySource).where(CategorySource.category_name == "Batteries"))
        assert produce is not None
        for tid in PAGES:
            queue.enqueue(
                s,
                run.id,
                "listing_node",
                f"{run.id}/listing/{tid}",
                taxonomy_id=tid,
                category_source_id=produce.id,
            )
        s.commit()
    return run.id


def membership_keys(factory: sessionmaker[Session], run_id: str) -> list[tuple[str, str | None, int]]:
    with factory() as s:
        rows = s.scalars(select(MembershipRow).where(MembershipRow.run_id == run_id)).all()
        return sorted((m.upc, m.taxonomy_id, m.page_offset) for m in rows)


def record_hashes(keys: list[tuple[str, str | None, int]]) -> list[str]:
    return sorted(
        record_sha256(build_record({"upc": u, "category": "Batteries"})) for u in {k[0] for k in keys}
    )


def test_crash_mid_listing_then_resume_matches_clean_run(migrated_engine: Engine, tmp_path: Path) -> None:
    factory, store = seed(migrated_engine)
    storage = LocalStorageAdapter(tmp_path)
    clean = start(factory, store)
    res = asyncio.run(
        Worker(factory, clean, "w-clean", {"listing_node": listing_handler()}, Settings(), storage).run()
    )
    assert res.outcome == "idle" and res.states == {"succeeded": 2}

    crashed = start(factory, store)
    w1 = Worker(
        factory,
        crashed,
        "w1",
        {"listing_node": listing_handler(crash_at=("26003", 1))},
        Settings(),
        storage,
        lease_s=1,
    )
    with pytest.raises(SimulatedCrash):
        asyncio.run(w1.run())
    with factory() as s:
        t = s.scalar(select(Task).where(Task.run_id == crashed, Task.taxonomy_id == "26003"))
        assert t is not None and t.state == "running" and t.cursor == {"next_page": 1}
    time.sleep(1.2)  # the dead worker's lease expires
    w2 = Worker(factory, crashed, "w2", {"listing_node": listing_handler()}, Settings(), storage)
    res2 = asyncio.run(w2.run())
    assert res2.outcome == "idle" and res2.states == {"succeeded": 2}
    assert membership_keys(factory, crashed) == membership_keys(factory, clean)  # page 1 re-run, no doubles
    assert record_hashes(membership_keys(factory, crashed)) == record_hashes(membership_keys(factory, clean))
    with factory() as s:
        codes = list(s.scalars(select(Event.code).where(Event.run_id == crashed)))
        assert "TASK_LEASE_RECLAIMED" in codes


def test_cooperative_cancel(migrated_engine: Engine, tmp_path: Path) -> None:
    factory, store = seed(migrated_engine)
    run_id = start(factory, store)
    w = Worker(
        factory,
        run_id,
        "w",
        {"listing_node": listing_handler(cancel_after_page=1)},
        Settings(),
        LocalStorageAdapter(tmp_path),
    )
    res = asyncio.run(w.run())
    assert res.outcome == "cancelled"
    with factory() as s:
        assert s.get(Run, run_id).status == "cancelled"  # type: ignore[union-attr]
        t = s.scalar(select(Task).where(Task.run_id == run_id, Task.taxonomy_id == "26003"))
        assert t is not None and t.cursor == {"next_page": 1}  # the checkpoint survived


def test_challenge_blocks_task_and_aborts_run(migrated_engine: Engine, tmp_path: Path) -> None:
    factory, store = seed(migrated_engine)
    run_id = start(factory, store)

    async def blocked(ctx: TaskContext) -> dict[str, Any]:
        raise TaskFailure(FailureKind.CHALLENGE, "HTTP 403 Access Denied")

    res = asyncio.run(
        Worker(
            factory, run_id, "w", {"listing_node": blocked}, Settings(), LocalStorageAdapter(tmp_path)
        ).run()
    )
    assert res.outcome == "aborted"
    assert res.states == {"blocked": 1, "skipped": 1}  # never retried, and nothing else attempted


def test_transient_failure_retries_with_backoff(migrated_engine: Engine, tmp_path: Path) -> None:
    factory, store = seed(migrated_engine)
    run_id = start(factory, store)
    calls = {"n": 0}

    async def flaky(ctx: TaskContext) -> dict[str, Any]:
        calls["n"] += 1
        if ctx.lease.taxonomy_id == "26003" and ctx.lease.attempts == 1:
            raise TaskFailure(FailureKind.TRANSIENT, "HTTP 503")
        return {"ok": True}

    w = Worker(factory, run_id, "w", {"listing_node": flaky}, Settings(), LocalStorageAdapter(tmp_path))
    res = asyncio.run(w.run())
    assert res.outcome == "waiting" and res.states == {"retry_wait": 1, "succeeded": 1}
    with factory() as s:
        t = s.scalar(select(Task).where(Task.run_id == run_id, Task.state == "retry_wait"))
        assert t is not None and t.not_before is not None and "503" in (t.last_error or "")
        s.execute(update(Task).where(Task.id == t.id).values(not_before=None))
        s.commit()
    res = asyncio.run(w.run())
    assert res.outcome == "idle" and res.states == {"succeeded": 2}


def test_unexpected_handler_error_fails_the_task_not_the_worker(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    """A malformed response that a parser rejects with an ordinary exception is a permanent task
    failure (recorded, traceable), not a worker crash that leaves the run stalled forever."""
    import json

    factory, store = seed(migrated_engine)
    run_id = start(factory, store)

    async def parse(ctx: TaskContext) -> dict[str, Any]:
        if ctx.lease.taxonomy_id == "26003":
            json.loads('{"meta": ')  # truncated JSON body
        return {"ok": True}

    res = asyncio.run(
        Worker(factory, run_id, "w", {"listing_node": parse}, Settings(), LocalStorageAdapter(tmp_path)).run()
    )
    assert res.outcome == "idle" and res.states == {"failed": 1, "succeeded": 1}
    with factory() as s:
        t = s.scalar(select(Task).where(Task.run_id == run_id, Task.taxonomy_id == "26003"))
        assert t is not None and t.attempts == 1 and "JSONDecodeError" in (t.last_error or "")
        codes = list(s.scalars(select(Event.code).where(Event.run_id == run_id)))
        assert "TASK_FAILED" in codes


def test_circuit_breaker_fails_category(migrated_engine: Engine, tmp_path: Path) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store, status="running")
    with factory() as s:
        cat = s.scalar(select(CategorySource).where(CategorySource.category_name == "Produce"))
        assert cat is not None
        for i in range(7):
            queue.enqueue(
                s, run.id, "listing_node", f"n{i}", taxonomy_id=f"0611{i}", category_source_id=cat.id
            )
        s.commit()

    async def broken(ctx: TaskContext) -> dict[str, Any]:
        raise TaskFailure(FailureKind.PERMANENT, "unexpected response shape")

    res = asyncio.run(
        Worker(
            factory, run.id, "w", {"listing_node": broken}, Settings(), LocalStorageAdapter(tmp_path)
        ).run()
    )
    assert res.states == {"failed": 5, "skipped": 2}
    with factory() as s:
        assert "CATEGORY_FAILED" in list(s.scalars(select(Event.code).where(Event.run_id == run.id)))


def test_pause_then_resume_continues_from_checkpoint(migrated_engine: Engine, tmp_path: Path) -> None:
    from marianos_headless.worker.runs import request_pause, transition

    factory, store = seed(migrated_engine)
    clean = start(factory, store)
    asyncio.run(
        Worker(
            factory,
            clean,
            "w-clean",
            {"listing_node": listing_handler()},
            Settings(),
            LocalStorageAdapter(tmp_path),
        ).run()
    )

    run_id = start(factory, store)

    def pausing_handler() -> Any:
        inner = listing_handler()

        async def handle(ctx: TaskContext) -> dict[str, Any]:
            if ctx.lease.taxonomy_id == "26003" and ctx.cursor.get("next_page", 0) == 0:
                with ctx.session() as s:
                    request_pause(s, ctx.run_id)  # operator clicks "Pause" during the first page
                    s.commit()
            return await inner(ctx)

        return handle

    res = asyncio.run(
        Worker(
            factory,
            run_id,
            "w1",
            {"listing_node": pausing_handler()},
            Settings(),
            LocalStorageAdapter(tmp_path),
        ).run()
    )
    assert res.outcome == "paused"
    with factory() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.status == "interrupted" and run.pause_requested is False
        t = s.scalar(select(Task).where(Task.run_id == run_id, Task.taxonomy_id == "26003"))
        assert t is not None and t.state == "pending" and t.lease_owner is None  # handed back, cursor kept
        transition(s, run_id, "running")  # what execute() does on resume
        s.commit()
    res = asyncio.run(
        Worker(
            factory,
            run_id,
            "w2",
            {"listing_node": listing_handler()},
            Settings(),
            LocalStorageAdapter(tmp_path),
        ).run()
    )
    assert res.outcome == "idle" and res.states == {"succeeded": 2}
    assert membership_keys(factory, run_id) == membership_keys(factory, clean)
