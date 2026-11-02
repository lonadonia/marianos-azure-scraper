"""The configuration file, the Azure cron expression and the store-local schedule guard (no database)."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from marianos_headless.config_file import LoadedConfig, StoreCollection
from marianos_headless.operations import due_occurrence, utc_cron
from tests.conftest import CONFIG, STORE_KEY


def _config(tmp_path: Path, **collector: object) -> Path:
    d = tmp_path / "config"
    shutil.copytree(CONFIG, d)
    data = yaml.safe_load((d / "collector.yaml").read_text(encoding="utf-8"))
    data.update(collector)
    (d / "collector.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return d / "collector.yaml"


def test_a_settings_file_that_is_not_there_is_an_error_not_the_defaults(tmp_path: Path) -> None:
    # The built-in defaults name another provider: using them would route a run silently.
    path = _config(tmp_path, settings_file="missing.yaml")
    with pytest.raises(FileNotFoundError, match="settings file not found"):
        LoadedConfig(path)


def test_the_shipped_configuration_names_store_53100503_in_store_twice_a_week() -> None:
    cfg = LoadedConfig(CONFIG / "collector.yaml")
    store = cfg.store(STORE_KEY)
    assert (store.location_id, store.expected.postal_code, store.modality.value) == (
        "53100503",
        "60601",
        "IN_STORE",
    )
    assert store.expected.address_line1 == "333 E Benton Pl"
    assert store.expected.display_name == "Marianos Lakeshore East"
    coll = cfg.collection(STORE_KEY)
    # Twice a week is configured, but the schedule ships OFF until the client switches it on.
    assert not coll.schedule.enabled and len(coll.schedule.weekdays) == 2
    assert coll.timezone == "America/Chicago"
    assert not coll.limits.bounded()  # production collects the full configured scope
    assert cfg.categories_csv.name == "Marianos_Category_URLs.csv" and len(cfg.seed["rows"]) == 28


def test_configuration_errors_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        LoadedConfig(_config(tmp_path / "a", retailer="walmart"))
    with pytest.raises(ValidationError):
        LoadedConfig(_config(tmp_path / "b", provider="oxylabs"))  # no other provider can be configured
    with pytest.raises(ValueError, match=r"not in stores.yaml"):
        LoadedConfig(_config(tmp_path / "c", collections={"marianos-99999999": {}}))
    with pytest.raises(ValidationError):
        StoreCollection.model_validate({"schedule": {"enabled": True, "weekdays": []}})
    with pytest.raises(ValidationError):
        StoreCollection.model_validate({"timezone": "Mars/Olympus"})
    with pytest.raises(ValidationError):  # a Walmart-only limit is refused, never silently ignored
        StoreCollection.model_validate({"limits": {"max_products_per_category": 5}})


def test_the_cron_expression_covers_standard_and_daylight_time() -> None:
    coll = StoreCollection.model_validate(
        {
            "timezone": "America/Chicago",
            "schedule": {"enabled": True, "weekdays": [1, 4], "start_time": "06:00"},
        }
    )
    cron = utc_cron(coll, year=2026)
    assert cron["cron_utc"] == "0 11,12 * * 2,5"  # Tuesday and Friday; 11:00 UTC in CDT, 12:00 in CST
    late = StoreCollection.model_validate(
        {"timezone": "America/Chicago", "schedule": {"enabled": True, "weekdays": [1], "start_time": "21:30"}}
    )
    # 21:30 Chicago is the next UTC day (02:30 or 03:30 UTC on Wednesday).
    assert utc_cron(late, year=2026)["cron_utc"] == "30 2,3 * * 3"


@pytest.mark.parametrize(
    ("utc", "due"),
    [
        (datetime(2026, 7, 14, 11, 0, tzinfo=UTC), True),  # 06:00 CDT
        (datetime(2026, 7, 14, 12, 0, tzinfo=UTC), False),  # 07:00 CDT: the other firing
        (datetime(2026, 7, 14, 10, 57, tzinfo=UTC), True),  # a few minutes early
        (datetime(2026, 7, 14, 11, 40, tzinfo=UTC), True),  # within the tolerance (45 min)
        (datetime(2026, 7, 14, 11, 50, tzinfo=UTC), False),
        (datetime(2026, 1, 13, 12, 0, tzinfo=UTC), True),  # 06:00 CST
        (datetime(2026, 1, 13, 11, 0, tzinfo=UTC), False),  # 05:00 CST
        (datetime(2026, 3, 10, 11, 0, tzinfo=UTC), True),  # the Tuesday after the March change: CDT
        (datetime(2026, 11, 3, 12, 0, tzinfo=UTC), True),  # the Tuesday after the November change: CST
        (datetime(2026, 7, 15, 11, 0, tzinfo=UTC), False),  # Wednesday
    ],
)
def test_only_the_due_local_occurrence_is_acted_on(utc: datetime, due: bool) -> None:
    coll = StoreCollection.model_validate(
        {"timezone": "America/Chicago", "schedule": {"enabled": True, "weekdays": [1], "start_time": "06:00"}}
    )
    assert (due_occurrence(coll, utc) is not None) is due


def test_a_second_store_is_configured_with_its_own_collection_and_schedule(tmp_path: Path) -> None:
    """Multi-store configuration (brief §8, release 1.5.0): a second entry (here the same store for Pickup,
    "the same store collected for two fulfillment modes is two entries"; SYNTHETIC configuration, no run) has
    its own collection, limits and schedule, and its own UTC cron; the first store is unchanged."""
    path = _config(
        tmp_path,
        collections={
            STORE_KEY: {"timezone": "America/Chicago"},
            "marianos-53100503-pickup": {
                "categories": [1, 7],
                "timezone": "America/Chicago",
                "limits": {"max_products_per_run": 500},
                "schedule": {"enabled": False, "weekdays": [1, 4], "start_time": "06:00"},
            },
        },
    )
    stores = yaml.safe_load((path.parent / "stores.yaml").read_text(encoding="utf-8"))
    pickup = {**stores["stores"][0], "key": "marianos-53100503-pickup", "modality": "PICKUP"}
    stores["stores"].append(pickup)
    (path.parent / "stores.yaml").write_text(yaml.safe_dump(stores, sort_keys=False), encoding="utf-8")
    cfg = LoadedConfig(path)
    assert cfg.store("marianos-53100503-pickup").modality.value == "PICKUP"
    assert cfg.store(STORE_KEY).modality.value == "IN_STORE"
    second = cfg.collection("marianos-53100503-pickup")
    assert second.categories == [1, 7] and second.limits.bounded()
    assert second.schedule.backlog_first  # the continuation/backlog policy is on by default
    assert utc_cron(second, year=2026)["cron_utc"] == "0 11,12 * * 2,5"
