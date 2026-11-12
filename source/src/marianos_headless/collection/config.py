"""What one run of a store collects: categories, subcategories, limits, the timezone of its days, and its
store-local schedule (read by the schedule guard of ``run --scheduled``; Azure starts the job).

Empty limits mean no limit: production collects the store's full configured scope. Small test limits are
set in the configuration file or on the command line for one run; they are recorded with the run and a run
they bound is labelled a pilot, never a complete catalogue.
"""

from __future__ import annotations

import re
from datetime import date, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Limits(_Model):
    """Empty means no limit. Products are unique verified products of the store (a product seen again in
    the same run, or again on the same day, is not counted twice). Credits are the provider's credits as
    it charged them; the reserve is checked against the account balance."""

    max_products_per_run: int | None = Field(None, ge=1)
    max_products_per_day: int | None = Field(None, ge=1)
    # Total active collection time of the run, over all its executions (segments).
    max_run_minutes: int | None = Field(None, ge=1, le=14 * 24 * 60)
    # One execution (segment) of the run; reaching it pauses the run resumably and the next execution
    # (``resume``, or the schedule's continuation) goes on from the checkpoints. Not a scope limit.
    max_segment_minutes: int | None = Field(None, ge=1, le=7 * 24 * 60)
    max_credits_per_run: int | None = Field(None, ge=5)
    max_credits_per_day: int | None = Field(None, ge=5)
    min_credit_reserve: int = Field(0, ge=0)
    # Bounded (pilot) runs: page steps read per listing (the first load and each "Load More"). A listing
    # stopped by it is incomplete and the run is a pilot.
    max_pages_per_listing: int | None = Field(None, ge=1)
    # Release 1.9.0 (M8): listing tasks one worker reads at once, each with at most one provider request in
    # flight (so at most this many requests are in flight). 1 = one listing at a time (the default and the
    # behaviour of every earlier release). Preflight, assembly and validation always run alone.
    max_concurrent_listings: int = Field(1, ge=1, le=4)
    # Release 1.9.0 (M4): product pages read for coupon terms in one run (``coverage.read_product_terms``);
    # empty: one for each product whose card shows a digital coupon; 0: none. Not a scope limit: a product
    # whose terms were not read is still recorded, flagged DIGITAL_TERMS_UNREAD with the reason.
    # Release 1.9.0rc3: on the tile served since 2026-11-06 (no coupon shown) every product is a candidate.
    max_product_term_reads: int | None = Field(None, ge=0)
    # Release 1.10.0 (C1): how many times one listing request is asked again later in the same run when a
    # later page answers with an earlier page's products, or when the first page of a listing above the
    # source's window carries no filter to subdivide it by (``collection.reask``). Empty or 0 (the default,
    # and the behaviour of every earlier release): never; at most 2. Each re-ask is one more submission, sent
    # once, reserved and checked against every limit like any other. Not a scope limit.
    max_reasks_per_request: int | None = Field(None, ge=0, le=2)
    # The shortest wait before a request is asked again, counted from its previous answer or attempt, in
    # seconds; empty: 300, which is also the least a configuration may set.
    reask_min_wait_seconds: int | None = Field(None, ge=300, le=3600)

    def bounded(self) -> bool:
        """True when a limit narrows the scope (the run is then a pilot, never a complete catalogue)."""
        return any(v is not None for v in (self.max_products_per_run, self.max_pages_per_listing))


def parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


class Schedule(_Model):
    """Runs start at ``start_time`` (store-local) on the chosen weekdays, between the optional start and end
    dates. A scheduled run may collect only inside the daily window (``window_start``, default the start
    time, to ``window_end``, default the end of the day); at the window's end it stops resumably."""

    enabled: bool = False
    weekdays: list[int] = Field(default_factory=list)  # 0 = Monday … 6 = Sunday
    start_time: str = "09:00"
    window_start: str | None = None
    window_end: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    # A scheduled run not finished by its first execution (its segment limit, the window's end, an
    # interruption) is continued by later executions, inside the daily window of each day, until the
    # next occurrence starts; that occurrence then closes it as partial (never published, its verified
    # products carried forward) and starts the next run.
    continue_unfinished: bool = True
    # The next run reads first the listings no earlier run read to its end (the backlog an unfinished run
    # left), then the others, the one read longest ago first (release 1.5.0; false: the CSV's order).
    backlog_first: bool = True

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekdays are 0 (Monday) to 6 (Sunday)")
        return sorted(set(v))

    @field_validator("start_time", "window_start", "window_end")
    @classmethod
    def _clock(cls, v: str | None) -> str | None:
        if v is not None and not _HHMM.match(v):
            raise ValueError("times are HH:MM (24-hour)")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> Schedule:
        if self.enabled and not self.weekdays:
            raise ValueError("choose at least one weekday to enable the schedule")
        start = parse_hhmm(self.window_start or self.start_time)
        if parse_hhmm(self.start_time) < start:
            raise ValueError("the start time must be inside the daily window")
        if self.window_end is not None and parse_hhmm(self.window_end) <= parse_hhmm(self.start_time):
            raise ValueError("the daily window must end after the start time")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("the schedule end date is before its start date")
        return self


class CollectionConfig(_Model):
    categories: list[int] = Field(default_factory=list)  # client CSV rows; empty = every category
    subcategories: dict[str, list[str]] = Field(default_factory=dict)  # row -> listing URLs; absent = all
    timezone: str = "America/Chicago"
    limits: Limits = Field(default_factory=Limits)
    schedule: Schedule = Field(default_factory=Schedule)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown timezone {v!r}") from None
        return v

    @field_validator("categories")
    @classmethod
    def _rows(cls, v: list[int]) -> list[int]:
        return sorted(set(v))

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
