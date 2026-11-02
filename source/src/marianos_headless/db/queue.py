"""Durable task queue on PostgreSQL (brief §11).

``FOR UPDATE SKIP LOCKED`` leasing with a heartbeat. An expired lease makes the task leasable again.
Every lease increments ``attempts``. A checkpoint (``cursor``) is written by the lease holder only, so
a worker that lost its lease cannot overwrite a newer worker's progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from marianos_headless.core.ids import new_id
from marianos_headless.core.timeutil import utcnow
from marianos_headless.db.models import Task

TERMINAL_STATES = frozenset({"succeeded", "failed", "blocked", "skipped"})
ACTIVE_STATES = frozenset({"leased", "running"})


class LeaseLost(RuntimeError):
    """The caller no longer holds the task's lease (it expired and was taken over)."""


@dataclass(frozen=True)
class Lease:
    task_id: str
    owner: str
    kind: str
    idem_key: str
    attempts: int
    cursor: dict[str, Any]
    taxonomy_id: str | None
    category_source_id: str | None
    reclaimed: bool  # the previous lease expired without completion


def enqueue(
    session: Session,
    run_id: str,
    kind: str,
    idem_key: str,
    *,
    priority: int = 100,
    category_source_id: str | None = None,
    taxonomy_id: str | None = None,
    cursor: dict[str, Any] | None = None,
) -> bool:
    """Insert a task once. Returns ``False`` when ``(run_id, idem_key)`` already exists."""
    stmt = (
        insert(Task)
        .values(
            run_id=run_id,
            kind=kind,
            idem_key=idem_key,
            priority=priority,
            category_source_id=category_source_id,
            taxonomy_id=taxonomy_id,
            cursor=cursor or {},
            id=new_id(),
        )
        .on_conflict_do_nothing(constraint="uq_tasks_run_idem")
        .returning(Task.id)
    )
    return session.execute(stmt).first() is not None


def lease_next(
    session: Session,
    run_id: str,
    owner: str,
    *,
    lease_s: float = 120,
    now: datetime | None = None,
    kinds: tuple[str, ...] | None = None,
) -> Lease | None:
    now = now or utcnow()
    cond = or_(
        Task.state == "pending",
        and_(Task.state == "retry_wait", or_(Task.not_before.is_(None), Task.not_before <= now)),
        and_(Task.state.in_(ACTIVE_STATES), Task.lease_expires_at < now),
    )
    # Stage barrier: a task waits until every earlier-stage task (lower priority) of the run is terminal,
    # so e.g. "assemble" never runs while a listing task is still leased by a crashed worker.
    earlier = aliased(Task)
    blocked = (
        select(earlier.id)
        .where(
            earlier.run_id == Task.run_id,
            earlier.priority < Task.priority,
            earlier.state.not_in(tuple(TERMINAL_STATES)),
        )
        .exists()
    )
    q = select(Task).where(Task.run_id == run_id, cond, ~blocked)
    if kinds:
        q = q.where(Task.kind.in_(kinds))
    task = session.scalars(
        q.order_by(Task.priority, Task.created_at, Task.id).with_for_update(skip_locked=True).limit(1)
    ).first()
    if task is None:
        return None
    reclaimed = task.state in ACTIVE_STATES
    task.state = "leased"
    task.lease_owner = owner
    task.lease_expires_at = now + timedelta(seconds=lease_s)
    task.attempts = (task.attempts or 0) + 1
    session.flush()
    return Lease(
        task.id,
        owner,
        task.kind,
        task.idem_key,
        task.attempts,
        dict(task.cursor or {}),
        task.taxonomy_id,
        task.category_source_id,
        reclaimed,
    )


def _owned(task_id: str, owner: str) -> Any:
    return and_(Task.id == task_id, Task.lease_owner == owner, Task.state.in_(ACTIVE_STATES))


def heartbeat(session: Session, lease: Lease, *, lease_s: float = 120, now: datetime | None = None) -> None:
    now = now or utcnow()
    res = session.execute(
        update(Task)
        .where(_owned(lease.task_id, lease.owner), Task.lease_expires_at >= now)
        .values(lease_expires_at=now + timedelta(seconds=lease_s))
    )
    if res.rowcount != 1:  # type: ignore[attr-defined]
        raise LeaseLost(lease.task_id)


def mark_running(session: Session, lease: Lease) -> None:
    res = session.execute(update(Task).where(_owned(lease.task_id, lease.owner)).values(state="running"))
    if res.rowcount != 1:  # type: ignore[attr-defined]
        raise LeaseLost(lease.task_id)


def checkpoint(
    session: Session, lease: Lease, cursor: dict[str, Any], *, now: datetime | None = None
) -> None:
    """Durably record progress *before* the next navigation (caller commits)."""
    now = now or utcnow()
    res = session.execute(
        update(Task)
        .where(_owned(lease.task_id, lease.owner), Task.lease_expires_at >= now)
        .values(cursor=cursor)
    )
    if res.rowcount != 1:  # type: ignore[attr-defined]
        raise LeaseLost(lease.task_id)


def _finish(session: Session, lease: Lease, **values: Any) -> None:
    res = session.execute(
        update(Task)
        .where(_owned(lease.task_id, lease.owner))
        .values(lease_owner=None, lease_expires_at=None, **values)
    )
    if res.rowcount != 1:  # type: ignore[attr-defined]
        raise LeaseLost(lease.task_id)


def succeed(session: Session, lease: Lease, cursor: dict[str, Any] | None = None) -> None:
    extra = {"cursor": cursor} if cursor is not None else {}
    _finish(session, lease, state="succeeded", last_error=None, **extra)


def release(session: Session, lease: Lease) -> None:
    """Return a leased task to ``pending`` (cursor and attempts kept), e.g. on pause or cancel."""
    _finish(session, lease, state="pending")


def block(session: Session, lease: Lease, reason: str) -> None:
    _finish(session, lease, state="blocked", last_error=reason[:2000])


def skip(session: Session, lease: Lease, reason: str) -> None:
    _finish(session, lease, state="skipped", last_error=reason[:2000])


def fail(
    session: Session, lease: Lease, error: str, *, retry_after_s: float | None, now: datetime | None = None
) -> str:
    """``retry_after_s=None`` makes the failure final; otherwise the task waits and is retried."""
    now = now or utcnow()
    if retry_after_s is None:
        _finish(session, lease, state="failed", last_error=error[:2000])
        return "failed"
    _finish(
        session,
        lease,
        state="retry_wait",
        last_error=error[:2000],
        not_before=now + timedelta(seconds=retry_after_s),
    )
    return "retry_wait"


def reclaim_orphans(session: Session, run_id: str) -> int:
    """Return every in-flight task of the run to ``pending`` (cursor kept).

    Only call this while holding the store's advisory run lock and before leasing anything: the lock dies
    with its process, so holding it proves no other worker of this store is alive and any lease left
    in the table belongs to a worker that stopped (whatever owner name it used).
    """
    res = session.execute(
        update(Task)
        .where(Task.run_id == run_id, Task.state.in_(ACTIVE_STATES))
        .values(state="pending", lease_owner=None, lease_expires_at=None)
    )
    return int(res.rowcount or 0)  # type: ignore[attr-defined]


def counts_by_state(session: Session, run_id: str) -> dict[str, int]:
    rows = session.execute(
        select(Task.state, func.count()).where(Task.run_id == run_id).group_by(Task.state)
    ).all()
    return {state: int(n) for state, n in rows}


def all_terminal(session: Session, run_id: str) -> bool:
    counts = counts_by_state(session, run_id)
    return bool(counts) and all(state in TERMINAL_STATES for state in counts)
