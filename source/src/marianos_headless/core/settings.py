"""Typed configuration (brief §15). Every run snapshots the fully resolved settings."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AcquisitionMode(StrEnum):
    UI_CAPTURE = "UI_CAPTURE"
    IN_PAGE_REPLAY = "IN_PAGE_REPLAY"  # needs written client authorization (Q-13)


class PpmSourcePolicy(StrEnum):
    DOM_ONLY = "DOM_ONLY"
    DOM_THEN_SITE_FORMATTED_JSON = "DOM_THEN_SITE_FORMATTED_JSON"  # only after client approval (Q-05)


class OtherPromoTarget(StrEnum):
    NONE = "NONE"
    VOLUME_DESCRIPTION = "VOLUME_DESCRIPTION"


class DealDescriptionFormat(StrEnum):
    TAG_TEXT_EXPIRY = "TAG_TEXT_EXPIRY"
    TEXT_ONLY = "TEXT_ONLY"


class PrimaryCategoryPolicy(StrEnum):
    CSV_ORDER_COUPONS_LAST = "CSV_ORDER_COUPONS_LAST"
    CSV_ORDER = "CSV_ORDER"


class SubCategoryFormat(StrEnum):
    LEAF = "LEAF"
    PATH = "PATH"


class Modality(StrEnum):
    IN_STORE = "IN_STORE"
    PICKUP = "PICKUP"
    DELIVERY = "DELIVERY"
    SHIP = "SHIP"


class BrowserProvider(StrEnum):
    LOCAL = "local"  # stock Playwright Chromium (tests against a local mock site only)
    SCRAPFLY = "scrapfly"  # Scrapfly Cloud Browser over CDP
    # Oxylabs Web API (release 1.3.0): Mariano's search result pages fetched by the provider's Mariano's
    # scraper with the store and fulfillment as request parameters; no browser runs on the collector side.
    OXYLABS = "oxylabs"


class ScrapflyBrowserSettings(_Strict):
    """Scrapfly Cloud Browser. The API key comes only from the environment (``SCRAPFLY_API_KEY`` or
    ``SCRAPFLY_API_KEY_FILE``); it is never part of the settings or a snapshot.

    The proxy pool and the browser platform are chosen before the first request, are the same for every
    session and are never changed after a refusal. Credit rates are the free plan's published ones (1
    credit per 30 s started, per-MB bandwidth by pool, at least 5 credits per browser); a browser session
    with no run, day or account budget to keep stops before its estimate passes ``max_credits_per_run``.
    """

    endpoint: str = "wss://browser.scrapfly.io"
    account_url: str = "https://api.scrapfly.io/account"
    proxy_pool: Literal["datacenter", "residential"] = "residential"
    country: str = Field("us", pattern=r"^[a-z]{2}$")
    # The provider's ``os`` parameter: the platform of the browser fingerprint it manages (no user agent or
    # other fingerprint value is set by the collector). None lets the provider pick one at random for each
    # session. ADR-008, addendum 2026-10-23: every saved session it gave a Linux platform was refused by
    # marianos.com (HTTP 403) or got no answer, while Windows and macOS sessions were served.
    browser_os: Literal["windows", "macos", "linux"] | None = None
    # The provider's ``browser_brand`` parameter: the Chromium-based brand its fingerprint is generated
    # for (documented values chrome, the provider's default, edge, brave, opera; "edge is Windows-only").
    # None sends nothing. Release 1.6.0: the only session served by the retailer since 2026-10-23 used
    # edge on Windows (minimal script A1, 2026-10-29 20:40Z, PROVIDER_COMPARISON).
    browser_brand: Literal["chrome", "edge", "brave", "opera"] | None = None
    target_url: str = "https://www.marianos.com/"
    block_images: bool = True  # stubbed by Scrapfly (1x1 pixel); image URLs stay in the DOM
    block_fonts: bool = True
    block_media: bool = True
    block_styles: bool = False  # kept so screenshots stay readable
    blacklist: bool = True  # stubs known analytics/tracking URLs
    cache: bool = True  # static resources from Scrapfly's cache are billed at 1 credit/MB
    session_timeout_s: int = Field(900, ge=60, le=1800)  # the provider closes the browser after this
    connect_timeout_s: float = Field(60, gt=0)
    credits_per_mb_datacenter: float = 7
    credits_per_mb_residential: float = 52
    bandwidth_overhead_factor: float = Field(1.3, ge=1.0)  # traffic the page meter cannot see
    max_credits_per_run: int = Field(300, ge=5)
    concurrency: Literal[1] = 1

    @model_validator(mode="after")
    def _edge_is_windows_only(self) -> ScrapflyBrowserSettings:
        # The provider refuses edge on another platform (ERR::BROWSER::CONFIG_ERROR) and picks a random
        # desktop platform when none is given: edge therefore needs browser_os windows.
        if self.browser_brand == "edge" and self.browser_os != "windows":
            raise ValueError("browser_brand edge requires browser_os windows (the provider's rule)")
        return self


class OxylabsSettings(_Strict):
    """Oxylabs Web API (``webapi.oxylabs.io``, a Bearer key). The key comes only from the environment
    (``OXYLABS_WEB_API_KEY`` or ``OXYLABS_WEB_API_KEY_FILE``); it is never part of the settings or a snapshot.

    The Mariano's scraper's OPTIONS answer (2026-10-28) lists ``store_id`` and ``fulfillment_type``
    (``delivery``, ``in_store``, ``pickup``). What it serves depends on the context: at store 53100503, In
    Store, probes of 2026-10-28 found ``/pl/`` listing pages refused (``500
    REQUEST_FAILED_AFTER_TOO_MANY_RETRIES``, not charged); at store 53100502, Pickup, probes of 2026-11-02
    found them served with real later pages (``?page=N``) rendered with ``render=html``, while the search
    route's page 2 repeated page 1 in another order. Each submission is reserved in the ledger at
    ``usd_per_result`` before it is sent, against the
    operator's ceiling (``set-ceiling``); Oxylabs documents no balance or usage API."""

    api_base: str = "https://webapi.oxylabs.io"
    search_endpoint: str = "/v1/scrape/marianos/search"
    page_endpoint: str = "/v1/scrape/marianos"
    location: str = Field("US", pattern=r"^[A-Z]{2}$")
    usd_per_result: float = Field(0.0015, gt=0)  # the price page's highest rate without AI parsing
    request_timeout_s: float = Field(180, gt=0)  # a JavaScript-rendered page took up to 120 s (probe)
    max_attempts: int = Field(3, ge=1, le=5)  # retry 408, 429 and 5xx with backoff (Troubleshooting)
    coupons_run_js: bool = True  # the Coupons page shows its cards only when rendered (probe 2026-10-28)
    # How a listing is read (release 1.8.0). ``listing``: its own /pl/ page and every later page. ``search``:
    # only the first page of the retailer's search for the listing's name, for a context whose /pl/ pages are
    # refused; such a listing is never complete.
    listing_route: Literal["listing", "search"] = "listing"
    # A listing page without rendering may carry its products in the page state only, with no card (probes L9,
    # L11, L12): the displayed values needed the rendered page. Release 1.9.0rc2: since the tile of 2026-11-06
    # the reverse holds: every unrendered listing answer carried all its tiles (5 of 5) and every rendered one
    # none (2 of 2, one of them not asked to render; stages S1 and O2), so listing pages are asked for without
    # rendering. The provider may still render one: the collector then asks again (``oxylabs_live``).
    listing_run_js: bool = False
    # Release 1.9.0 (M4): a product's own page, read for its coupons' complete terms, is requested rendered:
    # its Savings section loads only when the page's scripts run.
    product_terms_run_js: bool = True


