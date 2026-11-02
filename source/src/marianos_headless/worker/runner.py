"""Task runner (brief §11): lease → handle → checkpoint → succeed / retry / block.

Handlers are async and receive a :class:`TaskContext`. They call ``ctx.checkpoint(cursor)`` before
every next navigation, so a crash resumes from the last durable cursor. Writes must be idempotent
(observations and memberships use unique keys), so re-processing a page after a crash cannot double
counts. Cancellation is cooperative: handlers check ``ctx.cancelled()`` between navigations.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.core.settings import Settings
from marianos_headless.db import queue
from marianos_headless.db.models import Run, Task
from marianos_headless.storage.base import StorageAdapter
from marianos_headless.worker.retry import CircuitBreaker, FailureKind, TaskFailure, decide
from marianos_headless.worker.runs import clear_pause, event, transition


class CancelledByOperator(Exception):
    pass


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

    @property
    def cursor(self) -> dict[str, Any]:
        return self.lease.cursor

    def checkpoint(self, cursor: Mapping[str, Any]) -> None:
        with self.factory() as s:
            queue.checkpoint(s, self.lease, dict(cursor))
            queue.heartbeat(s, self.lease, lease_s=self.lease_s)
            s.commit()
        self.lease = queue.Lease(**{**self.lease.__dict__, "cursor": dict(cursor)})

    def heartbeat(self) -> None:
        with self.factory() as s:
            queue.heartbeat(s, self.lease, lease_s=self.lease_s)
            s.commit()

    def cancelled(self) -> bool:
        """True when the operator asked to stop or pause: handlers check it between navigations."""
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
    ):
        self.factory = factory
        self.run_id = run_id
        self.owner = owner
        self.handlers = handlers
        self.settings = settings
        self.storage = storage
        self.lease_s = lease_s
        self.breaker = CircuitBreaker(settings.circuit_breaker)
        self._rate_limited: set[str] = set()

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
        processed = 0
        while True:
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
                        "paused at a checkpoint; resume continues from it"
                        + (f" ({reason})" if reason else ""),
                        {"stop_code": run.stop_code, "stop_detail": run.stop_detail},
                    )
                    s.commit()
                return self._result("paused", processed)
            if max_tasks is not None and processed >= max_tasks:
                return self._result("max_tasks", processed)
            with self.factory() as s:
                lease = queue.lease_next(s, self.run_id, self.owner, lease_s=self.lease_s)
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
            if lease is None:
                with self.factory() as s:
                    done = queue.all_terminal(s, self.run_id)
                return self._result("idle" if done else "waiting", processed)
            processed += 1
            category = lease.category_source_id or lease.kind
            if self.breaker.is_open(category):
                with self.factory() as s:
                    queue.skip(s, lease, "category circuit open")
                    s.commit()
                continue
            handler = self.handlers.get(lease.kind)
            if handler is None:
                with self.factory() as s:
                    queue.fail(s, lease, f"no handler for {lease.kind}", retry_after_s=None)
                    s.commit()
                continue
            ctx = TaskContext(lease, self.run_id, self.factory, self.settings, self.storage, self.lease_s)
            try:
                final_cursor = await handler(ctx)
            except queue.LeaseLost:
                with self.factory() as s:
                    event(s, self.run_id, "WARN", "TASK_LEASE_LOST", lease.idem_key)
                    s.commit()
                continue
            except CancelledByOperator:
                # Hand the task back (cursor kept) so a resumed worker can lease it immediately;
                # the loop head then sees the cancel/pause flag and stops.
                with self.factory() as s:
                    queue.release(s, ctx.lease)
                    s.commit()
                continue
            except RunStop as stop:
                if self._stop(ctx, stop):
                    return self._result("aborted", processed)
                continue
            except TaskFailure as failure:
                aborted = self._handle_failure(ctx, category, failure)
                if aborted:
                    return self._result("aborted", processed)
                continue
            except SQLAlchemyError:
                raise  # database trouble stops the worker; a resume continues from the checkpoints
            except Exception as exc:
                # A parser or contract error (e.g. a malformed response) is a permanent task failure,
                # recorded with its type, never a worker crash that leaves the run stalled.
                permanent = TaskFailure(FailureKind.PERMANENT, f"{type(exc).__name__}: {exc}"[:500])
                if self._handle_failure(ctx, category, permanent):
                    return self._result("aborted", processed)
                continue
            with self.factory() as s:
                queue.succeed(s, ctx.lease, final_cursor if final_cursor is not None else ctx.lease.cursor)
                s.commit()
            self.breaker.record_success(category)

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
                "RUN_STOPPED" if not stop.resumable else "RUN_LIMIT_REACHED",
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
