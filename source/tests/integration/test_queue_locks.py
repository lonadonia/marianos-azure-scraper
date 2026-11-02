from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import Engine, select

from marianos_headless.core.timeutil import utcnow
from marianos_headless.db import queue
from marianos_headless.db.locks import RunLockHeld, StoreRunLock
from marianos_headless.db.models import Event, RunLock
from tests.integration.helpers import new_run, seed

pytestmark = pytest.mark.postgres


def test_enqueue_is_idempotent_and_skip_locked_spreads_work(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    with factory() as s:
        assert queue.enqueue(s, run.id, "listing_node", f"{run.id}/listing/26003", taxonomy_id="26003")
        assert not queue.enqueue(s, run.id, "listing_node", f"{run.id}/listing/26003", taxonomy_id="26003")
        assert queue.enqueue(s, run.id, "listing_node", f"{run.id}/listing/26002", taxonomy_id="26002")
        s.commit()
    # Two workers in concurrent transactions get different tasks.
    s1, s2 = factory(), factory()
    try:
        l1 = queue.lease_next(s1, run.id, "w1")
        l2 = queue.lease_next(s2, run.id, "w2")
        assert l1 and l2 and l1.task_id != l2.task_id
        with factory() as s3:
            assert queue.lease_next(s3, run.id, "w3") is None  # both rows locked or leased
        s1.commit()
        s2.commit()
    finally:
        s1.close()
        s2.close()


def test_expired_lease_is_reclaimed_and_old_owner_loses_it(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    t0 = utcnow()
    with factory() as s:
        queue.enqueue(s, run.id, "listing_node", "a")
        lease = queue.lease_next(s, run.id, "w1", lease_s=60, now=t0)
        assert lease is not None
        queue.mark_running(s, lease)
        queue.checkpoint(s, lease, {"next_offset": 48}, now=t0)
        s.commit()
    with factory() as s:
        assert queue.lease_next(s, run.id, "w2", now=t0 + timedelta(seconds=30)) is None  # still held
        taken = queue.lease_next(s, run.id, "w2", lease_s=60, now=t0 + timedelta(seconds=61))
        assert taken is not None and taken.reclaimed and taken.attempts == 2
        assert taken.cursor == {"next_offset": 48}  # resumes from the durable checkpoint
        s.commit()
    with factory() as s, pytest.raises(queue.LeaseLost):
        queue.checkpoint(s, lease, {"next_offset": 96}, now=t0 + timedelta(seconds=62))


def test_retry_wait_and_terminal_states(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    t0 = utcnow()
    with factory() as s:
        queue.enqueue(s, run.id, "pdp", "p1")
        lease = queue.lease_next(s, run.id, "w", now=t0)
        assert lease is not None
        assert queue.fail(s, lease, "timeout", retry_after_s=10, now=t0) == "retry_wait"
        s.commit()
        assert queue.lease_next(s, run.id, "w", now=t0 + timedelta(seconds=5)) is None
        again = queue.lease_next(s, run.id, "w", now=t0 + timedelta(seconds=11))
        assert again is not None and again.attempts == 2
        queue.succeed(s, again)
        s.commit()
        assert queue.all_terminal(s, run.id)
        assert queue.counts_by_state(s, run.id) == {"succeeded": 1}


def test_one_active_run_per_store(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    r1, r2 = new_run(factory, store), new_run(factory, store)
    lock = StoreRunLock(migrated_engine, store.id, r1.id, "w1").acquire()
    try:
        with pytest.raises(RunLockHeld):
            StoreRunLock(migrated_engine, store.id, r2.id, "w2").acquire()
        lock.heartbeat()
    finally:
        lock.release()
    with StoreRunLock(migrated_engine, store.id, r2.id, "w2"):
        pass


def test_stale_lock_row_is_taken_over_only_after_expiry(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    dead, fresh, newer = new_run(factory, store), new_run(factory, store), new_run(factory, store)
    now = utcnow()
    with factory() as s:  # a crashed worker left its row behind (its advisory lock died with it)
        s.add(
            RunLock(
                store_id=store.id,
                run_id=dead.id,
                holder="crashed",
                heartbeat_at=now,
                expires_at=now + timedelta(minutes=5),
            )
        )
        s.commit()
    with pytest.raises(RunLockHeld):
        StoreRunLock(migrated_engine, store.id, fresh.id, "w").acquire()
    with factory() as s:
        row = s.get(RunLock, store.id)
        assert row is not None
        row.expires_at = now - timedelta(seconds=1)
        s.commit()
    lock = StoreRunLock(migrated_engine, store.id, newer.id, "w").acquire()
    assert lock.took_over_from == dead.id
    lock.release()
    with factory() as s:
        codes = list(s.scalars(select(Event.code).where(Event.run_id == newer.id)))
        assert "RUN_LOCK_STALE_TAKEOVER" in codes


def test_stage_barrier_waits_for_earlier_stages(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    t0 = utcnow()
    with factory() as s:
        queue.enqueue(s, run.id, "listing_node", "listing", priority=50)
        queue.enqueue(s, run.id, "assemble", "assemble", priority=80)
        s.commit()
        first = queue.lease_next(s, run.id, "w1", lease_s=60, now=t0)
        assert first is not None and first.kind == "listing_node"
        s.commit()
        # The listing task is held (e.g. by a worker that crashed): assemble must not start.
        assert queue.lease_next(s, run.id, "w2", now=t0 + timedelta(seconds=1)) is None
        s.commit()
        queue.succeed(s, first)
        s.commit()
        nxt = queue.lease_next(s, run.id, "w2", now=t0 + timedelta(seconds=2))
        assert nxt is not None and nxt.kind == "assemble"


def test_reclaim_orphans_and_worker_liveness(migrated_engine: Engine) -> None:
    from marianos_headless.db.locks import worker_alive

    factory, store = seed(migrated_engine)
    run = new_run(factory, store)
    with factory() as s:
        queue.enqueue(s, run.id, "listing_node", "a")
        lease = queue.lease_next(s, run.id, "dead-worker", lease_s=600)
        assert lease is not None
        queue.checkpoint(s, lease, {"next_page": 3})
        s.commit()
        assert worker_alive(s, store.id) is False
    lock = StoreRunLock(migrated_engine, store.id, run.id, "new-worker").acquire()
    try:
        with factory() as s:
            assert worker_alive(s, store.id) is True
            assert queue.reclaim_orphans(s, run.id) == 1
            s.commit()
            again = queue.lease_next(s, run.id, "new-worker")
            assert again is not None and again.cursor == {"next_page": 3} and again.attempts == 2
    finally:
        lock.release()
    with factory() as s:
        assert worker_alive(s, store.id) is False


def test_liveness_is_per_run_and_direct_control_excludes_a_starting_worker(migrated_engine: Engine) -> None:
    """A stale run is not "alive" because another run's worker holds the store, and a direct
    pause/stop claim keeps workers out until its transaction ends."""
    from marianos_headless.db.locks import claim_idle_run, worker_alive, worker_state

    factory, store = seed(migrated_engine)
    stale, current = new_run(factory, store), new_run(factory, store)
    lock = StoreRunLock(migrated_engine, store.id, current.id, "worker-current").acquire()
    try:
        with factory() as s:
            assert worker_state(s, store.id, current.id) == "this"
            assert worker_state(s, store.id, stale.id) == "other"
            assert worker_alive(s, store.id, stale.id) is False
            assert worker_alive(s, store.id) is True  # store-level view unchanged
            # The stale run can be stopped directly: its own worker cannot start while the store is held.
            assert claim_idle_run(s, store.id, stale.id) is True
            assert claim_idle_run(s, store.id, current.id) is False
    finally:
        lock.release()
    with factory() as s:
        assert worker_state(s, store.id, stale.id) == "none"
        assert claim_idle_run(s, store.id, stale.id) is True  # xact lock now held by this session
        with pytest.raises(RunLockHeld):
            StoreRunLock(migrated_engine, store.id, stale.id, "worker-late").acquire()
        s.commit()  # releases the transaction lock
    late = StoreRunLock(migrated_engine, store.id, stale.id, "worker-late").acquire()
    late.release()


def test_dead_worker_lock_row_does_not_block_once_its_run_is_stopped(migrated_engine: Engine) -> None:
    """A killed worker leaves its row behind. Its own run may resume at once; another run is refused
    while the dead run is still active, and takes over as soon as that run is stopped."""
    from sqlalchemy import update

    from marianos_headless.db.locks import claim_idle_run, drop_dead_lock, stale_holder
    from marianos_headless.db.models import Run

    factory, store = seed(migrated_engine)
    dead, fresh = new_run(factory, store), new_run(factory, store)
    with factory() as s:
        s.execute(update(Run).where(Run.id == dead.id).values(status="running"))
        s.commit()
    crashed = StoreRunLock(migrated_engine, store.id, dead.id, "worker-dead").acquire()
    crashed._unlock()  # the process died: advisory lock gone, row left with a future expiry
    with factory() as s:
        assert stale_holder(s, store.id) is not None
        assert stale_holder(s, store.id, dead.id) is None  # its own run is not blocked by it
    with pytest.raises(RunLockHeld, match="holds the lock until"):
        StoreRunLock(migrated_engine, store.id, fresh.id, "worker-fresh").acquire()
    # Resume of the dead run itself is allowed immediately.
    StoreRunLock(migrated_engine, store.id, dead.id, "worker-resumed").acquire()._unlock()
    # Operator stops the dead run (API direct path): its row goes, the store is free at once.
    with factory() as s:
        assert claim_idle_run(s, store.id, dead.id)
        drop_dead_lock(s, dead.id)
        s.execute(update(Run).where(Run.id == dead.id).values(status="cancelled"))
        s.commit()
        assert stale_holder(s, store.id) is None
    StoreRunLock(migrated_engine, store.id, fresh.id, "worker-fresh").acquire().release()


def test_row_of_a_finished_run_is_taken_over_without_waiting(migrated_engine: Engine) -> None:
    from sqlalchemy import update

    from marianos_headless.db.models import Run

    factory, store = seed(migrated_engine)
    old, new = new_run(factory, store), new_run(factory, store)
    leftover = StoreRunLock(migrated_engine, store.id, old.id, "worker-old").acquire()
    leftover._unlock()
    with factory() as s:
        s.execute(update(Run).where(Run.id == old.id).values(status="rejected"))
        s.commit()
    lock = StoreRunLock(migrated_engine, store.id, new.id, "worker-new").acquire()
    assert lock.took_over_from == old.id
    lock.release()