class AcquisitionSettings(_Strict):
    mode: AcquisitionMode = AcquisitionMode.UI_CAPTURE
    browser_provider: BrowserProvider = BrowserProvider.SCRAPFLY
    scrapfly: ScrapflyBrowserSettings = ScrapflyBrowserSettings()
    oxylabs: OxylabsSettings = OxylabsSettings()
    headless: bool = True
    navigation_min_interval_s: float = Field(4.0, ge=1.0)
    navigation_interval_jitter_s: float = Field(1.0, ge=0.0)
    page_load_timeout_s: float = 45
    response_wait_timeout_s: float = 30
    # A page opened once at the start of each browser session, after robots.txt and before the first
    # listing (for example the home page), with the same challenge checks; None opens the listing
    # directly (as every run before 2026-10-22 did).
    entry_url: str | None = None


class RetrySettings(_Strict):
    max_attempts_per_task: int = 3
    backoff_base_s: float = 10
    backoff_max_s: float = 300
    pause_on_429_s: float = 600  # when a 429 comes without a Retry-After header
    max_retry_after_s: float = 1800  # a site asking for a longer pause stops the category instead


class CircuitBreakerSettings(_Strict):
    consecutive_failures_to_fail_category: int = 5
    challenge_pages_to_abort_run: int = 1


