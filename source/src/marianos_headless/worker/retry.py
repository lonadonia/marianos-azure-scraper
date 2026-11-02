"""Retry policy and circuit breaker (brief §5.11).

- 5xx and timeouts: up to ``max_attempts_per_task`` with exponential backoff (base 10 s, cap 300 s).
- 429: no immediate retry. The category pauses for the site's ``Retry-After`` (at least
  ``backoff_base_s``), or ``pause_on_429_s`` when the site gave none; a requested pause longer than
  ``max_retry_after_s`` blocks the category instead of retrying early, and so does a second 429.
- Challenge or denial: never retried, the task is BLOCKED.
- ``consecutive_failures_to_fail_category`` consecutive failures in a category → category FAILED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from marianos_headless.core.settings import CircuitBreakerSettings, RetrySettings


class FailureKind(StrEnum):
    CHALLENGE = "challenge"
    RATE_LIMITED = "rate_limited"
    TRANSIENT = "transient"  # 5xx, timeouts, network errors
    PERMANENT = "permanent"  # parser/contract errors, 4xx other than 429


class TaskFailure(Exception):
    def __init__(self, kind: FailureKind, message: str, *, retry_after_s: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class RetryDecision:
    action: str  # retry | block | fail
    delay_s: float | None = None
    reason: str = ""


def backoff_delay(attempt: int, base_s: float, cap_s: float) -> float:
    """attempt 1 → base, 2 → 2·base, … capped."""
    return float(min(cap_s, base_s * (2 ** max(0, attempt - 1))))


def decide(
    failure: TaskFailure, attempts: int, policy: RetrySettings, *, rate_limited_before: bool
) -> RetryDecision:
    if failure.kind is FailureKind.CHALLENGE:
        return RetryDecision("block", None, "challenge or denial: never retried")
    if failure.kind is FailureKind.RATE_LIMITED:
        if rate_limited_before:
            return RetryDecision("block", None, "second 429 in this category")
        if failure.retry_after_s is None:
            return RetryDecision("retry", policy.pause_on_429_s, "429: category paused")
        if failure.retry_after_s > policy.max_retry_after_s:
            return RetryDecision(
                "block",
                None,
                f"429: the site asks for a {failure.retry_after_s:.0f} s pause, longer than the "
                f"{policy.max_retry_after_s:.0f} s a run may wait",
            )
        wait = max(failure.retry_after_s, policy.backoff_base_s)
        return RetryDecision("retry", wait, "429: category paused as the site asked (Retry-After)")
    if failure.kind is FailureKind.TRANSIENT and attempts < policy.max_attempts_per_task:
        return RetryDecision(
            "retry", backoff_delay(attempts, policy.backoff_base_s, policy.backoff_max_s), "transient failure"
        )
    return RetryDecision("fail", None, "permanent failure or attempts exhausted")


@dataclass
class CircuitBreaker:
    settings: CircuitBreakerSettings
    consecutive: dict[str, int] = field(default_factory=dict)
    open_categories: set[str] = field(default_factory=set)
    challenges: int = 0

    def record_success(self, category: str) -> None:
        self.consecutive[category] = 0

    def record_failure(self, category: str) -> bool:
        """Returns True when the category's circuit opens (category FAILED)."""
        n = self.consecutive.get(category, 0) + 1
        self.consecutive[category] = n
        if n >= self.settings.consecutive_failures_to_fail_category:
            self.open_categories.add(category)
            return True
        return False

    def record_challenge(self) -> bool:
        """Returns True when the run must abort (``challenge_pages_to_abort_run`` reached)."""
        self.challenges += 1
        return self.challenges >= self.settings.challenge_pages_to_abort_run

    def is_open(self, category: str) -> bool:
        return category in self.open_categories
