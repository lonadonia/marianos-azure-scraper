"""Task runner (brief §11): lease → handle → checkpoint → succeed / retry / block.

Handlers are async and receive a :class:`TaskContext`. They call ``ctx.checkpoint(cursor)`` before
every next navigation, so a crash resumes from the last durable cursor. Writes must be idempotent
(observations and memberships use unique keys), so re-processing a page after a crash cannot double
counts. Cancellation is cooperative: handlers check ``ctx.cancelled()`` between navigations.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.core.settings import Settings
from marianos_headless.core.timeutil import utcnow
from marianos_headless.db import queue
from marianos_headless.db.models import Run, Task
from marianos_headless.storage.base import StorageAdapter
from marianos_headless.worker.retry import CircuitBreaker, FailureKind, TaskFailure, decide
from marianos_headless.worker.runs import clear_pause, event, transition

# 1.9.0 (T07): the event of a resumable stop names its cause: a limit, the operator, or a failure. A provider
# error that pauses the run is never reported as a limit.
LIMIT_CODES = frozenset(
    {
        "RUN_PRODUCT_LIMIT",
        "DAILY_PRODUCT_LIMIT",
        "RUN_DURATION_LIMIT",
        "SEGMENT_DURATION_LIMIT",
        "RUN_CREDIT_LIMIT",
        "DAILY_CREDIT_LIMIT",
        "CREDIT_RESERVE",
        "CREDITS_EXHAUSTED",
        "SPENDING_CEILING",
        "SCHEDULE_WINDOW_END",
    }
)
OPERATOR_CODES = frozenset({"OPERATOR_PAUSE", "OPERATOR_STOP"})


def pause_event(code: str) -> str:
    """The event code of a resumable stop."""
    if code in LIMIT_CODES:
        return "RUN_LIMIT_REACHED"
    if code in OPERATOR_CODES:
        return "RUN_PAUSE_REQUESTED"
    return "RUN_PAUSED_ON_FAILURE"


@dataclass(frozen=True)
class Timer:
    """The time the task queue goes by, and how a run waits for it (release 1.10.0): the real clock and
    ``asyncio.sleep`` unless a test supplies a clock of its own. One timer serves every queue decision of
    a run (leases, heartbeats, retry and re-ask times), so they never disagree."""

    now: Callable[[], datetime] = utcnow
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


class CancelledByOperator(Exception):
    pass


class TaskDeferred(Exception):
    """A handler sets its task aside until ``not_before`` (release 1.10.0, C1): the task keeps its
    checkpoint, the run's other tasks go first, and the task is leased again once the time has come. Not
    a failure and not a stop."""

    def __init__(self, not_before: datetime, detail: str):
        super().__init__(detail)
        self.not_before = not_before
        self.detail = detail


class RunStop(Exception):
    """A handler ends the run's current stretch of work: a limit was reached, the site refused, the
    store could not be verified, the provider failed. ``resumable`` stops hand the task back with its
    checkpoint and pause the run (``interrupted``); the others block the task and stop the run."""

    def __init__(self, code: str, detail: str, *, resumable: bool):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.resumable = resumable


@dataclass
class TaskContext:
    lease: queue.Lease
    run_id: str
    factory: sessionmaker[Session]
    settings: Settings
    storage: StorageAdapter
    lease_s: float
    data: dict[str, Any] = field(default_factory=dict)
    # 1.9.0 (M8): set by the worker when another lane stopped the run (a lane then stops at its next
    # check, as for an operator's pause, and hands its task back).
    halt: asyncio.Event | None = None
    # 1.10.0: the queue's clock (the worker's timer).
    clock: Callable[[], datetime] = utcnow

    @property
    def cursor(self) -> dict[str, Any]:
        return self.lease.cursor

    def checkpoint(self, cursor: Mapping[str, Any]) -> None:
        with self.factory() as s:
            now = self.clock()
            queue.checkpoint(s, self.lease, dict(cursor), now=now)
            queue.heartbeat(s, self.lease, lease_s=self.lease_s, now=now)
            s.commit()
        self.lease = queue.Lease(**{**self.lease.__dict__, "cursor": dict(cursor)})

    def heartbeat(self) -> None:
        with self.factory() as s:
            queue.heartbeat(s, self.lease, lease_s=self.lease_s, now=self.clock())
            s.commit()

    def cancelled(self) -> bool:
        """True when the operator asked to stop or pause (or another lane stopped the run): handlers check
        it between navigations."""
        if self.halt is not None and self.halt.is_set():
            return True
        with self.factory() as s:
            row = s.execute(
                select(Run.cancel_requested, Run.pause_requested).where(Run.id == self.run_id)
            ).one()
            return bool(row[0] or row[1])

    def session(self) -> Session:
        return self.factory()


Handler = Callable[[TaskContext], Awaitable[dict[str, Any] | None]]


@dataclass
class WorkerResult:
    outcome: str  # idle | waiting | cancelled | paused | aborted | max_tasks
    processed: int
    states: dict[str, int]


class Worker:
    def __init__(
        self,
        factory: sessionmaker[Session],
        run_id: str,
        owner: str,
        handlers: Mapping[str, Handler],
        settings: Settings,
        storage: StorageAdapter,
        *,
        lease_s: float = 120,
        lanes: int = 1,
        timer: Timer | None = None,
    ):
        self.factory = factory
        self.run_id = run_id
        self.owner = owner
        self.handlers = handlers
        self.settings = settings
        self.storage = storage
        self.lease_s = lease_s
        self.timer = timer or Timer()
        self.breaker = CircuitBreaker(settings.circuit_breaker)
        self._rate_limited: set[str] = set()
        # 1.9.0 (M8): listing tasks read at once (each with at most one provider request in flight). Other
        # tasks (preflight, assemble, validate) always run alone.
        self.lanes = max(1, int(lanes))
        self.halt = asyncio.Event()
        self.max_lanes_busy = 0

    def _cancel_requested(self) -> bool:
        with self.factory() as s:
            return bool(s.scalar(select(Run.cancel_requested).where(Run.id == self.run_id)))

    def _pause_requested(self) -> bool:
        with self.factory() as s:
            return bool(s.scalar(select(Run.pause_requested).where(Run.id == self.run_id)))

    def _skip_pending(self, reason: str) -> None:
        with self.factory() as s:
            s.execute(
                update(Task)
                .where(Task.run_id == self.run_id, Task.state.in_(("pending", "retry_wait")))
                .values(state="skipped", last_error=reason)
            )
            s.commit()

    async def run(self, *, max_tasks: int | None = None) -> WorkerResult:
        if self.lanes <= 1:
            return await self._run_serial(max_tasks)
        return await self._run_lanes(max_tasks)

    def _head(self, processed: int) -> WorkerResult | None:
        """The loop head: the operator's stop or pause (applied here, once no task is in hand)."""
        if self._cancel_requested():
            with self.factory() as s:
                transition(s, self.run_id, "cancelled")
                s.commit()
            return self._result("cancelled", processed)
        if self._pause_requested():
            with self.factory() as s:
                clear_pause(s, self.run_id)
                run = transition(s, self.run_id, "interrupted")
                reason = f"{run.stop_code}: {run.stop_detail or ''}".rstrip(": ") if run.stop_code else ""
                event(
                    s,
                    self.run_id,
                    "INFO",
                    "RUN_PAUSED",
                    "paused at a checkpoint; resume continues from it" + (f" ({reason})" if reason else ""),
                    {"stop_code": run.stop_code, "stop_detail": run.stop_detail},
                )
                s.commit()
            return self._result("paused", processed)
        return None

    def _lease(self, kinds: tuple[str, ...] | None = None) -> queue.Lease | None:
        with self.factory() as s:
            lease = queue.lease_next(
                s, self.run_id, self.owner, lease_s=self.lease_s, kinds=kinds, now=self.timer.now()
            )
            if lease is not None:
                queue.mark_running(s, lease)
                if lease.reclaimed:
                    event(
                        s,
                        self.run_id,
                        "WARN",
                        "TASK_LEASE_RECLAIMED",
                        lease.idem_key,
                        {"attempts": lease.attempts, "cursor": lease.cursor},
                    )
            s.commit()
        return lease

    async def _run_serial(self, max_tasks: int | None) -> WorkerResult:
        processed = 0
        while True:
            head = self._head(processed)
            if head is not None:
                return head
            if max_tasks is not None and processed >= max_tasks:
                return self._result("max_tasks", processed)
            lease = self._lease()
            if lease is None:
                with self.factory() as s:
                    done = queue.all_terminal(s, self.run_id)
                return self._result("idle" if done else "waiting", processed)
            processed += 1
            if await self._process(lease):
                return self._result("aborted", processed)

    async def _run_lanes(self, max_tasks: int | None) -> WorkerResult:
        """Up to ``lanes`` listing tasks at once (release 1.9.0, M8). A stage task (preflight, assemble,
        validate) is leased only when no lane is busy and runs alone; the queue's stage barrier keeps it
        from starting while a listing task is unfinished. A lane that stops the run (a limit, the provider,
        the site) halts the others at their next check: they hand their tasks back with their checkpoints."""
        processed = 0
        busy: dict[asyncio.Task[bool], queue.Lease] = {}
        aborted = False
        while True:
            for t in [t for t in busy if t.done()]:
                busy.pop(t)
                if t.result():
                    aborted = True
                    self.halt.set()
            stopping = aborted or self.halt.is_set() or self._cancel_requested() or self._pause_requested()
            if stopping or (max_tasks is not None and processed >= max_tasks):
                if stopping:
                    self.halt.set()
                if busy:
                    await asyncio.wait(busy)
                    continue
                if aborted:
                    self._skip_pending("run stopped by another lane")
                    return self._result("aborted", processed)
                head = self._head(processed)
                if head is not None:
                    return head
                if max_tasks is not None and processed >= max_tasks:
                    return self._result("max_tasks", processed)
                self.halt.clear()
                continue
            lease = self._lease(("listing_node",) if busy else None) if len(busy) < self.lanes else None
            if lease is not None:
                processed += 1
                task = asyncio.create_task(self._process(lease))
                busy[task] = lease
                self.max_lanes_busy = max(self.max_lanes_busy, len(busy))
                if lease.kind != "listing_node":
                    await asyncio.wait({task})  # a stage task runs alone
                continue
            if not busy:
                with self.factory() as s:
                    done = queue.all_terminal(s, self.run_id)
                return self._result("idle" if done else "waiting", processed)
            # A lane may free up, or a running listing may plan child listings: look again soon.
            await asyncio.wait(busy, timeout=2.0, return_when=asyncio.FIRST_COMPLETED)

    async def _process(self, lease: queue.Lease) -> bool:
        """One leased task: its handler, then succeed, retry, block or stop. True when the run is aborted."""
        category = lease.category_source_id or lease.kind
        if self.breaker.is_open(category):
            with self.factory() as s:
                queue.skip(s, lease, "category circuit open")
                s.commit()
            return False
        handler = self.handlers.get(lease.kind)
        if handler is None:
            with self.factory() as s:
                queue.fail(s, lease, f"no handler for {lease.kind}", retry_after_s=None)
                s.commit()
            return False
        ctx = TaskContext(
            lease,
            self.run_id,
            self.factory,
            self.settings,
            self.storage,
            self.lease_s,
            halt=self.halt,
            clock=self.timer.now,
        )
        try:
            final_cursor = await handler(ctx)
        except queue.LeaseLost:
            with self.factory() as s:
                event(s, self.run_id, "WARN", "TASK_LEASE_LOST", lease.idem_key)
                s.commit()
            return False
        except CancelledByOperator:
            # Hand the task back (cursor kept) so a resumed worker can lease it immediately;
            # the loop head then sees the cancel/pause flag and stops.
            with self.factory() as s:
                queue.release(s, ctx.lease)
                s.commit()
            return False
        except RunStop as stop:
            return self._stop(ctx, stop)
        except TaskDeferred as deferred:
            # Set aside, not failed: the task waits with its checkpoint and the run's other tasks go first.
            with self.factory() as s:
                queue.defer(s, ctx.lease, not_before=deferred.not_before)
                event(
                    s,
                    self.run_id,
                    "INFO",
                    "TASK_DEFERRED",
                    deferred.detail[:500],
                    {"task": ctx.lease.idem_key, "not_before": deferred.not_before.isoformat()},
                )
                s.commit()
            return False
        except TaskFailure as failure:
            return self._handle_failure(ctx, category, failure)
        except SQLAlchemyError:
            raise  # database trouble stops the worker; a resume continues from the checkpoints
        except Exception as exc:
            # A parser or contract error (e.g. a malformed response) is a permanent task failure,
            # recorded with its type, never a worker crash that leaves the run stalled.
            permanent = TaskFailure(FailureKind.PERMANENT, f"{type(exc).__name__}: {exc}"[:500])
            return self._handle_failure(ctx, category, permanent)
        with self.factory() as s:
            queue.succeed(s, ctx.lease, final_cursor if final_cursor is not None else ctx.lease.cursor)
            s.commit()
        self.breaker.record_success(category)
        return False

    def _stop(self, ctx: TaskContext, stop: RunStop) -> bool:
        """Record the stop on the run. A resumable stop hands the task back and pauses the run (the
        loop head applies it); any other stop blocks the task and skips the rest. True = aborted."""
        with self.factory() as s:
            run = s.get(Run, self.run_id, with_for_update=True)
            assert run is not None
            run.stop_code, run.stop_detail = stop.code, stop.detail[:2000]
            if stop.resumable:
                run.pause_requested = True
                queue.release(s, ctx.lease)
            else:
                queue.block(s, ctx.lease, str(stop)[:2000])
            event(
                s,
                self.run_id,
                "WARN",
                "RUN_STOPPED" if not stop.resumable else pause_event(stop.code),
                stop.detail[:500],
                {"stop_code": stop.code, "task": ctx.lease.idem_key, "resumable": stop.resumable},
            )
            s.commit()
        if not stop.resumable:
            self._skip_pending(f"run stopped: {stop.code}")
            return True
        return False

    def _handle_failure(self, ctx: TaskContext, category: str, failure: TaskFailure) -> bool:
        decision = decide(
            failure,
            ctx.lease.attempts,
            self.settings.retries,
            rate_limited_before=category in self._rate_limited,
        )
        if failure.kind is FailureKind.RATE_LIMITED:
            self._rate_limited.add(category)
        with self.factory() as s:
            if decision.action == "block":
                queue.block(s, ctx.lease, f"{failure.kind}: {failure}")
            else:
                queue.fail(
                    s,
                    ctx.lease,
                    f"{failure.kind}: {failure}",
                    retry_after_s=decision.delay_s if decision.action == "retry" else None,
                    now=self.timer.now(),
                )
            if failure.kind is FailureKind.CHALLENGE:
                code = "TASK_BLOCKED"
            elif failure.kind is FailureKind.RATE_LIMITED:
                code = "RATE_LIMITED"
            else:
                code = "TASK_RETRY" if decision.action == "retry" else "TASK_FAILED"
            event(
                s,
                self.run_id,
                "WARN",
                code,
                str(failure),
                {"task": ctx.lease.idem_key, "decision": decision.action, "delay_s": decision.delay_s},
            )
            s.commit()
        if failure.kind is FailureKind.CHALLENGE and self.breaker.record_challenge():
            self._skip_pending("run aborted: challenge detected")
            return True
        if decision.action != "retry" and self.breaker.record_failure(category):
            with self.factory() as s:
                event(s, self.run_id, "WARN", "CATEGORY_FAILED", category, {"reason": "circuit breaker"})
                s.commit()
        return False

    def _result(self, outcome: str, processed: int) -> WorkerResult:
        with self.factory() as s:
            return WorkerResult(outcome, processed, queue.counts_by_state(s, self.run_id))
