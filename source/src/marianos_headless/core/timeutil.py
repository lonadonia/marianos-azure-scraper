"""Time helpers. All stored timestamps are UTC; ``crawl_date`` is the store-local date (Q-10)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


def store_local_date(observed_at: datetime, timezone: str) -> str:
    """``YYYY-MM-DD`` of ``observed_at`` in the store's timezone."""
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return observed_at.astimezone(ZoneInfo(timezone)).date().isoformat()


def iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")
