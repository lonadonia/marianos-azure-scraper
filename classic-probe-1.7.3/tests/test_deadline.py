"""The session clock and Retry-After (1.7.0, findings C3 and C5). OFFLINE."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from classic_probe.deadline import DeadlinePassed, SessionClock, parse_retry_after
from tests.conftest import FakeClock


class Mono:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make(
    wall: FakeClock, mono: Mono, minutes: float = 10, reserve_s: float = 60
) -> tuple[SessionClock, list[float]]:
    slept: list[float] = []

    def sleeper(s: float) -> None:
        slept.append(s)
        mono.t += s
        wall.advance(s)

    clock = SessionClock(
        wall() + timedelta(minutes=minutes),
        export_reserve_s=reserve_s,
        wall=wall,
        monotonic=mono,
        sleeper=sleeper,
    )
    return clock, slept


def test_a_wall_clock_jump_backwards_never_extends_the_session(clock: FakeClock) -> None:
    mono = Mono()
    session, _ = make(clock, mono)
    mono.t += 300  # five minutes really pass ...
    clock.advance(-3600)  # ... while the wall clock is set back an hour
    assert session.remaining() == pytest.approx(300)  # the monotonic reading bounds it
    assert session.dispatch_remaining() == pytest.approx(240)


def test_a_wall_clock_jump_forwards_ends_the_session_early(clock: FakeClock) -> None:
    mono = Mono()
    session, _ = make(clock, mono)
    clock.advance(570)  # the wall clock says the end is 30 s away
    assert session.remaining() == pytest.approx(30)
    with pytest.raises(DeadlinePassed):
        session.allowance(120)  # 30 s left is inside the 60 s kept for export and cleanup


def test_an_allowance_is_clamped_to_the_time_before_the_reserve(clock: FakeClock) -> None:
    mono = Mono()
    session, _ = make(clock, mono)
    assert session.allowance(120) == 120
    mono.t += 480
    clock.advance(480)
    assert session.allowance(120) == pytest.approx(60)


def test_a_backoff_really_waits_and_never_past_the_deadline(clock: FakeClock) -> None:
    mono = Mono()
    session, slept = make(clock, mono)
    assert session.sleep(5, then_needs_s=1) is True and slept == [5]
    mono.t += 525
    clock.advance(525)  # 10 s left before the reserve
    assert session.sleep(9.5, then_needs_s=1) is False and slept == [5]  # not slept at all
    assert session.sleep(-3) is True and slept == [5, 0.0]


def test_the_default_sleeper_is_the_real_one() -> None:
    import time

    session = SessionClock(datetime.now(UTC) + timedelta(minutes=5), export_reserve_s=10)
    assert session.sleeper is time.sleep
    t0 = time.monotonic()
    assert session.sleep(0.3) is True
    assert time.monotonic() - t0 >= 0.29


def test_retry_after_is_read_in_both_documented_forms() -> None:
    now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    assert parse_retry_after("7", now) == 7.0
    assert parse_retry_after("Tue, 03 Nov 2026 12:00:30 GMT", now) == 30.0
    assert parse_retry_after("Tue, 03 Nov 2026 11:59:00 GMT", now) == 0.0  # already past
    for bad in (None, "", "soon", "-5", "1.5e9x"):
        assert parse_retry_after(bad, now) is None
