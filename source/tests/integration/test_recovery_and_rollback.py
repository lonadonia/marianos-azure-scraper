"""Release 1.4.0: a segment left open by a killed worker, its unsettled provider request, and rolling the
published dataset back. SYNTHETIC rows in a throwaway database; no provider request is sent."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection import recovery
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.db.models import AuditLog, CollectionSegment, Event, ProviderUsage, PublicationPointer
from marianos_headless.publishing.publish import (
    PointerConflict,
    PublicationRefused,
    latest_key,
    publish_run,
    rollback_publication,
)
from marianos_headless.storage.local import LocalStorageAdapter
from tests.integration.helpers import new_run, seed
from tests.integration.test_publish import prepared_run

pytestmark = pytest.mark.postgres

RATE = 0.0015


def usage(factory: sessionmaker[Session]) -> dict[str, object]:
    with factory() as s:
        return oxylabs.usage_since(s, None)


def test_a_killed_segment_is_closed_as_abandoned_with_bounds_and_its_request_kept_as_possibly_billed(
    migrated_engine: Engine,
) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store, status="running")
    started = utcnow() - timedelta(minutes=10)
    last_seen = started + timedelta(minutes=4)
    with factory() as s:
        seg = CollectionSegment(
            run_id=run.id,
            store_id=store.id,
            trigger="test",
            day=started.date().isoformat(),
            started_at=started,
            heartbeat_at=last_seen,
            steps=3,
        )
        s.add(seg)
        s.flush()
        seg_id = seg.id
        for state, source, cost in (("settled", "rule", RATE), ("reserved", "reserved", RATE)):
            s.add(
                ProviderUsage(
                    provider=oxylabs.PROVIDER,
                    run_id=run.id,
                    segment_id=seg_id,
                    purpose="listing",
                    endpoint="/v1/scrape/marianos/search",
                    target="q",
                    reserved_at=started,
                    cost_usd=cost,
                    state=state,
                    cost_source=source,
                )
            )
        s.commit()
    before = usage(factory)
    assert before["submissions"] == 2 and before["usd"] == pytest.approx(2 * RATE)

    now = utcnow()
    with factory() as s:
        (found,) = recovery.recover_abandoned(s, store.id, now=now)
        s.commit()
    assert found["segment"] == seg_id and found["end"] == "unknown" and found["ended_at"] is None
    assert found["ended_not_before"] == iso(last_seen) and found["ended_not_after"] == iso(now)
    assert found["reservations_unsettled"] == 1 and found["reservations_usd_kept"] == RATE
    with factory() as s:
        g = s.get(CollectionSegment, seg_id)
        assert g is not None and g.end_state == "abandoned" and g.ended_at is None
        assert g.recovered_at is not None and g.stop_code == "TERMINATED"
        rows = list(s.scalars(select(ProviderUsage).where(ProviderUsage.segment_id == seg_id)))
        interrupted = [u for u in rows if u.outcome == recovery.INTERRUPTED]
        assert len(interrupted) == 1
        u = interrupted[0]
        assert (u.state, u.cost_source, u.cost_usd) == ("settled", "unknown", RATE)
        assert s.scalar(select(Event).where(Event.code == "SEGMENT_ABANDONED")) is not None
    # Kept once: the possibly billed request still counts against the ceiling, and only once.
    after = usage(factory)
    assert after["submissions"] == 2 and after["usd"] == pytest.approx(2 * RATE) and after["unknown"] == 1
    # A second recovery finds nothing left to do.
    with factory() as s:
        assert recovery.recover_abandoned(s, store.id, now=utcnow()) == []
        s.commit()
    assert usage(factory) == after


def test_a_closed_or_current_segment_is_not_recovered(migrated_engine: Engine) -> None:
    factory, store = seed(migrated_engine)
    run = new_run(factory, store, status="running")
    now = utcnow()
    with factory() as s:
        closed = CollectionSegment(
            run_id=run.id,
            store_id=store.id,
            trigger="test",
            day=now.date().isoformat(),
            started_at=now,
            heartbeat_at=now,
            ended_at=now,
            end_state="ended",
        )
        current = CollectionSegment(
            run_id=run.id,
            store_id=store.id,
            trigger="test",
            day=now.date().isoformat(),
            started_at=now,
            heartbeat_at=now,
        )
        s.add_all([closed, current])
        s.commit()
        assert recovery.recover_abandoned(s, store.id, now=now, exclude=current.id) == []


def test_rollback_moves_the_pointer_back_atomically_and_is_audited(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    factory, store = seed(migrated_engine)
    storage = LocalStorageAdapter(tmp_path)
    first = prepared_run(factory, store, storage)
    p1 = publish_run(factory, storage, first, "tester")
    with pytest.raises(PublicationRefused, match="nothing to roll back to"):
        rollback_publication(factory, storage, store.id, "tester", "test")
    second = prepared_run(factory, store, storage, n=4)
    p2 = publish_run(factory, storage, second, "tester")
    assert p2.previous_publication_id == p1.publication_id

    with pytest.raises(PublicationRefused, match="reason"):
        rollback_publication(factory, storage, store.id, "tester", "  ")

    class Crash(Exception):
        pass

    def fault(stage: str) -> None:
        if stage == "inside_commit":
            raise Crash(stage)

    with pytest.raises(Crash):
        rollback_publication(factory, storage, store.id, "tester", "demo", fault=fault)
    with factory() as s:
        ptr = s.get(PublicationPointer, store.id)
        assert ptr is not None and ptr.publication_id == p2.publication_id  # the crash changed nothing

    rb = rollback_publication(factory, storage, store.id, "tester", "demo: the newer dataset is withdrawn")
    assert rb.publication_id == p1.publication_id and rb.previous_publication_id == p2.publication_id
    with factory() as s:
        ptr = s.get(PublicationPointer, store.id)
        assert ptr is not None and ptr.publication_id == p1.publication_id and ptr.version == p2.version + 1
        audit = s.scalar(select(AuditLog).where(AuditLog.action == "rollback"))
        assert audit is not None and audit.target == first
    latest = storage.get_bytes(latest_key(store.key))
    assert first.encode() in latest


def test_a_concurrent_pointer_move_makes_the_rollback_fail_cleanly(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    factory, store = seed(migrated_engine)
    storage = LocalStorageAdapter(tmp_path)
    publish_run(factory, storage, prepared_run(factory, store, storage), "tester")
    p2 = publish_run(factory, storage, prepared_run(factory, store, storage), "tester")

    def bump(stage: str) -> None:
        if stage == "before_commit":
            with factory() as s, s.begin():
                ptr = s.get(PublicationPointer, store.id)
                assert ptr is not None
                ptr.version += 1

    with pytest.raises(PointerConflict):
        rollback_publication(factory, storage, store.id, "tester", "race", fault=bump)
    with factory() as s:
        ptr = s.get(PublicationPointer, store.id)
        assert ptr is not None and ptr.publication_id == p2.publication_id
