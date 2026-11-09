"""Release 1.9.0 (M8): what the shipped schedule lets one run collect before the next occurrence supersedes it
(pure functions; no database, no provider). These tests state the current failure mode: with the shipped
Monday/Thursday 07:00-19:00 schedule and its 48-hour run limit, the full-catalog workload estimated at 48.4 to
77.3 active hours with one worker cannot finish between two occurrences, so each run is closed unfinished."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from marianos_headless.collection.schedule import capacity, next_occurrence, occurrence_on
from marianos_headless.config_file import LoadedConfig

ROOT = Path(__file__).resolve().parents[2]
CHICAGO = ZoneInfo("America/Chicago")
PICKUP = "marianos-53100502-pickup"
ESTIMATE = (48.4, 77.3)  # active hours of a full run with brand partitions, one worker (planning estimate)


@pytest.fixture(scope="module")
def shipped() -> tuple[object, int | None]:
    coll = LoadedConfig(ROOT / "config" / "collector.yaml").collector.collections[PICKUP]
    assert coll.schedule.enabled is False  # shipped off; the capacity is computed as if it were enabled
    assert coll.timezone == "America/Chicago"
    return coll.schedule.model_copy(update={"enabled": True}), coll.limits.max_run_minutes


def test_the_shipped_schedule_and_limits_are_the_ones_reviewed(shipped: tuple[object, int | None]) -> None:
    schedule, max_run = shipped
    assert schedule.weekdays == [0, 3] and schedule.start_time == "07:00"  # type: ignore[attr-defined]
    assert schedule.window_end == "19:00" and schedule.continue_unfinished  # type: ignore[attr-defined]
    assert max_run == 2880


def test_monday_to_thursday_gives_36_collection_hours_of_72_elapsed(
    shipped: tuple[object, int | None],
) -> None:
    schedule, max_run = shipped
    occ = occurrence_on(schedule, date(2026, 11, 9), CHICAGO)  # type: ignore[arg-type]
    assert occ is not None
    cap = capacity(schedule, occ, CHICAGO, max_run_minutes=max_run)  # type: ignore[arg-type]
    assert cap.next_start == datetime(2026, 11, 12, 7, tzinfo=CHICAGO)
    assert (cap.elapsed_hours, cap.window_hours, cap.run_limit_hours, cap.usable_hours) == (72, 36, 48, 36)
    assert not any(cap.fits(h) for h in ESTIMATE)  # superseded unfinished at Thursday 07:00


def test_thursday_to_monday_gives_48_collection_hours_still_short(shipped: tuple[object, int | None]) -> None:
    schedule, max_run = shipped
    occ = occurrence_on(schedule, date(2026, 11, 12), CHICAGO)  # type: ignore[arg-type]
    assert occ is not None
    cap = capacity(schedule, occ, CHICAGO, max_run_minutes=max_run)  # type: ignore[arg-type]
    assert (cap.elapsed_hours, cap.window_hours, cap.usable_hours) == (96, 48, 48)
    assert not any(cap.fits(h) for h in ESTIMATE)  # even the lower estimate exceeds the window and the limit


@pytest.mark.parametrize(
    ("thursday", "elapsed"),
    [
        (date(2026, 10, 29), 97),  # daylight time ends on Sunday 2026-11-01: one hour more
        (date(2027, 3, 11), 95),  # daylight time starts on Sunday 2027-03-14: one hour less
    ],
)
def test_a_daylight_saving_change_moves_the_elapsed_time_not_the_local_windows(
    shipped: tuple[object, int | None], thursday: date, elapsed: int
) -> None:
    schedule, max_run = shipped
    occ = occurrence_on(schedule, thursday, CHICAGO)  # type: ignore[arg-type]
    assert occ is not None
    cap = capacity(schedule, occ, CHICAGO, max_run_minutes=max_run)  # type: ignore[arg-type]
    assert cap.elapsed_hours == elapsed and cap.window_hours == 48
    nxt = next_occurrence(schedule, occ.start, CHICAGO)  # type: ignore[arg-type]
    assert nxt is not None and nxt.start.hour == 7  # 07:00 local on both sides of the change
    assert occ.start.astimezone(UTC).hour != nxt.start.astimezone(UTC).hour


def test_without_continuation_a_run_has_only_its_first_window(shipped: tuple[object, int | None]) -> None:
    schedule, _ = shipped
    once = schedule.model_copy(update={"continue_unfinished": False})  # type: ignore[attr-defined]
    occ = occurrence_on(once, date(2026, 11, 9), CHICAGO)
    assert occ is not None
    assert capacity(once, occ, CHICAGO).window_hours == 12


def test_even_an_all_day_window_cannot_hold_the_upper_estimate_twice_a_week(
    shipped: tuple[object, int | None],
) -> None:
    # The capacity change the cadence needs: a window open all day gives Monday 07:00 to Thursday 07:00 its
    # 72 elapsed hours, still short of 77.3 hours with one worker (and of any run limit below that).
    schedule, _ = shipped
    open_all_day = schedule.model_copy(update={"window_start": "00:00", "window_end": None})  # type: ignore[attr-defined]
    occ = occurrence_on(open_all_day, date(2026, 11, 9), CHICAGO)
    assert occ is not None
    cap = capacity(open_all_day, occ, CHICAGO)
    assert cap.window_hours == 72 and cap.fits(ESTIMATE[0]) and not cap.fits(ESTIMATE[1])
