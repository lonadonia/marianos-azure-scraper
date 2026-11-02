"""When scheduled collection may start and run (pure functions over :class:`Schedule`).

An occurrence is a scheduled weekday inside the optional date range. Its run starts at the start time
and may collect until the daily window ends (the end of the day when no end is set). Times are local
to the collection timezone, with daylight-saving changes handled by ``zoneinfo``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
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
