"""One active run per store (brief §11): a ``run_locks`` row plus a session-level advisory lock.

The advisory lock lives on a dedicated connection for the run's lifetime and disappears with the
process, so two live workers can never both hold it. The row makes the lock visible and records
heartbeats. A row left behind by a crashed worker is taken over by its own run at once (resume), by
another run once the old run is no longer active (stopped/finished), and otherwise only after
``expires_at`` passes with no heartbeat. Cron flags alone are never relied on.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy import Connection, Engine, delete, func, select, text
from sqlalchemy.orm import Session

from marianos_headless.core.timeutil import utcnow
from marianos_headless.db.models import Event, Run, RunLock

ACTIVE_RUN_STATES = ("queued", "preflight", "running", "validating")


class RunLockHeld(RuntimeError):
    pass


def advisory_key(store_id: str) -> int:
    digest = hashlib.sha256(f"marianos_headless-run:{store_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _advisory_held(session: Session, store_id: str) -> bool:
    key = advisory_key(store_id) & 0xFFFFFFFFFFFFFFFF
    classid, objid = key >> 32, key & 0xFFFFFFFF
    held = session.execute(
        text(
            "SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
            "AND classid::bigint = :c AND objid::bigint = :o AND objsubid = 1"
        ),
        {"c": classid, "o": objid},
    ).first()
    return held is not None


def worker_state(session: Session, store_id: str, run_id: str) -> str:
    """Who is working on the store: ``"this"`` run, an ``"other"`` run, or ``"none"``.

    The advisory lock proves a live worker process; the ``run_locks`` row (written right after the
    advisory lock is taken) says which run it serves. While the row is missing the holder is assumed
    to be this run, so control requests stay cooperative rather than racing a starting worker.
    """
    if not _advisory_held(session, store_id):
        return "none"
    row = session.get(RunLock, store_id)
    return "other" if row is not None and row.run_id != run_id else "this"


def worker_alive(session: Session, store_id: str, run_id: str | None = None) -> bool:
    """True while a worker process holds the store lock (for ``run_id``, when given)."""
    if run_id is None:
        return _advisory_held(session, store_id)
    return worker_state(session, store_id, run_id) == "this"


def claim_idle_run(session: Session, store_id: str, run_id: str) -> bool:
    """True when ``run_id`` has no worker and none can start before this transaction ends.

    Takes a transaction-scoped advisory lock on the store key (it conflicts with a worker's session
    lock), so a direct pause/stop and its orphan reclaim cannot interleave with a worker starting up.
    If another run's worker holds the store, this run cannot gain a worker either until that one ends.
    """
    got = session.execute(select(func.pg_try_advisory_xact_lock(advisory_key(store_id)))).scalar()
    return bool(got) or worker_state(session, store_id, run_id) != "this"


def stale_holder(session: Session, store_id: str, run_id: str | None = None) -> RunLock | None:
    """The lock row of another, still-active run whose worker is gone and whose TTL has not passed.

    Such a run blocks new runs for the store until it is resumed or stopped (or the row expires)."""
    if _advisory_held(session, store_id):
        return None
    row = session.get(RunLock, store_id)
    if row is None or row.run_id == run_id or row.expires_at < utcnow():
        return None
    holder = session.get(Run, row.run_id)
    return row if holder is not None and holder.status in ACTIVE_RUN_STATES else None


def drop_dead_lock(session: Session, run_id: str) -> None:
    """Remove the lock row a dead worker left for ``run_id``. Only call after ``claim_idle_run``."""
    session.execute(delete(RunLock).where(RunLock.run_id == run_id))


class StoreRunLock:
    def __init__(self, engine: Engine, store_id: str, run_id: str, holder: str, ttl_s: float = 300):
        self.engine = engine
        self.store_id = store_id
        self.run_id = run_id
        self.holder = holder
        self.ttl = timedelta(seconds=ttl_s)
        self._conn: Connection | None = None
        self.took_over_from: str | None = None

    def acquire(self) -> StoreRunLock:
        conn = self.engine.connect()
        got = conn.execute(select(func.pg_try_advisory_lock(advisory_key(self.store_id)))).scalar()
        conn.commit()
        if not got:
            conn.close()
            raise RunLockHeld(f"store {self.store_id}: another worker holds the advisory lock")
        self._conn = conn
        try:
            with Session(self.engine) as s:
                now = utcnow()
                row = s.get(RunLock, self.store_id, with_for_update=True)
                if row is None:
                    s.add(
                        RunLock(
                            store_id=self.store_id,
                            run_id=self.run_id,
                            holder=self.holder,
                            heartbeat_at=now,
                            expires_at=now + self.ttl,
                        )
                    )
                elif row.run_id == self.run_id or row.expires_at < now or not self._active(s, row.run_id):
                    if row.run_id != self.run_id:
                        self.took_over_from = row.run_id
                        s.add(
                            Event(
                                run_id=self.run_id,
                                level="WARN",
                                code="RUN_LOCK_STALE_TAKEOVER",
                                message=f"took over lock from run {row.run_id}",
                                data={
                                    "previous_holder": row.holder,
                                    "previous_expires_at": row.expires_at.isoformat(),
                                },
                            )
                        )
                    row.run_id, row.holder = self.run_id, self.holder
                    row.heartbeat_at, row.expires_at = now, now + self.ttl
                else:
                    until = row.expires_at.isoformat()
                    raise RunLockHeld(f"store {self.store_id}: run {row.run_id} holds the lock until {until}")
                s.commit()
        except BaseException:
            self._unlock()
            raise
        return self

    @staticmethod
    def _active(s: Session, run_id: str) -> bool:
        run = s.get(Run, run_id)
        return run is not None and run.status in ACTIVE_RUN_STATES

    def heartbeat(self) -> None:
        with Session(self.engine) as s:
            row = s.get(RunLock, self.store_id, with_for_update=True)
            if row is None or row.run_id != self.run_id:
                raise RunLockHeld(f"store {self.store_id}: lock lost")
            now = utcnow()
            row.heartbeat_at, row.expires_at = now, now + self.ttl
            s.commit()

    def release(self) -> None:
        try:
            with Session(self.engine) as s:
                s.execute(
                    delete(RunLock).where(RunLock.store_id == self.store_id, RunLock.run_id == self.run_id)
                )
                s.commit()
        finally:
            self._unlock()

    def _unlock(self) -> None:
        if self._conn is not None:
            try:
                self._conn.execute(select(func.pg_advisory_unlock(advisory_key(self.store_id))))
                self._conn.commit()
            finally:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> StoreRunLock:
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()
