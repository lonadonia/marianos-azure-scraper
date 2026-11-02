"""The collector's configuration file (``config/collector.yaml``) and what it points to.

Everything an operator used to set in a console is here, outside the source code: the stores file, the
client's category CSV, the saved site menu (each category's listing pages), per-store collection settings
(categories, limits, the store-local schedule), the automated canary and publication. Secrets never go in
it: the provider key and the database password come from the environment (Azure secret references in
production).

Relative paths are resolved against the configuration file's own directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from marianos_headless.collection.config import CollectionConfig
from marianos_headless.collection.nodes import load_seed
from marianos_headless.core.settings import (
    PrivateLabelConfig,
    Settings,
    StoreConfig,
    StoresFile,
    load_private_label,
    load_settings,
    load_stores,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CanaryConfig(_Model):
    """The automated checks of a run's first recorded page (they replace a person's review)."""

    enabled: bool = True
    min_valid_records: int = Field(1, ge=0)
    min_valid_ratio: float = Field(0.05, ge=0, le=1)  # of the page's recorded products
    required_fields: tuple[str, ...] = (
        "zipcode",
        "store_name",
        "store_location",
        "category",
        "sub_category",
        "product_title",
        "image_url",
        "url",
        "upc",
        "crawl_date",
    )
    # Every valid record equal to the site's own product data for the store (UPC, store, prices), read
    # independently of the collector's parser; the page requests that data for most, not always all, of
    # its cards, so a share of them must be found in it.
    source_check: bool = True
    min_source_verified_ratio: float = Field(0.5, ge=0, le=1)


class HistoricalConfig(_Model):
    """Retention of the store's verified products (``collection/retention.py``): a product a run does not
    observe keeps its last verified observation, carried forward unchanged with its own crawl date;
    ``max_age_days`` (default none) would stop carrying observations older than that."""

    enabled: bool = True
    max_age_days: int | None = Field(None, ge=0)


class PublishConfig(_Model):
    """A complete, validated, non-pilot run is published to ``published/<store>/`` (the last successful
    complete dataset). Runs with warnings are published only with ``accept_warnings`` and a reason."""

    auto: bool = True
    accept_warnings_reason: str | None = None


class StoreCollection(CollectionConfig):
    """One store's collection: what to collect, limits, the store-local schedule, and how a scheduled
    execution treats an unfinished run of the same occurrence."""

    max_auto_resumes: int = Field(3, ge=0)
    # A scheduled execution may start at most this long after the store-local start time (the Azure cron
    # fires at both standard-time and daylight-time UTC hours; the other one is outside this tolerance).
    start_tolerance_minutes: int = Field(45, ge=5, le=240)


class CollectorConfig(_Model):
    retailer: str = "marianos"
    settings_file: str = "settings.yaml"
    stores_file: str = "stores.yaml"
    categories_csv: str = "Marianos_Category_URLs.csv"
    private_label_file: str = "private_label_brands.yaml"
    taxonomy_seed_file: str = "taxonomy_seed.snapshot_2026-10-17.json"
    collections: dict[str, StoreCollection] = Field(default_factory=dict)
    canary: CanaryConfig = Field(default_factory=CanaryConfig)
    historical: HistoricalConfig = Field(default_factory=HistoricalConfig)
    publish: PublishConfig = Field(default_factory=PublishConfig)

    @model_validator(mode="after")
    def _marianos(self) -> CollectorConfig:
        if self.retailer != "marianos":
            raise ValueError("this collector collects Mariano's only (retailer: marianos)")
        return self


class LoadedConfig:
    """The configuration file and the files it names, loaded and checked."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.base = self.path.parent
        raw: Any = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.collector = CollectorConfig.model_validate(raw)
        settings_path = self._p(self.collector.settings_file)
        if not settings_path.is_file():
            # Never the built-in defaults instead: they name another provider (no silent routing).
            raise FileNotFoundError(f"settings file not found: {settings_path}")
        self.settings: Settings = load_settings(settings_path)
        self.stores: StoresFile = load_stores(self._p(self.collector.stores_file))
        self.private_label: PrivateLabelConfig = load_private_label(
            self._p(self.collector.private_label_file)
        )
        self.categories_csv = self._p(self.collector.categories_csv)
        if not self.categories_csv.is_file():
            raise FileNotFoundError(f"categories CSV not found: {self.categories_csv}")
        seed_path = self._p(self.collector.taxonomy_seed_file)
        if not seed_path.is_file():
            raise FileNotFoundError(f"site menu (taxonomy seed) not found: {seed_path}")
        self.seed: dict[str, Any] = load_seed(seed_path)
        unknown = sorted(set(self.collector.collections) - {s.key for s in self.stores.stores})
        if unknown:
            raise ValueError(f"collections for stores not in {self.collector.stores_file}: {unknown}")

    def _p(self, name: str) -> Path:
        p = Path(name)
        return p if p.is_absolute() else self.base / p

    def store(self, key: str) -> StoreConfig:
        for s in self.stores.stores:
            if s.key == key:
                if not s.enabled:
                    raise ValueError(f"store {key} is disabled in {self.collector.stores_file}")
                return s
        raise KeyError(f"unknown store {key!r}; configured: {[s.key for s in self.stores.stores]}")

    def collection(self, key: str) -> StoreCollection:
        """The store's collection settings (defaults: every category, no limit, schedule off)."""
        return self.collector.collections.get(key) or StoreCollection()
