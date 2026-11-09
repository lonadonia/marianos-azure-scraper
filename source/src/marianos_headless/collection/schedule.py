"""When scheduled collection may start and run (pure functions over :class:`Schedule`).

An occurrence is a scheduled weekday inside the optional date range. Its run starts at the start time
and may collect until the daily window ends (the end of the day when no end is set). Times are local
to the collection timezone, with daylight-saving changes handled by ``zoneinfo``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from marianos_headless.collection.config import Schedule, parse_hhmm


@dataclass(frozen=True)
class Occurrence:
    day: date
    start: datetime  # aware, local
    window_start: datetime
    window_end: datetime

    def as_dict(self) -> dict[str, str]:
        return {
            "day": self.day.isoformat(),
            "start": self.start.isoformat(),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
        }


def _at(day: date, clock: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, clock, tzinfo=tz)


def occurrence_on(schedule: Schedule, day: date, tz: ZoneInfo) -> Occurrence | None:
    if not schedule.enabled or day.weekday() not in schedule.weekdays:
        return None
    if (schedule.start_date and day < schedule.start_date) or (schedule.end_date and day > schedule.end_date):
        return None
    start = _at(day, parse_hhmm(schedule.start_time), tz)
    w_start = _at(day, parse_hhmm(schedule.window_start or schedule.start_time), tz)
    w_end = (
        _at(day, parse_hhmm(schedule.window_end), tz)
        if schedule.window_end
        else _at(day + timedelta(days=1), time(0, 0), tz)
    )
    return Occurrence(day, start, w_start, w_end)


def local_day(now: datetime, tz: ZoneInfo) -> date:
    return now.astimezone(tz).date()


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The local calendar day as an aware [start, end) interval."""
    return _at(day, time(0, 0), tz), _at(day + timedelta(days=1), time(0, 0), tz)


def current_occurrence(schedule: Schedule, now: datetime, tz: ZoneInfo) -> Occurrence | None:
    """Today's occurrence once its start time has passed and while its window is open."""
    occ = occurrence_on(schedule, local_day(now, tz), tz)
    if occ is None or now < occ.start or now >= occ.window_end:
        return None
    return occ


def in_window(schedule: Schedule, now: datetime, tz: ZoneInfo) -> bool:
    occ = occurrence_on(schedule, local_day(now, tz), tz)
    return occ is not None and occ.window_start <= now < occ.window_end


def next_occurrence(
    schedule: Schedule, now: datetime, tz: ZoneInfo, horizon_days: int = 400
) -> Occurrence | None:
    """The next occurrence whose start is still ahead (today's, if it has not started yet)."""
    today = local_day(now, tz)
    for i in range(horizon_days):
        occ = occurrence_on(schedule, today + timedelta(days=i), tz)
        if occ is not None and occ.start > now:
            return occ
        if schedule.end_date and today + timedelta(days=i) > schedule.end_date:
            break
    return None


@dataclass(frozen=True)
class Capacity:
    """Release 1.9.0 (M8): what one occurrence's run can collect before the next occurrence closes it.

    ``window_hours``: the hours inside the daily windows from the occurrence's start to the next occurrence's
    start (the continuation days included when the schedule continues unfinished runs), as elapsed time, so a
    daylight-saving change counts as it happens. ``usable_hours`` is that, capped by the run's own limit."""

    occurrence: Occurrence
    next_start: datetime | None
    elapsed_hours: float
    window_hours: float
    run_limit_hours: float | None
    usable_hours: float

    def fits(self, active_hours: float) -> bool:
        """Whether a run needing ``active_hours`` of collection can finish before it is superseded."""
        return active_hours <= self.usable_hours

    def as_dict(self) -> dict[str, object]:
        return {
            "occurrence": self.occurrence.as_dict(),
            "next_start": self.next_start.isoformat() if self.next_start else None,
            "elapsed_hours": round(self.elapsed_hours, 3),
            "window_hours": round(self.window_hours, 3),
            "run_limit_hours": self.run_limit_hours,
            "usable_hours": round(self.usable_hours, 3),
        }


def _elapsed_s(a: datetime, b: datetime) -> float:
    """Elapsed seconds from ``a`` to ``b``. Python subtracts two datetimes of the same zone as wall-clock
    times (a daylight-saving change ignored): both are converted to UTC first."""
    return (b.astimezone(UTC) - a.astimezone(UTC)).total_seconds()


def capacity(
    schedule: Schedule, occ: Occurrence, tz: ZoneInfo, *, max_run_minutes: int | None = None
) -> Capacity:
    """The collection hours ``occ``'s run has before the next occurrence starts (see :class:`Capacity`)."""
    nxt = next_occurrence(schedule, occ.start, tz)
    end = nxt.start if nxt is not None else occ.window_end
    w_start_clock = parse_hhmm(schedule.window_start or schedule.start_time)
    seconds = 0.0
    day = occ.day
    while _at(day, time(0, 0), tz) < end:
        w_start = max(_at(day, w_start_clock, tz), occ.start)
        w_end = (
            _at(day, parse_hhmm(schedule.window_end), tz)
            if schedule.window_end
            else _at(day + timedelta(days=1), time(0, 0), tz)
        )
        seconds += max(0.0, _elapsed_s(w_start, min(w_end, end)))
        if not schedule.continue_unfinished:
            break
        day += timedelta(days=1)
    window = seconds / 3600
    limit = None if max_run_minutes is None else max_run_minutes / 60
    return Capacity(
        occurrence=occ,
        next_start=nxt.start if nxt is not None else None,
        elapsed_hours=_elapsed_s(occ.start, end) / 3600,
        window_hours=window,
        run_limit_hours=limit,
        usable_hours=window if limit is None else min(window, limit),
    )
