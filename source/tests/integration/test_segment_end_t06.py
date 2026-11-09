"""Release 1.9.0 (T06): the exported run data shows each collection segment as it ended.

Before 1.9.0 the run's exports were written while its last segment was still open (the provider session and
the segment were closed only after the export task), so the exported supporting log gave the final segment no
end.
Now the segment ends (provider session closed, end written) before the records are assembled, checked and
exported. A segment whose worker was killed keeps an unknown end: only its bounds are exported.

The provider is the fake Web API of ``test_oxylabs_collector`` (synthetic pages; nothing leaves the process).
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from marianos_headless.collection import recovery
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.db.models import CollectionSegment, Event, Run, Store
from marianos_headless.publishing.supporting_log import supporting_log
from marianos_headless.worker.pipeline import Pipeline
from tests.integration.test_oxylabs_collector import FakeOxylabs, _ceiling, _run, env  # noqa: F401

pytestmark = [pytest.mark.postgres]


def _exported(env: dict[str, Any], run_id: str) -> dict[str, Any]:  # noqa: F811
    key = f"runs/{env['store'].key}/{run_id}/exports/provenance.json"
    return json.loads(env["storage"].get_bytes(key))


def _segments(env: dict[str, Any], run_id: str) -> list[CollectionSegment]:  # noqa: F811
    with env["factory"]() as s:
        return list(
            s.scalars(
                select(CollectionSegment)
                .where(CollectionSegment.run_id == run_id)
                .order_by(CollectionSegment.started_at)
            )
        )


def _codes(env: dict[str, Any], run_id: str) -> list[str]:  # noqa: F811
    with env["factory"]() as s:
        return list(s.scalars(select(Event.code).where(Event.run_id == run_id).order_by(Event.id)))


def test_a_finished_run_exports_its_segment_with_the_end_it_has(env: dict[str, Any], settings: Any) -> None:  # noqa: F811
    _ceiling(env["factory"], 10)
    run_id, status = _run(env, settings, FakeOxylabs())
    assert status == "rejected"  # finished; incomplete as every read-through search listing is
    (seg,) = _segments(env, run_id)
    assert seg.end_state == "ended" and seg.ended_at is not None
    (exported,) = _exported(env, run_id)["segments"]
    assert exported["ended_at"] == iso(seg.ended_at) and exported["end_state"] == "ended"
    assert exported["ended_not_after"] is None
    # Close, then snapshot: the provider session and the segment end before the records are assembled.
    codes = _codes(env, run_id)
    assert (
        codes.index("PROVIDER_SESSION_CLOSED")
        < codes.index("RECORDS_ASSEMBLED")
        < codes.index("EXPORTS_STAGED")
    )


def test_a_paused_and_resumed_run_exports_both_segments_as_they_ended(
    env: dict[str, Any],  # noqa: F811
    settings: Any,
) -> None:
    _ceiling(env["factory"], 3)
    fake = FakeOxylabs()
    run_id, status = _run(env, settings, fake)
    assert status == "interrupted"  # a graceful stop: the spending ceiling
    (first,) = _segments(env, run_id)
    assert first.end_state == "ended" and first.ended_at is not None and first.stop_code == "SPENDING_CEILING"
    _ceiling(env["factory"], 5)
    run_id, status = _run(env, settings, fake, run_id=run_id)
    assert status == "rejected"
    segs = _segments(env, run_id)
    assert len(segs) == 2 and all(g.end_state == "ended" and g.ended_at is not None for g in segs)
    exported = _exported(env, run_id)["segments"]
    assert [(e["id"], e["ended_at"], e["stop_code"]) for e in exported] == [
        (g.id, iso(g.ended_at), g.stop_code) for g in segs
    ]
    assert exported[0]["stop_code"] == "SPENDING_CEILING" and exported[1]["stop_code"] is None


def test_a_failed_export_leaves_the_segment_ended_and_no_export_with_an_open_one(
    env: dict[str, Any],  # noqa: F811
    settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ceiling(env["factory"], 10)
    calls: list[str] = []

    def failing(self: Pipeline, s: Any, run: Run, prefix: str | None = None) -> Any:
        calls.append(run.id)
        raise OSError("storage refused the write (test)")

    monkeypatch.setattr(Pipeline, "write_run_exports", failing)
    run_id, status = _run(env, settings, FakeOxylabs())
    assert calls and status == "rejected"
    (seg,) = _segments(env, run_id)
    assert seg.end_state == "ended" and seg.ended_at is not None  # ended before the export was attempted
    monkeypatch.undo()
    # The partial export written afterwards (operations.after_run does this for a rejected run) agrees.
    with env["factory"]() as s:
        log = supporting_log(s, run_id)
    assert [(e["ended_at"], e["end_state"]) for e in log["segments"]] == [(iso(seg.ended_at), "ended")]


def test_a_killed_segment_is_exported_with_an_unknown_end_and_its_bounds(
    env: dict[str, Any],  # noqa: F811
    settings: Any,
) -> None:
    _ceiling(env["factory"], 10)
    run_id, _ = _run(env, settings, FakeOxylabs())
    last_seen = utcnow() - timedelta(minutes=5)
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        store = s.get(Store, run.store_id)
        assert store is not None
        # A segment whose worker was killed (no end written), as a forced kill leaves it.
        killed = CollectionSegment(
            run_id=run_id,
            store_id=store.id,
            trigger="resume",
            day=last_seen.date().isoformat(),
            started_at=last_seen - timedelta(minutes=1),
            heartbeat_at=last_seen,
        )
        s.add(killed)
        s.commit()
        killed_id = killed.id
    found_at = utcnow()
    with env["factory"]() as s:
        (found,) = recovery.recover_abandoned(s, store.id, now=found_at)
        s.commit()
        log = supporting_log(s, run_id)
    assert found["segment"] == killed_id and found["ended_at"] is None
    exported = {e["id"]: e for e in log["segments"]}[killed_id]
    assert exported["end_state"] == "abandoned" and exported["ended_at"] is None  # never an invented time
    assert exported["last_seen_at"] == iso(last_seen) and exported["ended_not_after"] == iso(found_at)
