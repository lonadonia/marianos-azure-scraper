"""Shared fixtures. Synthetic pages (tests/synthetic_marianos.py) are invented; the cards and responses under
tests/fixtures/live_2026-10-20 and the run under tests/captures were captured from marianos.com by earlier
live runs and are replayed offline."""

from __future__ import annotations

from pathlib import Path

import pytest

from marianos_headless.core.settings import (
    BrowserProvider,
    PrivateLabelConfig,
    Settings,
    StoreConfig,
    load_private_label,
    load_settings,
    load_stores,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
CAPTURES = ROOT / "tests" / "captures"
STORE_KEY = "marianos-53100503-instore"


@pytest.fixture(autouse=True)
def no_ambient_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reads a key or a database from the developer's environment."""
    for name in (
        "SCRAPFLY_API_KEY",
        "SCRAPFLY_API_KEY_FILE",
        "OXYLABS_WEB_API_KEY",
        "OXYLABS_WEB_API_KEY_FILE",
        "MARIANOS_COLLECTOR_DATABASE_URL",
        "MARIANOS_COLLECTOR_DATABASE_AUTH",
        "MARIANOS_COLLECTOR_STORAGE",
        "MARIANOS_COLLECTOR_DATA_DIR",
        "MARIANOS_COLLECTOR_BLOB_ACCOUNT_URL",
        "MARIANOS_COLLECTOR_BLOB_CONTAINER",
        "MARIANOS_COLLECTOR_CONFIG",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def settings() -> Settings:
    """The shipped settings with the Scrapfly provider: the browser tests drive the Scrapfly path (the
    Oxylabs tests build their own settings)."""
    s = load_settings(CONFIG / "settings.yaml")
    acq = s.acquisition.model_copy(update={"browser_provider": BrowserProvider.SCRAPFLY})
    return s.model_copy(update={"acquisition": acq})


@pytest.fixture(scope="session")
def dev_store() -> StoreConfig:
    return next(s for s in load_stores(CONFIG / "stores.yaml").stores if s.key == STORE_KEY)


@pytest.fixture(scope="session")
def private_label() -> PrivateLabelConfig:
    return load_private_label(CONFIG / "private_label_brands.yaml")
