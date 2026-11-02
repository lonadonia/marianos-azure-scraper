"""Scrapfly Cloud Browser provider and pilot logic, offline (no network, no browser). SYNTHETIC data."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Error as PlaywrightError
from pydantic import SecretStr

from marianos_headless.acquisition import browser as browser_mod
from marianos_headless.acquisition import scrapfly
from marianos_headless.acquisition.browser import BrowserSession
from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    PrivateLabelConfig,
    ScrapflyBrowserSettings,
    Settings,
    StoreConfig,
)
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker import store_selection as sp
from tests import synthetic_marianos as syn

KEY = "scp-live-0123456789abcdef0123456789abcdef"
BASE = "https://www.marianos.com"


# -- connection, credentials, redaction --------------------------------------------------------------


def test_endpoint_carries_key_and_parameters_but_public_form_does_not() -> None:
    cfg = ScrapflyBrowserSettings()
    url = scrapfly.ws_endpoint(cfg, SecretStr(KEY))
    assert url.startswith("wss://browser.scrapfly.io?api_key=" + KEY)
    for part in (
        "proxy_pool=residential",
        "country=us",
        "auto_close=true",
        "block_images=true",
        "cache=true",
        "target_url=https%3A%2F%2Fwww.marianos.com%2F",
        "timeout=900",
    ):
        assert part in url
    public = scrapfly.public_endpoint(cfg)
    assert KEY not in public and "api_key=%5BREDACTED%5D" in public
    assert "os=" not in url  # no platform configured: the provider picks one for each session


def test_the_configured_browser_platform_is_sent_and_recorded() -> None:
    cfg = ScrapflyBrowserSettings(browser_os="macos")
    assert scrapfly.connection_params(cfg)["os"] == "macos"
    assert "&os=macos&" in scrapfly.ws_endpoint(cfg, SecretStr(KEY))
    assert "&os=macos&" in scrapfly.public_endpoint(cfg)  # the session record shows it
    with pytest.raises(ValueError):
        ScrapflyBrowserSettings(browser_os="android")  # type: ignore[arg-type]


def test_the_configured_browser_brand_is_sent_and_recorded() -> None:
    cfg = ScrapflyBrowserSettings(browser_os="windows", browser_brand="edge")
    assert scrapfly.connection_params(cfg)["browser_brand"] == "edge"
    assert "&browser_brand=edge&" in scrapfly.ws_endpoint(cfg, SecretStr(KEY))
    assert "&browser_brand=edge&" in scrapfly.public_endpoint(cfg)  # the session record shows it
    assert "browser_brand" not in scrapfly.connection_params(ScrapflyBrowserSettings())  # none by default
    with pytest.raises(ValueError):
        ScrapflyBrowserSettings(browser_brand="safari")  # type: ignore[arg-type]


def test_edge_needs_the_windows_platform() -> None:
    # The provider's documented rule: edge is Windows-only (ERR::BROWSER::CONFIG_ERROR otherwise).
    for platform in (None, "macos", "linux"):
        with pytest.raises(ValueError, match="windows"):
            ScrapflyBrowserSettings(browser_brand="edge", browser_os=platform)  # type: ignore[arg-type]
    assert ScrapflyBrowserSettings(browser_brand="brave", browser_os="linux").browser_brand == "brave"


def test_the_delivered_settings_keep_the_providers_platform_and_the_longest_session() -> None:
    from marianos_headless.core.settings import load_settings
    from tests.conftest import CONFIG  # the source tree's, also when the package is installed

    s = load_settings(CONFIG / "settings.yaml").acquisition.scrapfly
    # os=macos had no observed effect live (2026-10-23): the provider's choice is kept.
    assert s.browser_os is None and s.proxy_pool == "residential"
    assert s.session_timeout_s == 1800  # the provider's maximum
    assert s.bandwidth_overhead_factor == 2.0  # measured 1.9 and 1.8 on the new account


def test_redact_removes_the_key_and_any_key_parameter() -> None:
    msg = f"connect failed: wss://browser.scrapfly.io?api_key={KEY}&x=1 and key=other-secret; monkey=ok"
    out = scrapfly.redact(msg, SecretStr(KEY))
    assert KEY not in out and "other-secret" not in out
    assert "monkey=ok" in out


def test_load_api_key_environment_first_then_file(tmp_path: Path) -> None:
    f = tmp_path / "scrapfly.env"
    f.write_text(f'# comment\nexport SCRAPFLY_API_KEY="{KEY}"\n', encoding="utf-8")
    assert scrapfly.load_api_key(f, environ={}).get_secret_value() == KEY  # type: ignore[union-attr]
    from_env = scrapfly.load_api_key(f, environ={"SCRAPFLY_API_KEY": "from-env"})
    assert from_env is not None and from_env.get_secret_value() == "from-env"
    assert scrapfly.load_api_key(tmp_path / "missing.env", environ={}) is None
    assert repr(scrapfly.load_api_key(f, environ={})) == "SecretStr('**********')"


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("WebSocket error: 401 Unauthorized", scrapfly.ProviderErrorKind.AUTH),
        ("Unexpected server response: 402 quota exhausted", scrapfly.ProviderErrorKind.QUOTA),
        ("Unexpected server response: 429", scrapfly.ProviderErrorKind.CONCURRENCY),
        ("ERR::BROWSER::CONFIG_ERROR edge requires windows", scrapfly.ProviderErrorKind.CONFIG),
        ("connect ECONNREFUSED 127.0.0.1:9", scrapfly.ProviderErrorKind.NETWORK),
        ("Timeout 60000ms exceeded", scrapfly.ProviderErrorKind.NETWORK),
        ("something odd", scrapfly.ProviderErrorKind.PROVIDER),
    ],
)
def test_connect_errors_are_classified(message: str, kind: scrapfly.ProviderErrorKind) -> None:
    assert scrapfly.classify_connect_error(message) is kind


@pytest.mark.parametrize(
    ("message", "side"),
    [
        ("net::ERR_TUNNEL_CONNECTION_FAILED at https://www.marianos.com/", "provider"),
        ("net::ERR_PROXY_CONNECTION_FAILED", "provider"),
        ("Target page, context or browser has been closed", "provider"),
        ("net::ERR_CONNECTION_RESET at https://www.marianos.com/robots.txt", "origin_network"),
        ("net::ERR_HTTP2_PROTOCOL_ERROR", "origin_network"),
        ("Page.goto: Timeout 45000ms exceeded.", "timeout"),
    ],
)
def test_navigation_errors_separate_provider_from_site(message: str, side: str) -> None:
    assert scrapfly.classify_navigation_error(message) == side


def test_credit_meter_follows_the_published_billing_rules() -> None:
    now = [100.0]
    meter = scrapfly.CreditMeter(rate_per_mb=52, overhead=1.0, clock=lambda: now[0])
    assert meter.estimate().credits == 5  # minimum per browser
    meter.add("https://www.marianos.com/app.js", 1_500_000)
    meter.add("https://www.marianos.com/", 200_000)
    now[0] += 61  # three started 30-second blocks
    est = meter.estimate()
    assert (est.time_credits, est.bandwidth_mb, est.bandwidth_credits) == (3, 1.7, 89)  # 1.7 MB x 52, up
    assert est.credits == 3 + 89
    assert meter.top_hosts()[0] == {"host": "www.marianos.com", "bytes": 1_700_000}
    assert meter.estimate(extra_bytes=300_000).bandwidth_credits == 104


def test_account_reading_keeps_no_identifiers_and_redacts_errors() -> None:
    body = {
        "account": {"account_id": "758899d9-aaaa", "timezone": "Africa/Casablanca", "suspended": False},
        "project": {"allow_extra_usage": True, "budget_limit": None},
        "subscription": {
            "plan_name": "FREE",
            "extra_scrape_allowed": False,
            "period": {"start": "2026-10-19 22:12:02", "end": "2026-11-19 22:12:02"},
            "usage": {
                "scrape": {
                    "limit": 1000,
                    "current": 12,
                    "remaining": 988,
                    "extra": 0,
                    "concurrent_limit": 5,
                    "concurrent_usage": 0,
                }
            },
        },
    }

    class Resp:
        status_code = 200

        def json(self) -> Any:
            return body

    seen: dict[str, Any] = {}

    def get(url: str, **kw: Any) -> Resp:
        seen.update(kw)
        return Resp()

    usage = scrapfly.read_account(ScrapflyBrowserSettings(), SecretStr(KEY), get=get)
    assert (usage.plan, usage.credits_used, usage.credits_remaining, usage.extra_usage_allowed) == (
        "FREE",
        12,
        988,
        False,
    )
    dumped = json.dumps(usage.__dict__)
    assert "758899d9" not in dumped and "Casablanca" not in dumped
    assert seen["headers"] == {"Authorization": f"Bearer {KEY}"} and "params" not in seen

    def failing(url: str, **kw: Any) -> Resp:
        raise RuntimeError(f"GET {url}?key={KEY} failed")

    err = scrapfly.read_account(ScrapflyBrowserSettings(), SecretStr(KEY), get=failing)
    assert err.error is not None and KEY not in err.error


# -- session lifecycle with a fake cloud browser ---------------------------------------------------


class FakeCDP:
    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.bodies: dict[str, str] = {}  # requestId -> body for Network.getResponseBody
        self.hang = False

    def on(self, name: str, fn: Any) -> None:
        self.handlers[name] = fn

    async def send(self, method: str, params: Any = None) -> dict[str, Any]:
        if method == "Network.getResponseBody":
            if self.hang:
                await asyncio.sleep(3600)
            return {"body": self.bodies[params["requestId"]], "base64Encoded": False}
        return {}


class FakePage:
    """A cloud-browser page whose navigation, like Scrapfly's, returns no response object; the document
    response only shows up as a CDP network event (``events`` is called during ``goto``)."""

    url = "about:blank"

    def __init__(self) -> None:
        self.text = ""
        self.events: Any = None

    def set_default_navigation_timeout(self, ms: float) -> None: ...

    def set_default_timeout(self, ms: float) -> None: ...

    def on(self, name: str, fn: Any) -> None: ...

    async def goto(self, url: str, **kw: Any) -> None:
        self.url = url
        if self.events:
            self.events(url)

    async def wait_for_timeout(self, ms: float) -> None: ...

    async def evaluate(self, expr: str, arg: Any = None) -> str:
        return self.text if "innerText" in expr else "FakeUA"

    async def content(self) -> str:
        return f"<html><body><pre>{self.text}</pre></body></html>"

    async def screenshot(self, **kw: Any) -> bytes:
        return b"\xff\xd8 synthetic jpeg"


class FakeContext:
    def __init__(self) -> None:
        self.pages = [FakePage()]
        self.cdp = FakeCDP()

    async def new_page(self) -> FakePage:
        raise AssertionError("the supplied page must be used")

    async def new_cdp_session(self, page: Any) -> FakeCDP:
        return self.cdp


class FakeBrowser:
    version = "fake-1"

    def __init__(self) -> None:
        self.contexts = [FakeContext()]
        self.closed = 0

    async def new_context(self) -> None:
        raise AssertionError("a new context must never be created on the cloud browser")

    async def close(self) -> None:
        self.closed += 1


class FakePlaywright:
    def __init__(self, browser: FakeBrowser | None, error: str | None = None) -> None:
        self.browser = browser
        self.error = error
        self.endpoint = ""
        self.stopped = False
        self.chromium = self

    async def connect_over_cdp(self, endpoint: str, timeout: float | None = None) -> FakeBrowser:
        self.endpoint = endpoint
        if self.error:
            raise PlaywrightError(self.error.format(endpoint=endpoint))
        assert self.browser is not None
        return self.browser

    async def launch(self, **kw: Any) -> None:
        raise AssertionError("no local browser with the scrapfly provider")

    async def start(self) -> FakePlaywright:
        return self

    async def stop(self) -> None:
        self.stopped = True


SCRAPFLY = AcquisitionSettings(browser_provider=BrowserProvider.SCRAPFLY)


def _session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakePlaywright, **kw: Any
) -> BrowserSession:
    monkeypatch.setattr(browser_mod, "async_playwright", lambda: fake)
    return BrowserSession(
        SCRAPFLY, LocalStorageAdapter(tmp_path), "runs/t", provider_key=SecretStr(KEY), **kw
    )


def test_supplied_context_is_used_and_the_browser_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakePlaywright(FakeBrowser())
    s = _session(tmp_path, monkeypatch, fake)

    async def run() -> None:
        async with s:
            assert fake.browser is not None
            assert s.context is fake.browser.contexts[0]
            assert s.page is fake.browser.contexts[0].pages[0]

    asyncio.run(run())
    assert fake.browser is not None and fake.browser.closed == 1 and fake.stopped and s.closed_at
    started = next(e for e in s.events if e.code == "BROWSER_STARTED")
    assert KEY not in json.dumps(started.data) and "REDACTED" in started.data["endpoint"]
    assert KEY in fake.endpoint  # the real endpoint went only to the connection call


@pytest.mark.parametrize("how", ["error", "cancel", "timeout"])
def test_the_browser_is_closed_on_failure_cancellation_and_timeout(
    how: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakePlaywright(FakeBrowser())
    s = _session(tmp_path, monkeypatch, fake)

    async def body() -> None:
        async with s:
            if how == "error":
                raise RuntimeError("boom")
            await asyncio.sleep(30)

    async def run() -> None:
        if how == "timeout":
            await asyncio.wait_for(body(), 0.05)
        elif how == "cancel":
            task = asyncio.ensure_future(body())
            await asyncio.sleep(0.05)
            task.cancel()
            await task
        else:
            await body()

    expected: type[BaseException] = {
        "error": RuntimeError,
        "cancel": asyncio.CancelledError,
        "timeout": TimeoutError,
    }[how]
    with pytest.raises(expected):
        asyncio.run(run())
    assert fake.browser is not None and fake.browser.closed == 1 and fake.stopped


def test_connect_failure_is_a_redacted_provider_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakePlaywright(
        None, error="BrowserType.connect_over_cdp: 401 Unauthorized\n  - <ws connecting> {endpoint}"
    )
    s = _session(tmp_path, monkeypatch, fake)

    async def run() -> None:
        async with s:
            pass

    with pytest.raises(scrapfly.ProviderError) as info:
        asyncio.run(run())
    assert info.value.kind is scrapfly.ProviderErrorKind.AUTH
    assert KEY not in str(info.value) and info.value.__context__ is None and info.value.__cause__ is None
    assert all(KEY not in json.dumps(e.data) + e.message for e in s.events)
    assert fake.stopped


def test_missing_key_stops_before_connecting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePlaywright(FakeBrowser())
    monkeypatch.setattr(browser_mod, "async_playwright", lambda: fake)
    s = BrowserSession(SCRAPFLY, LocalStorageAdapter(tmp_path), "runs/t", provider_key=None)

    async def run() -> None:
        async with s:
            pass

    with pytest.raises(scrapfly.ProviderError) as info:
        asyncio.run(run())
    assert info.value.kind is scrapfly.ProviderErrorKind.AUTH and fake.endpoint == "" and fake.stopped


def test_budget_guard_stops_before_the_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePlaywright(FakeBrowser())
    s = _session(tmp_path, monkeypatch, fake, max_credits=300)

    async def run() -> None:
        async with s:
            assert fake.browser is not None
            cdp = fake.browser.contexts[0].cdp
            cdp.handlers["Network.requestWillBeSent"]({"requestId": "1", "request": {"url": f"{BASE}/a.js"}})
            cdp.handlers["Network.loadingFinished"]({"requestId": "1", "encodedDataLength": 1_000_000})
            s.check_budget()  # 1 MB x 1.3 x 52 = 68 credits + time: allowed
            cdp.handlers["Network.requestWillBeSent"]({"requestId": "2", "request": {"url": f"{BASE}/b.js"}})
            cdp.handlers["Network.loadingFinished"]({"requestId": "2", "encodedDataLength": 3_500_000})
            with pytest.raises(scrapfly.ProviderError) as info:
                s.check_budget()
            assert info.value.kind is scrapfly.ProviderErrorKind.BUDGET

    asyncio.run(run())
    assert fake.browser is not None and fake.browser.closed == 1
    assert any(e.code == "PROVIDER_BUDGET_REACHED" for e in s.events)


def _document_event(cdp: FakeCDP, status: int) -> Any:
    def fire(url: str) -> None:
        response = {
            "url": url,
            "status": status,
            "mimeType": "text/plain",
            "headers": {"Server": "AkamaiGHost", "Set-Cookie": "_abck=x", "Retry-After": "120"},
        }
        cdp.handlers["Network.responseReceived"]({"type": "Document", "response": response})

    return fire


@pytest.mark.parametrize("status", [200, 403, None])
def test_robots_status_comes_from_network_events_when_navigation_gives_no_response(
    status: int | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = FakeBrowser()
    fake = FakePlaywright(browser)
    page = browser.contexts[0].pages[0]
    page.text = (
        "User-agent: *\nDisallow: /checkout\n" if status == 200 else "Access Denied Reference #18.ab.1"
    )
    if status is not None:
        page.events = _document_event(browser.contexts[0].cdp, status)
    s = _session(tmp_path, monkeypatch, fake)

    async def run() -> None:
        async with s:
            await s.load_robots(f"{BASE}/robots.txt")

    if status == 200:
        asyncio.run(run())
        assert s.robots is not None and not s.robots.allowed(f"{BASE}/checkout")
    else:
        expected = browser_mod.ChallengeDetected if status == 403 else browser_mod.NoDocumentResponse
        with pytest.raises(expected):
            asyncio.run(run())
    fetch = s.fetches[0]
    assert fetch.status == status and fetch.dom_key  # evidence kept in every case
    if status is None:
        assert fetch.notes["response_object"] == "missing" and fetch.screenshot_key
    else:
        doc = fetch.notes["document"]
        assert doc["headers"] == {"server": "AkamaiGHost", "retry-after": "120"}  # no cookies kept
    assert browser.closed == 1


SEARCH = f"{BASE}/atlas/v1/search/v1/products-search?filter.locationId=53100503&filter.taxonomies=01006"


def _data_request(cdp: FakeCDP, rid: str, body: str) -> None:
    cdp.bodies[rid] = body
    request = {"url": SEARCH, "method": "GET", "headers": {"Cookie": "_abck=x", "x-laf-object": "[]"}}
    cdp.handlers["Network.requestWillBeSent"]({"requestId": rid, "request": request})
    response = {
        "url": SEARCH,
        "status": 200,
        "headers": {"Set-Cookie": "x=1", "Content-Type": "application/json"},
    }
    cdp.handlers["Network.responseReceived"]({"requestId": rid, "type": "Fetch", "response": response})
    cdp.handlers["Network.loadingFinished"]({"requestId": rid, "encodedDataLength": len(body)})


def test_data_responses_are_captured_over_cdp_with_redacted_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = FakeBrowser()
    s = _session(tmp_path, monkeypatch, FakePlaywright(browser))

    async def run() -> None:
        async with s:
            s._new_fetch("listing", f"{BASE}/pl/canned-foods/01006")
            _data_request(browser.contexts[0].cdp, "7", json.dumps({"data": {"productsSearch": []}}))
            await s.drain()

    asyncio.run(run())
    (rec,) = s.captured
    assert (rec.kind, rec.status, rec.request_location_id, rec.json_ok) == (
        "products_search",
        200,
        "53100503",
        True,
    )
    assert rec.request_headers == {"x-laf-object": "[]"} and rec.response_headers == {
        "content-type": "application/json"
    }
    assert rec.artifact_key and (tmp_path / rec.artifact_key).is_file()
    assert s.fetches[0].captured == [rec]


def test_a_capture_that_never_finishes_is_abandoned_not_waited_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = FakeBrowser()
    browser.contexts[0].cdp.hang = True
    s = _session(tmp_path, monkeypatch, FakePlaywright(browser))

    async def run() -> None:
        async with s:
            s._new_fetch("listing", f"{BASE}/pl/canned-foods/01006")
            _data_request(browser.contexts[0].cdp, "8", "{}")
            await s.drain(timeout_s=0.05)

    asyncio.run(run())
    assert any(e.code == "CAPTURE_ABANDONED" for e in s.events)
    assert browser.closed == 1


def test_the_page_copy_is_kept_when_the_screenshot_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser = FakeBrowser()
    page = browser.contexts[0].pages[0]

    async def broken(**kw: Any) -> bytes:
        raise PlaywrightError("Target crashed")

    page.screenshot = broken  # type: ignore[method-assign]
    s = _session(tmp_path, monkeypatch, FakePlaywright(browser))

    async def run() -> None:
        async with s:
            fetch = s._new_fetch("store_page", f"{BASE}/stores/x")
            await s.save_evidence(fetch, "<html><body>Marianos Lakeshore East</body></html>", screenshot=True)

    asyncio.run(run())
    fetch = s.fetches[0]
    assert (
        fetch.dom_key and fetch.screenshot_key is None and "Target crashed" in fetch.notes["screenshot_error"]
    )


def test_next_step_projection_does_not_repeat_the_first_heavy_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = _session(tmp_path, monkeypatch, FakePlaywright(FakeBrowser()))
    assert s.projected_step_bytes() == 0
    s._step_sizes = [5_000, 3_000_000]  # robots.txt, then the first page with the site's scripts
    assert s.projected_step_bytes() == 1_000_000
    s._step_sizes.append(1_400_000)  # a later page heavier than a third of the first
    assert s.projected_step_bytes() == 1_400_000


def test_scrapfly_is_the_provider_by_default_with_one_browser() -> None:
    assert AcquisitionSettings().browser_provider is BrowserProvider.SCRAPFLY
    assert ScrapflyBrowserSettings().concurrency == 1


# -- store verification ------------------------------------------------------------------------------


def _page(**state: Any) -> str:
    hdr = syn.header(modality_word=state.pop("word", "In-Store"))
    return syn.page(hdr, state=syn.state_script(**state))


def _verify(
    html: str, store: StoreConfig, settings: Settings, urls: tuple[str, ...] = ()
) -> sp.StoreVerification:
    return sp.verify_store(
        store, settings, html, fetch_id="f", purpose="listing", url="u", data_request_urls=urls
    )


def test_store_verification_passes_only_for_an_explicit_in_store_selection(
    dev_store: StoreConfig, settings: Settings
) -> None:
    ok = _verify(
        _page(),
        dev_store,
        settings,
        (f"{BASE}/atlas/v1/search/v1/products-search?filter.locationId=53100503",),
    )
    assert ok.passed, ok.failures()
    default = _verify(
        _page(modality="PICKUP", source="DEFAULT_MODALITY_ADDRESS", trusted=False, word="Pickup"),
        dev_store,
        settings,
    )
    assert not default.passed
    assert {c.name for c in default.checks if c.ok is False} == {"fulfillment", "explicit_selection"}
    other = _verify(_page(location_id="53100511"), dev_store, settings)
    assert {"location_id", "postal_code"} & {c.name for c in other.checks if c.ok is False}
    moved = _verify(_page(address="1 Other St"), dev_store, settings)
    assert "address" in {c.name for c in moved.checks if c.ok is False}
    wrong_request = _verify(
        _page(),
        dev_store,
        settings,
        (f"{BASE}/atlas/v1/search/v1/products-search?filter.locationId=53100999",),
    )
    assert not wrong_request.passed and "data_requests" in {
        c.name for c in wrong_request.checks if c.ok is False
    }
    no_state = _verify(syn.page(syn.header()), dev_store, settings)
    assert not no_state.passed


# -- product page parser -----------------------------------------------------------------------------


# -- records from saved evidence ----------------------------------------------------------------------


def _detector(private_label: PrivateLabelConfig, settings: Settings) -> PrivateLabelDetector:
    return PrivateLabelDetector(private_label, settings.records.store_brand_positive_value)


STAGE1_FETCHES = [  # the measured weights of the live stage 1 of 2026-10-20 00:52 UTC
    {"purpose": "robots", "notes": {"bytes_received": 6_247}},
    {"purpose": "listing", "notes": {"bytes_received": 1_339_085}},
    {"purpose": "open_store_picker", "notes": {"bytes_received": 29_356}},
    {"purpose": "choose_in_store", "notes": {"bytes_received": 10_984}},
    {"purpose": "search_postal_code", "notes": {"bytes_received": 499_107}},
    {"purpose": "pick_store", "notes": {"bytes_received": 2_088}},
    {"purpose": "confirm_store", "notes": {"bytes_received": 343_531}},
    {"purpose": "listing_after_selection", "notes": {"bytes_received": 265_509}},
]


def test_a_data_request_is_scoped_by_its_url_or_its_laf_header(
    dev_store: StoreConfig, settings: Settings
) -> None:
    laf = json.dumps([{"modality": {"type": "IN_STORE", "handoffLocation": {"storeId": "53100503"}}}])
    v2 = f"{BASE}/atlas/v1/product/v2/products?filter.gtin13s=0006414428243"
    assert sp.request_scope(v2, {"x-laf-object": laf}) == {
        "store_ids": ["53100503"],
        "modalities": ["IN_STORE"],
    }
    assert sp.request_scope(SEARCH, {})["store_ids"] == ["53100503"]
    live_case = sp.verify_store(  # products/v2 carries the store only in its header (live, 2026-10-20)
        dev_store,
        settings,
        _page(),
        fetch_id="f",
        purpose="listing",
        url="u",
        data_request_urls=(SEARCH, v2),
        data_request_headers=({}, {"x-laf-object": laf}),
    )
    assert live_case.passed, live_case.failures()
    check = next(c for c in live_case.checks if c.name == "data_requests")
    assert (check.observed["store_ids"], check.observed["without_store"]) == (["53100503"], 0)
    unscoped = _verify(_page(), dev_store, settings, (SEARCH, v2))  # no header saved: reported, not failed
    check = next(c for c in unscoped.checks if c.name == "data_requests")
    assert unscoped.passed and check.observed["without_store"] == 1
    other = json.dumps([{"modality": {"type": "IN_STORE", "handoffLocation": {"storeId": "53100526"}}}])
    pickup = json.dumps([{"modality": {"type": "PICKUP", "handoffLocation": {"storeId": "53100503"}}}])
    for header in (other, pickup):
        bad = sp.verify_store(
            dev_store,
            settings,
            _page(),
            fetch_id="f",
            purpose="listing",
            url="u",
            data_request_urls=(v2,),
            data_request_headers=({"x-laf-object": header},),
        )
        assert not bad.passed and "data_requests" in {c.name for c in bad.checks if c.ok is False}


def test_a_cookie_source_alone_does_not_prove_an_explicit_store_selection(
    dev_store: StoreConfig, settings: Settings
) -> None:
    # live, 2026-10-20: a site-default page also reported FALLBACK_ACTIVE_MODALITY_COOKIE
    html = _page(source="FALLBACK_ACTIVE_MODALITY_COOKIE")

    def check(selected: bool | None) -> bool | None:
        v = sp.verify_store(
            dev_store, settings, html, fetch_id="f", purpose="listing", url="u", selected_before=selected
        )
        return next(c.ok for c in v.checks if c.name == "explicit_selection")

    assert check(False) is False and check(True) is True
    order = ["R", "L0", "C1", "L1"]
    selection = [{"step": "confirm_store", "found": True, "fetch_id": "C1"}]
    assert sp.picker_confirmed_before(selection, order, "L1") is True
    assert sp.picker_confirmed_before(selection, order, "L0") is False
    assert sp.picker_confirmed_before([{"step": "confirm_store", "found": False}], order, "L1") is False
