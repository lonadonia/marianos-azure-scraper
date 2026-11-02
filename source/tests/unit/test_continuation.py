"""Long runs in execution segments: the daily window of a continuation day, and which stops leave a run
for the next execution instead of finalizing it (pure functions; no database, no provider)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from marianos_headless import operations
from marianos_headless.collection.config import Limits
from marianos_headless.collection.limits import StopCode, Usage, first_stop
from marianos_headless.collection.live import segment_window_end
from marianos_headless.config_file import StoreCollection

CHICAGO = ZoneInfo("America/Chicago")
OCC = {
    "day": "2026-07-14",
    "start": "2026-07-14T06:00:00-05:00",
    "window_start": "2026-07-14T06:00:00-05:00",
    "window_end": "2026-07-14T18:00:00-05:00",
}


def test_the_occurrence_day_keeps_its_own_window_end() -> None:
    now = datetime(2026, 7, 14, 12, tzinfo=UTC)  # 07:00 local
    assert segment_window_end(OCC, now, CHICAGO) == datetime(2026, 7, 14, 18, tzinfo=CHICAGO)


def test_a_continuation_day_gets_that_days_window_end_also_across_daylight_saving() -> None:
    later = datetime(2026, 7, 16, 14, tzinfo=UTC)  # Thursday 09:00 local
    assert segment_window_end(OCC, later, CHICAGO) == datetime(2026, 7, 16, 18, tzinfo=CHICAGO)
    november = {
        "day": "2026-10-30",
        "start": "2026-10-30T06:00:00-05:00",
        "window_start": "2026-10-30T06:00:00-05:00",
        "window_end": "2026-10-30T18:00:00-05:00",
    }
    after_change = datetime(2026, 11, 2, 15, tzinfo=UTC)  # Monday 09:00 CST (UTC-6)
    end = segment_window_end(november, after_change, CHICAGO)
    assert end == datetime(2026, 11, 2, 18, tzinfo=CHICAGO) and end.utcoffset().total_seconds() == -6 * 3600  # type: ignore[union-attr]


def test_a_window_ending_at_midnight_ends_at_the_next_midnight_on_a_continuation_day() -> None:
    occ = {**OCC, "window_end": "2026-07-15T00:00:00-05:00"}
    later = datetime(2026, 7, 16, 14, tzinfo=UTC)
    assert segment_window_end(occ, later, CHICAGO) == datetime(2026, 7, 17, 0, tzinfo=CHICAGO)


def test_an_execution_limit_is_a_resumable_stop_and_never_the_runs_scope() -> None:
    limits = Limits(max_run_minutes=2880, max_segment_minutes=300)
    assert not limits.bounded()  # a production run with segments is not a pilot
    stop = first_stop(limits, Usage(run_active_s=301 * 60, segment_active_s=301 * 60), account_remaining=None)
    assert stop is not None and stop[0] is StopCode.SEGMENT_DURATION_LIMIT
    whole = first_stop(limits, Usage(run_active_s=2881 * 60, segment_active_s=10), account_remaining=None)
    assert whole is not None and whole[0] is StopCode.RUN_DURATION_LIMIT  # the run's total budget holds


def _run(trigger: str, schedule: dict[str, Any]) -> Any:
    coll = StoreCollection(schedule=schedule).model_dump(mode="json")
    return SimpleNamespace(trigger=trigger, config_snapshot={"collection": coll})


@pytest.mark.parametrize(
    ("trigger", "continue_unfinished", "code", "expected"),
    [
        ("manual", True, "SEGMENT_DURATION_LIMIT", True),  # any run: the next execution continues it
        ("schedule", True, "SEGMENT_DURATION_LIMIT", True),
        ("schedule", True, "SCHEDULE_WINDOW_END", True),  # continued inside a later day's window
        ("schedule", False, "SCHEDULE_WINDOW_END", False),  # no continuation: finalized as before
        ("manual", True, "SCHEDULE_WINDOW_END", False),
        ("schedule", True, "RUN_DURATION_LIMIT", False),  # the run's own budget: finalized
        ("schedule", True, "RUN_CREDIT_LIMIT", False),
    ],
)
def test_which_stops_leave_the_run_for_the_next_execution(
    trigger: str, continue_unfinished: bool, code: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched = {
        "enabled": True,
        "weekdays": [1],
        "start_time": "06:00",
        "continue_unfinished": continue_unfinished,
    }
    run = _run(trigger, sched)
    monkeypatch.setattr(
        operations, "collection_of", lambda r: StoreCollection.model_validate(r.config_snapshot["collection"])
    )
    assert operations.continues_later(run, code) is expected


def test_the_daily_window_is_open_on_any_day_between_its_start_and_end() -> None:
    coll = StoreCollection(
        schedule={"enabled": True, "weekdays": [1], "start_time": "06:00", "window_end": "18:00"}
    )
    assert operations.daily_window_open(coll, datetime(2026, 7, 16, 14, tzinfo=UTC))  # Thursday 09:00 local
    assert not operations.daily_window_open(
        coll, datetime(2026, 7, 16, 3, tzinfo=UTC)
    )  # Wednesday 22:00 local
    assert not operations.daily_window_open(coll, datetime(2026, 7, 16, 23, 30, tzinfo=UTC))  # 18:30 local