class CoverageSettings(_Strict):
    node_min_coverage_ratio: float = Field(0.98, gt=0, le=1)
    row_fail_below_ratio: float = Field(0.90, gt=0, le=1)
    allow_paid_only_membership: bool = False
    # A listing whose site total exceeds what its search lets the page reach (availableCount) is read through
    # the child listings the site's own category facet names (each one checked and paged like any listing).
    partition_large_listings: bool = True
    # Release 1.9.0 (M4), Oxylabs route: the product's own page is read (rendered, once per product and run)
    # for every card that shows a digital coupon, for the coupon's ID, complete terms, displayed expiry,
    # clipping instruction and qualifying products. Each read is one more provider request (counted and
    # bounded like any other; ``limits.max_product_term_reads``). Off: the card's headline only, flagged
    # DIGITAL_TERMS_UNREAD.
    # Release 1.9.0rc3: the tile served since 2026-11-06 shows no coupon, so with this on every tile's product
    # page is read (one more request per product, within ``limits.max_product_term_reads``); a product left
    # unread is flagged DIGITAL_COUPONS_UNOBSERVED (its coupon is unknown, not absent).
    read_product_terms: bool = False


class YieldSettings(_Strict):
    warn_drop_vs_last_good: float = 0.30
    fail_drop_vs_last_good: float = 0.50


class AttestationSettings(_Strict):
    periodic_every_navigations: int = 25
    # Phase 0 deliverable: the modality `source` value the site reports after an explicit store
    # selection. Empty means "not yet recorded", and A3 fails until it is filled in.
    trusted_modality_sources: tuple[str, ...] = ()
    require_is_trusted_source: bool = True


# The client's rule (Shared_Scraper_Technical_Requirements §5): "Exclude records whose weight contains approx,
# approximately or equivalent approximate-weight wording." Read on the weight only: "approx", "approximately",
# "avg"/"average", "estimated", "~" or "about" before a quantity ("about 2 lb"), and a weight range
# ("10-14 lb"). "About" elsewhere (a marketing phrase) is not approximate-weight wording (release 1.4.0).
APPROX_WEIGHT_PATTERN = (
    r"(?i)\b(approx\.?|approximately|avg\.?|average|estimated)(?=[\s\d.]|$)|~\s*\d|\babout\s+\d"
    r"|\b\d+(\.\d+)?\s*(-|to)\s*\d+(\.\d+)?\s*(lb|lbs|pound|pounds|oz|ounce|ounces|kg|g)\b"
)


# Where the rule reads the product's weight (release 1.5.0). "weight": the displayed weight;
# "product_data_size": the size the site's own product data states for the store (``customerFacingSize``,
# "10-14 lb" for a whole turkey sold by weight whose size slot shows "$0.98/lb"); "title": a weight range in
# the name of a product sold by weight, read only when no weight is displayed (a diaper's "(22-37 lbs)" is the
# baby's weight, never read). ["weight"] alone is the rule of release 1.4.0.
ApproxWeightSource = Literal["weight", "product_data_size", "title"]
APPROX_WEIGHT_SOURCES: tuple[ApproxWeightSource, ...] = ("weight", "product_data_size", "title")


class RecordSettings(_Strict):
    exclude_ship_only: bool = True
    approx_weight_pattern: str = APPROX_WEIGHT_PATTERN
    approx_weight_sources: tuple[ApproxWeightSource, ...] = APPROX_WEIGHT_SOURCES
    store_brand_positive_value: str = "yes"
    store_brand_negative_value: Literal["no"] = "no"
    include_cashback_in_digital: bool = False
    include_points_offers_in_deals: bool = False
    other_promo_target: OtherPromoTarget = OtherPromoTarget.NONE
    deal_description_format: DealDescriptionFormat = DealDescriptionFormat.TAG_TEXT_EXPIRY
    deal_description_separator: str = " | "
    ppm_source_policy: PpmSourcePolicy = PpmSourcePolicy.DOM_ONLY
    primary_category_policy: PrimaryCategoryPolicy = PrimaryCategoryPolicy.CSV_ORDER_COUPONS_LAST
    sub_category_format: SubCategoryFormat = SubCategoryFormat.LEAF
    sub_category_path_separator: str = " > "
    crawl_date: Literal["STORE_LOCAL_DATE"] = "STORE_LOCAL_DATE"
    fail_on_price_mismatch: bool = True

    @field_validator("approx_weight_pattern")
    @classmethod
    def _compiles(cls, v: str) -> str:
        re.compile(v)
        return v


