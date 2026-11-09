"""One session deadline for everything a campaign does (1.7.0, findings C2, C3 and C5; 1.7.1, C2).

The deadline is durable: it is derived from the campaign's start recorded once in the ledger, so a restart
never grants a new window. Inside a process it is held on the monotonic clock (a wall-clock jump cannot
extend it), and the ledger checks the wall clock again under its write lock. Every wait (lock, request,
backoff) is clamped to the time left before the reserve kept for export and cleanup.

1.7.1: the same deadline also bounds what follows the requests. The end of the session is split in three:

- until ``end - export_reserve``: requests, their lock waits and backoffs
  (:meth:`SessionClock.dispatch_remaining`);
- until ``end - recovery_reserve``: the session's own ledger writes (an answer's index and settlement, a
  stop, the export's index of a kept copy; :meth:`SessionClock.write_remaining`). After that, the ledger is
  left to a supervisor's recovery, which never has to wait for the session's writes;
- until ``end``: the session's reads of the ledger and of its own files (the export checks each capture while
  5 s are left and writes its manifest, a local file, while 1 s is left), and a supervisor's recovery after it
  kills a session that did not end in time (supervisor.py), in a file of its own.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

RECOVERY_RESERVE_S = 30.0  # 1.7.1 (C2): at most this much of the end is kept for a supervisor's recovery


def recovery_reserve(export_reserve_s: float) -> float:
    """The last part of the export reserve, kept for a recovery after a kill: 30 s, or a third if less."""
    return max(0.0, min(RECOVERY_RESERVE_S, export_reserve_s / 3))


class DeadlinePassed(RuntimeError):
    """No time is left for this step: nothing was started."""


class SessionClock:
    def __init__(
        self,
        end_wall: datetime,
        *,
        export_reserve_s: float,
        wall: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        recovery_reserve_s: float = 0.0,
    ) -> None:
        self.wall = wall or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.sleeper = sleeper  # the real sleep unless a test injects a fake one (C5)
        self.export_reserve_s = export_reserve_s
        self.recovery_reserve_s = recovery_reserve_s
        self.end_wall = end_wall
        self._end_mono = monotonic() + (end_wall - self.wall()).total_seconds()

    def remaining(self) -> float:
        """Seconds until the session's end (export and cleanup included)."""
        return min(self._end_mono - self.monotonic(), (self.end_wall - self.wall()).total_seconds())

    def dispatch_remaining(self) -> float:
        """Seconds a request, a lock wait or a backoff may still use: the end less the export reserve."""
        return self.remaining() - self.export_reserve_s

    def write_remaining(self) -> float:
        """Seconds the session's own ledger writes may still use (1.7.1, C2): the end less the part kept for a
        supervisor's recovery."""
        return self.remaining() - self.recovery_reserve_s

    def allowance(self, cap_s: float) -> float:
        """A request's whole allowance (connect, read and decode), clamped; raises when none is left."""
        left = min(cap_s, self.dispatch_remaining())
        if left <= 0:
            raise DeadlinePassed("no time is left before the reserve kept for export and cleanup")
        return left

    def sleep(self, seconds: float, *, then_needs_s: float = 0.0) -> bool:
        """A real, bounded backoff. False (and no sleep) when the wait plus what must follow it would end
        past the dispatch deadline: the caller then stops instead of retrying late."""
        if seconds < 0:
            seconds = 0.0
        if seconds + then_needs_s > self.dispatch_remaining():
            return False
        self.sleeper(seconds)
        return self.dispatch_remaining() > then_needs_s


def parse_retry_after(value: str | None, now: datetime) -> float | None:
    """Seconds from a ``Retry-After`` header (delta-seconds or an HTTP-date); None when absent or invalid."""
    if not value:
        return None
    v = value.strip()
    if v.isdigit():
        return float(v)
    from email.utils import parsedate_to_datetime

    try:
        when = parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())
