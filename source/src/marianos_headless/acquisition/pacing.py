"""Politeness pacing between navigations (brief §3.5, §5.11)."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from statistics import median


class NavigationBudgetExceeded(RuntimeError):
    pass


class Pacer:
    """Ensures at least ``min_interval + U(0, jitter)`` seconds between navigation starts."""

    def __init__(
        self,
        min_interval_s: float,
        jitter_s: float,
        *,
        max_navigations: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ):
        if min_interval_s < 1.0:
            raise ValueError("min interval below 1 s is not allowed")
        self.min_interval_s = min_interval_s
        self.jitter_s = jitter_s
        self.max_navigations = max_navigations
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._last: float | None = None
        self.count = 0
        self.waits: list[float] = []

    async def wait_turn(self) -> float:
        if self.max_navigations is not None and self.count >= self.max_navigations:
            raise NavigationBudgetExceeded(f"navigation budget of {self.max_navigations} reached")
        waited = 0.0
        if self._last is not None:
            due = self._last + self.min_interval_s + self._rng.uniform(0, self.jitter_s)
            waited = max(0.0, due - self._clock())
            if waited:
                await self._sleep(waited)
        self._last = self._clock()
        self.count += 1
        self.waits.append(waited)
        return waited


class LatencyWatch:
    """ABNORMAL_LATENCY: median of the last 20 navigations > 3x the run's first-20 baseline."""

    def __init__(self, window: int = 20, factor: float = 3.0):
        self.window = window
        self.factor = factor
        self.samples: list[float] = []

    def add(self, seconds: float) -> bool:
        self.samples.append(seconds)
        if len(self.samples) < 2 * self.window:
            return False
        baseline = median(self.samples[: self.window])
        recent = median(self.samples[-self.window :])
        return recent > self.factor * baseline