class ContestSettings(_Strict):
    enabled: bool = True
    min_valid_records: int = 500
    min_categories: int = 3


class StorageSettings(_Strict):
    backend: Literal["local", "azure_blob"] = "local"
    local_root: str = "./data"
    azure_account_url: str | None = None
    azure_container: str | None = None


class GateThresholds(_Strict):
    coverage_warn_below: float = 0.98
    coverage_fail_below: float = 0.90
    price_completeness_warn_below: float = 0.98
    reconciliation_warn_above: float = 0.005
    reconciliation_fail_above: float = 0.02
    canary_missing_is_fail: bool = False


class Settings(_Strict):
    acquisition: AcquisitionSettings = AcquisitionSettings()
    retries: RetrySettings = RetrySettings()
    circuit_breaker: CircuitBreakerSettings = CircuitBreakerSettings()
    coverage: CoverageSettings = CoverageSettings()
    yield_: YieldSettings = Field(YieldSettings(), alias="yield")
    attestation: AttestationSettings = AttestationSettings()
    records: RecordSettings = RecordSettings()
    gates: GateThresholds = GateThresholds()
    contest: ContestSettings = ContestSettings()
    storage: StorageSettings = StorageSettings()

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    def snapshot(self) -> dict[str, Any]:
        """JSON-serialisable copy stored on every run (``runs.config_snapshot``)."""
        return self.model_dump(mode="json", by_alias=True)


class StoreExpectation(_Strict):
    display_name: str
    postal_code: str
    address_line1: str | None = None


class StoreConfig(_Strict):
    """One Mariano's store and the fulfillment its prices are collected for. ``location_id`` = 3-digit
    division + 5-digit store (Kroger's location id). The same physical store collected for two fulfillment
    modes is two entries (two keys). The labels here are expectations: every page is checked against them."""

    key: str
    retailer: Literal["marianos"] = "marianos"
    enabled: bool = True
    location_id: str
    division_number: str = ""
    store_number: str = ""
    expected: StoreExpectation
    modality: Modality = Modality.IN_STORE
    timezone: str = "America/Chicago"
    store_page_url: str | None = None  # the store's own page on the banner site (store selection)
    is_contest_store: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _location_id_matches_parts(self) -> StoreConfig:
        if self.modality not in (Modality.IN_STORE, Modality.PICKUP):
            raise ValueError("store price context must be IN_STORE or PICKUP")
        if not re.fullmatch(r"\d{3}", self.division_number):
            raise ValueError("division_number must be 3 digits")
        if not re.fullmatch(r"\d{5}", self.store_number):
            raise ValueError("store_number must be 5 digits")
        if self.location_id != self.division_number + self.store_number:
            raise ValueError("location_id must equal division_number + store_number")
        return self


class StoresFile(_Strict):
    stores: tuple[StoreConfig, ...]

    @model_validator(mode="after")
    def _unique_keys(self) -> StoresFile:
        keys = [s.key for s in self.stores]
        if len(keys) != len(set(keys)):
            raise ValueError("store keys must be unique")
        return self


class PrivateLabelConfig(_Strict):
    brands: tuple[str, ...]
    upc_prefix_signals: tuple[str, ...] = ()


class Canary(_Strict):
    upc: str
    name: str
    expected_category: str | None = None


class CanariesFile(_Strict):
    canaries: tuple[Canary, ...] = ()


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings(path: Path | None) -> Settings:
    if path is None or not path.exists():
        return Settings()
    return Settings.model_validate(_load_yaml(path))


def load_stores(path: Path) -> StoresFile:
    return StoresFile.model_validate(_load_yaml(path))


def load_private_label(path: Path) -> PrivateLabelConfig:
    return PrivateLabelConfig.model_validate(_load_yaml(path))


def load_canaries(path: Path) -> CanariesFile:
    if not path.exists():
        return CanariesFile()
    return CanariesFile.model_validate(_load_yaml(path))
