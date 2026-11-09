"""Collection settings, the schedule, limits, the key encryption, the listing plan and the Scrapfly
account states. Pure functions; no database, browser or network."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from marianos_headless.acquisition.scrapfly import AccountUsage
from marianos_headless.collection import scrapfly_account
from marianos_headless.collection.config import CollectionConfig, Limits, Schedule
from marianos_headless.collection.limits import (
    RESUMABLE,
    SUSPENDS_SCHEDULE,
    TRANSIENT,
    StopCode,
    Usage,
    credit_room,
    first_stop,
    product_room,
    stop_text,
)
from marianos_headless.collection.nodes import load_seed, plan_nodes
from marianos_headless.collection.schedule import (
    current_occurrence,
    day_bounds,
    in_window,
    next_occurrence,
    occurrence_on,
)
from marianos_headless.core.paths import config_dir

CHICAGO = ZoneInfo("America/Chicago")


# -- settings ---------------------------------------------------------------------------------------


def test_a_new_installation_collects_nothing_until_configured() -> None:
    cfg = CollectionConfig()
    assert cfg.categories == [] and cfg.schedule.enabled is False
    assert cfg.limits == Limits() and all(
        v is None
        for k, v in cfg.limits.model_dump().items()
        if k not in ("min_credit_reserve", "max_concurrent_listings")
    )
    assert cfg.limits.min_credit_reserve == 0 and cfg.timezone == "America/Chicago"
    assert cfg.limits.max_concurrent_listings == 1  # 1.9.0: one listing at a time unless configured


@pytest.mark.parametrize(
    "schedule",
    [
        {"enabled": True, "weekdays": []},
        {"weekdays": [7]},
        {"start_time": "9:00"},
        {"start_time": "09:00", "window_end": "08:00"},
        {"start_time": "08:00", "window_start": "09:00"},
        {"start_date": "2026-11-02", "end_date": "2026-11-01"},
    ],
)
def test_inconsistent_schedules_are_refused(schedule: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Schedule.model_validate(schedule)


@pytest.mark.parametrize(
    "limits", [{"max_products_per_run": 0}, {"max_credits_per_day": 1}, {"min_credit_reserve": -1}]
)
def test_limits_must_be_positive(limits: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Limits.model_validate(limits)


def test_unknown_timezones_and_extra_fields_are_refused() -> None:
    with pytest.raises(ValidationError):
        CollectionConfig.model_validate({"timezone": "Mars/Base"})
    with pytest.raises(ValidationError):
        CollectionConfig.model_validate({"max_products": 50})  # no hidden or misspelled limits


# -- schedule ---------------------------------------------------------------------------------------

TUE_FRI = Schedule(enabled=True, weekdays=[1, 4], start_time="09:00", window_end="17:00")


def test_occurrences_follow_the_weekdays_dates_and_window() -> None:
    tue = date(2026, 10, 20)  # a Tuesday
    occ = occurrence_on(TUE_FRI, tue, CHICAGO)
    assert occ is not None and occ.start == datetime(2026, 10, 20, 9, 0, tzinfo=CHICAGO)
    assert occ.window_end == datetime(2026, 10, 20, 17, 0, tzinfo=CHICAGO)
    assert occurrence_on(TUE_FRI, tue + timedelta(days=1), CHICAGO) is None
    bounded = TUE_FRI.model_copy(update={"start_date": date(2026, 10, 21), "end_date": date(2026, 10, 31)})
    assert occurrence_on(bounded, tue, CHICAGO) is None
    assert occurrence_on(bounded, date(2026, 10, 23), CHICAGO) is not None
    assert occurrence_on(TUE_FRI.model_copy(update={"enabled": False}), tue, CHICAGO) is None


def test_a_run_is_due_only_inside_its_window() -> None:
    before = datetime(2026, 10, 20, 13, 59, tzinfo=UTC)  # 08:59 CDT
    during = datetime(2026, 10, 20, 14, 30, tzinfo=UTC)
    after = datetime(2026, 10, 20, 22, 0, tzinfo=UTC)  # 17:00 CDT
    assert current_occurrence(TUE_FRI, before, CHICAGO) is None
    assert current_occurrence(TUE_FRI, during, CHICAGO) is not None
    assert current_occurrence(TUE_FRI, after, CHICAGO) is None
    assert in_window(TUE_FRI, during, CHICAGO) and not in_window(TUE_FRI, after, CHICAGO)


def test_the_next_run_respects_daylight_saving_time() -> None:
    sat = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
    nxt = next_occurrence(TUE_FRI, sat, CHICAGO)
    assert nxt is not None and nxt.day == date(2026, 11, 3)  # the Tuesday after the clocks change
    assert nxt.start.astimezone(UTC).hour == 15  # 09:00 CST = 15:00 UTC (was 14:00 UTC in CDT)
    ended = TUE_FRI.model_copy(update={"end_date": date(2026, 11, 1)})
    assert next_occurrence(ended, sat, CHICAGO) is None


def test_a_day_is_the_local_calendar_day() -> None:
    start, end = day_bounds(date(2026, 3, 8), CHICAGO)  # 23 hours long (spring forward)
    assert end.astimezone(UTC) - start.astimezone(UTC) == timedelta(hours=23)


# -- limits -----------------------------------------------------------------------------------------


def test_the_first_limit_reached_is_reported_with_its_figures() -> None:
    limits = Limits(max_products_per_run=100, max_products_per_day=150, max_run_minutes=30)
    assert first_stop(limits, Usage(run_products=99), account_remaining=None) is None
    code, detail = first_stop(limits, Usage(run_products=100), account_remaining=None) or ("", "")
    assert code is StopCode.RUN_PRODUCT_LIMIT and "100 verified products in this run" in detail
    code, _ = first_stop(limits, Usage(run_products=10, day_products=150), account_remaining=None) or ("", "")
    assert code is StopCode.DAILY_PRODUCT_LIMIT
    code, detail = first_stop(limits, Usage(run_active_s=1800), account_remaining=None) or ("", "")
    assert code is StopCode.RUN_DURATION_LIMIT and "30 minutes" in detail


def test_product_room_is_the_smaller_of_the_run_and_day_room() -> None:
    limits = Limits(max_products_per_run=100, max_products_per_day=40)
    assert product_room(limits, Usage(run_products=10, day_products=25)) == 15
    assert product_room(Limits(), Usage(run_products=10)) is None
    assert product_room(limits, Usage(run_products=120, day_products=0)) == 0


def test_credit_room_takes_the_tightest_budget_and_the_reserve() -> None:
    limits = Limits(max_credits_per_run=500, max_credits_per_day=800, min_credit_reserve=100)
    room, code = credit_room(limits, Usage(run_credits=450, day_credits=600), account_remaining=2000)
    assert (room, code) == (50, StopCode.RUN_CREDIT_LIMIT)
    room, code = credit_room(limits, Usage(run_credits=10, day_credits=790), account_remaining=2000)
    assert (room, code) == (10, StopCode.DAILY_CREDIT_LIMIT)
    room, code = credit_room(limits, Usage(), account_remaining=130)
    assert (room, code) == (30, StopCode.CREDIT_RESERVE)
    assert credit_room(Limits(), Usage(), account_remaining=None) == (None, None)
    room, code = credit_room(Limits(), Usage(), account_remaining=3)
    assert (room, code) == (3, StopCode.CREDITS_EXHAUSTED)
    stop = first_stop(limits, Usage(run_credits=450), account_remaining=2000, min_step_credits=60)
    assert stop is not None and stop[0] is StopCode.RUN_CREDIT_LIMIT  # the next step could cross it


def test_stop_classes_are_consistent() -> None:
    assert TRANSIENT <= RESUMABLE
    assert not (SUSPENDS_SCHEDULE & TRANSIENT)
    assert StopCode.SITE_REFUSAL not in RESUMABLE and StopCode.STORE_NOT_VERIFIED not in RESUMABLE
    assert all(stop_text(c.value) for c in StopCode) and stop_text(None) is None


# -- secret box -------------------------------------------------------------------------------------


# -- listing plan -----------------------------------------------------------------------------------


def test_the_plan_lists_every_menu_subcategory_and_names_what_it_cannot_collect() -> None:
    seed = load_seed()
    sources = {r["row_index"]: (r["category"], f"id{r['row_index']}") for r in seed["rows"]}
    nodes, skipped = plan_nodes(seed, sources, [], {})
    assert len({n.url for n in nodes}) == len(nodes) and len(nodes) > 250
    assert {n.category for n in nodes} >= {"Grocery", "Dairy", "Beverages"}
    reasons = {s.get("category"): s["reason"] for s in skipped if "sub_category" not in s}
    assert {"Coupons", "Candles Home Fragrances", "Batteries"} <= set(reasons)
    assert "not collected" in reasons["Coupons"]
    canned = next(n for n in nodes if n.sub_category == "Canned Foods")
    assert canned.url == "https://www.marianos.com/pl/canned-foods/01006?pzn=relevance"
    only, _ = plan_nodes(seed, sources, [8], {"8": ["02001"]})
    assert [(n.category, n.sub_category) for n in only] == [("Dairy", "Milk & Plant-based Milk")]


def test_a_csv_row_that_is_itself_a_listing_page_is_planned_and_the_coupons_row_says_why_not() -> None:
    seed = load_seed()
    csv_rows = list(csv.DictReader((config_dir() / "Marianos_Category_URLs.csv").open(encoding="utf-8")))
    sources = {i: (r["Category (Auto)"], f"id{i}", r["URL"]) for i, r in enumerate(csv_rows)}
    nodes, skipped = plan_nodes(seed, sources, [], {})
    direct = {n.category: n for n in nodes if n.kind == "row_listing"}
    assert set(direct) == {
        "Candles Home Fragrances",
        "Batteries",
        "Light Bulbs",
        "School Office",
        "Hardware Home Improvement",
    }
    batteries = direct["Batteries"]
    assert batteries.taxonomy_id == "26003" and batteries.sub_category == ""
    assert batteries.url == "https://www.marianos.com/pl/batteries/26003?pzn=relevance"
    reasons = {s.get("category"): s["reason"] for s in skipped if "sub_category" not in s}
    assert set(reasons) == {"Coupons"} and "offers, not products" in reasons["Coupons"]
    only, _ = plan_nodes(seed, sources, [24], {"24": ["26003"]})
    assert [(n.category, n.kind) for n in only] == [("Batteries", "row_listing")]


# -- Scrapfly account states ------------------------------------------------------------------------


def _usage(**kw: object) -> AccountUsage:
    base: dict[str, object] = {"observed_at": "t", "http_status": 200, "credits_remaining": 85}
    return AccountUsage(**{**base, **kw})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("usage", "state"),
    [
        (_usage(), "ok"),
        (_usage(http_status=401, error="Unauthorized"), "invalid_key"),
        (_usage(http_status=None, error="timed out"), "unavailable"),
        (_usage(http_status=503, error="unavailable"), "unavailable"),
        (_usage(suspended=True), "suspended"),
        (_usage(credits_remaining=0, extra_usage_allowed=False), "exhausted"),
        (_usage(credits_remaining=0, extra_usage_allowed=True), "ok"),
    ],
)
def test_account_readings_are_classified_honestly(usage: AccountUsage, state: str) -> None:
    assert scrapfly_account.classify(usage)[0] == state


def test_the_balance_is_labelled_as_account_wide_api_credits() -> None:
    view = scrapfly_account.balance_view(
        _usage(credits_limit=1000, credits_used=915, plan="FREE", period_end="2026-11-19 22:12:02")
    )
    assert view["unit"] == "API credits" and view["scope"] == "account-wide"
    assert (view["allowance"], view["consumed"], view["remaining"]) == (1000, 915, 85)
    assert view["period_end"] == "2026-11-19 22:12:02"
