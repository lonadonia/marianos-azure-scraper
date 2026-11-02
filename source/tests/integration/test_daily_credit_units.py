"""Release 1.7.0: the store-day credit budget counts each provider in its own unit.

Before 1.7.0 the store-day sum added every segment's ``credits_estimated`` whatever the provider: Scrapfly API
credits and Oxylabs Web API submissions as if they were one unit (on 2026-10-29 the 1.6.0 Scrapfly canary A2a
was refused by the daily credit limit because of the day's Oxylabs submissions). A segment's provider is its
run's, recorded in the run snapshot for the run's whole life. SYNTHETIC rows and a fake Oxylabs API (the fakes
of test_oxylabs_collector.py); no provider request leaves the process."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, select

from marianos_headless.collection.config import Limits
from marianos_headless.collection.limits import segment_totals
from marianos_headless.collection.schedule import local_day
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig
from marianos_headless.core.timeutil import utcnow
from marianos_headless.db.models import CollectionSegment, Run, Store
from marianos_headless.storage.local import LocalStorageAdapter
from tests.conftest import STORE_KEY
from tests.integration.helpers import new_run, seed
from tests.integration.test_oxylabs_collector import FakeOxylabs, _ceiling, _run

pytestmark = [pytest.mark.postgres]


@pytest.fixture
def env(
    migrated_engine: Engine, tmp_path: Path, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": dev_store,
        "private_label": private_label,
        "tmp": tmp_path,
    }


def _earlier_segment(env: dict[str, Any], provider: str | None, credits: float) -> tuple[str, str, str]:
    """A finished run of ``provider`` (None: a run whose snapshot names no provider) with one segment today
    (the store's local day) that used ``credits`` in that provider's unit."""
    factory = env["factory"]
    with factory() as s:
        store = s.scalars(select(Store).where(Store.key == STORE_KEY)).one()
    earlier = new_run(factory, store, status="rejected")
    day = local_day(utcnow(), ZoneInfo("America/Chicago")).isoformat()
    now = utcnow()
    with factory() as s:
        run = s.get(Run, earlier.id)
        assert run is not None
        snap = dict(run.config_snapshot or {})
        if provider is None:
            snap.pop("provider", None)
            snap["acquisition"] = {
                k: v for k, v in snap.get("acquisition", {}).items() if k != "browser_provider"
            }
        else:
            snap["provider"] = provider
        run.config_snapshot = snap
        s.add(
            CollectionSegment(
                run_id=run.id,
                store_id=store.id,
                trigger="test",
                day=day,
                started_at=now,
                heartbeat_at=now,
                ended_at=now,
                credits_estimated=credits,
            )
        )
        s.commit()
    return earlier.id, store.id, day


def test_scrapfly_credits_used_today_do_not_count_against_an_oxylabs_daily_budget(
    env: dict[str, Any], settings: Settings
) -> None:
    scrapfly_run, store_id, day = _earlier_segment(env, "scrapfly", 100.0)
    _ceiling(env["factory"], 10)
    fake = FakeOxylabs()
    run_id, status = _run(env, settings, fake, limits=Limits(max_credits_per_day=50))
    # Before 1.7.0: stopped at opening (about 100 "credits" today against a budget of 50), nothing sent.
    assert status == "rejected" and len(fake.requests) == 4  # the whole plan (incomplete as every listing)
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code != "DAILY_CREDIT_LIMIT"
        assert segment_totals(s, run_id, store_id, day, provider="oxylabs")[2] == 4  # submissions
        assert segment_totals(s, scrapfly_run, store_id, day, provider="scrapfly")[2] == 100  # API credits


def test_an_oxylabs_daily_budget_still_counts_its_own_submissions_of_the_day(
    env: dict[str, Any], settings: Settings
) -> None:
    _earlier_segment(env, "oxylabs", 50.0)  # an earlier Oxylabs run of the same store today
    _ceiling(env["factory"], 10)
    fake = FakeOxylabs()
    run_id, status = _run(env, settings, fake, limits=Limits(max_credits_per_day=50))
    assert status == "interrupted" and fake.requests == []
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "DAILY_CREDIT_LIMIT"


def test_a_run_that_names_no_provider_counts_as_a_scrapfly_run(
    env: dict[str, Any], settings: Settings
) -> None:
    """Runs created before the snapshot named a provider collected with Scrapfly (the only provider then)."""
    old_run, store_id, day = _earlier_segment(env, None, 100.0)
    _ceiling(env["factory"], 10)
    fake = FakeOxylabs()
    _, status = _run(env, settings, fake, limits=Limits(max_credits_per_day=50))
    assert status == "rejected" and len(fake.requests) == 4
    with env["factory"]() as s:
        assert segment_totals(s, old_run, store_id, day, provider="scrapfly")[2] == 100
