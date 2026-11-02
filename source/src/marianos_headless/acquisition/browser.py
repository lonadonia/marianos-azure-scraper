"""Anonymous, read-only browser session (brief §3, §5.2 mode A UI_CAPTURE).

Stock Playwright Chromium with its default identity: no stealth plugins, no user-agent or fingerprint
changes, no injected cookies or headers. One context and one page. Every navigation and UI action
waits its turn with the :class:`Pacer`, is checked against robots.txt, and is screened for challenge
pages. A challenge stops the session after its evidence is saved.

With ``browser_provider: scrapfly`` (a provider pilot, ADR-008) the browser is Scrapfly's Cloud Browser,
reached over CDP; the provider supplies the context and its fingerprint, which are used unchanged. The
session meters received bytes into a credit estimate, stops before the run's credit cap, and always
closes the remote browser (success, error, timeout or cancellation) so billing stops.

Traffic controls (cloud browser): a *resource policy* decides which requests the page may make (the rest
are aborted before they leave the browser, e.g. Walmart listing pages are read as their HTML document
only), and a *traffic ceiling* aborts every further request once the metered bytes reach it, so one page
cannot run past the session's credit room while it loads. Both act in Playwright's request filter;
``routed`` counts the requests that reached it, because a remote browser can serve pages without
Playwright seeing their requests (then neither control acts, and only the credit checks before each step
and the provider's own stubbing limit the traffic).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    Route,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from pydantic import SecretStr

from marianos_headless.acquisition import scrapfly
from marianos_headless.acquisition.capture import (
    DOCUMENT_HEADER_ALLOWLIST,
    REQUEST_HEADER_ALLOWLIST,
    RESPONSE_HEADER_ALLOWLIST,
    CapturedResponse,
    classify_url,
    gzip_bytes,
    query_values,
    redact_headers,
)
from marianos_headless.acquisition.challenge import (
    MARIANOS_STATE_MARKER,
    ChallengeVerdict,
    blocked_response,
    detect_document_challenge,
    is_rate_limit_only,
    parse_retry_after,
)
from marianos_headless.acquisition.pacing import Pacer
from marianos_headless.acquisition.robots import RobotsPolicy, parse_robots
from marianos_headless.core.ids import new_id
from marianos_headless.core.settings import AcquisitionSettings, BrowserProvider
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.sites.marianos.sanitize import sanitize_html
from marianos_headless.storage.base import StorageAdapter

# (url, resource type) -> may the page make this request?
ResourcePolicy = Callable[[str, str], bool]


def trace_url(url: str) -> str:
    """A traced request's address without its query or fragment (they can carry visitor IDs)."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"[:300]


class ChallengeDetected(RuntimeError):
    def __init__(self, fetch: PageFetch):
        super().__init__(f"challenge on {fetch.url}: {', '.join(fetch.challenge.reasons)}")
        self.fetch = fetch


class RateLimited(ChallengeDetected):
    """A plain HTTP 429: the page is stopped like a challenge (so existing handlers stay safe), and the
    worker may pause the category for ``retry_after_s`` (the site's ``Retry-After``, when it sent one)
    before a single retry; a second 429 blocks the category (``worker.retry.decide``)."""

    def __init__(self, fetch: PageFetch, retry_after_s: float | None):
        super().__init__(fetch)
        self.retry_after_s = retry_after_s


def _refusal(fetch: PageFetch, retry_after_header: str | None) -> ChallengeDetected:
    if retry_after_header is not None:
        fetch.notes["retry_after"] = retry_after_header[:100]
    if is_rate_limit_only(fetch.challenge):
        return RateLimited(fetch, parse_retry_after(retry_after_header, utcnow()))
    return ChallengeDetected(fetch)


class NavigationFailed(PlaywrightError):
    """The navigation itself failed (connection reset/closed, proxy error, timeout): no document.
    Still a ``PlaywrightError`` for existing handlers; ``fetch`` holds the evidence."""

    def __init__(self, fetch: PageFetch, message: str):
        super().__init__(message)
        self.fetch = fetch


class RobotsDisallowed(RuntimeError):
    pass


class RobotsUnreachable(RobotsDisallowed):
    """robots.txt could not be fetched at all (connection reset, TLS/DNS failure)."""


class NoDocumentResponse(RobotsUnreachable):
    """The navigation ended without any document response the session could see: a tooling fault, not
    an answer from the site."""


@dataclass
class PageFetch:
    fetch_id: str
    purpose: str
    url: str
    final_url: str = ""
    status: int | None = None
    started_at: str = ""
    duration_ms: int | None = None
    challenge: ChallengeVerdict = field(default_factory=lambda: ChallengeVerdict(False))
    dom_key: str | None = None
    screenshot_key: str | None = None
    captured: list[CapturedResponse] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["challenge"] = asdict(self.challenge)
        return d


@dataclass
class Event:
    ts: str
    level: str
    code: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


class BrowserSession:
    def __init__(
        self,
        settings: AcquisitionSettings,
        storage: StorageAdapter,
        run_prefix: str,
        *,
        max_navigations: int | None = None,
        provider_key: SecretStr | None = None,
        max_credits: float | None = None,
        state_marker: str = MARIANOS_STATE_MARKER,
        sanitizer: Callable[[str], tuple[str, Any]] = sanitize_html,
    ):
        self.session_id = new_id()  # this session's own ID, in its events and the run's evidence
        self.state_marker = state_marker  # the page data a content page of the site embeds
        self.sanitizer = sanitizer
        self._policy: ResourcePolicy | None = None
        self._routed = False
        self.byte_ceiling: int | None = None  # metered bytes after which every request is aborted
        self.blocked: dict[str, int] = {}  # aborted requests by reason and resource type
        # Requests that reached the request filter: 0 after a page load means the browser connection does
        # not apply it (the policy and the traffic ceiling are then not enforced in the browser).
        self.routed = 0
        self._trace: list[dict[str, Any]] | None = None  # network trace of selected requests (diagnosis)
        self._trace_match: Callable[[str], bool] | None = None
        self._trace_ids: dict[str, dict[str, Any]] = {}
        self._trace_t0 = 0.0
        self.settings = settings
        self.storage = storage
        self.prefix = run_prefix.rstrip("/")
        self.pacer = Pacer(
            settings.navigation_min_interval_s,
            settings.navigation_interval_jitter_s,
            max_navigations=max_navigations,
        )
        self.robots: RobotsPolicy | None = None
        self.robots_text: str | None = None
        self.events: list[Event] = []
        self.fetches: list[PageFetch] = []
        self.captured: list[CapturedResponse] = []
        self._current: PageFetch | None = None
        self._seq = 0
        self._pending: set[asyncio.Task[None]] = set()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.provider = settings.browser_provider
        self._provider_key = provider_key
        self.max_credits = (
            max_credits
            if max_credits is not None
            else settings.scrapfly.max_credits_per_run
            if self.provider is BrowserProvider.SCRAPFLY
            else None
        )
        self.meter: scrapfly.CreditMeter | None = None
        self._request_urls: dict[str, str] = {}
        self._cdp: Any = None  # the session's own CDP connection (cloud browser only)
        self._cdp_capture: dict[str, dict[str, Any]] = {}  # requestId -> data request being captured
        self._step_sizes: list[int] = []  # bytes received per navigation or action
        self.documents: list[dict[str, Any]] = []  # top-level document responses seen over CDP
        self.closed_at: str | None = None
        self.cdp_bytes = 0  # page content, screenshots and response bodies read over the connection

    # -- lifecycle ---------------------------------------------------------------------------------

    async def __aenter__(self) -> BrowserSession:
        self._pw = await async_playwright().start()
        try:
            if self.provider is BrowserProvider.SCRAPFLY:
                await self._open_scrapfly()
            else:
                await self._open_local()
        except BaseException:
            await self._shutdown()
            raise
        return self

    async def _open_local(self) -> None:
        assert self._pw is not None
        self._browser = await self._pw.chromium.launch(headless=self.settings.headless)
        self.context = await self._browser.new_context()
        self.page = await self.context.new_page()
        self._configure_page(self.page)
        self.event(
            "INFO",
            "BROWSER_STARTED",
            "stock Chromium",
            {
                "version": self._browser.version,
                "headless": self.settings.headless,
                "user_agent": await self.page.evaluate("navigator.userAgent"),
            },
        )

    async def _open_scrapfly(self) -> None:
        """Connect to Scrapfly's Cloud Browser and use the context it supplies (never a new one, no
        fingerprint overrides). The authenticated endpoint is never logged; errors are redacted."""
        assert self._pw is not None
        cfg = self.settings.scrapfly
        key = self._provider_key
        if key is None or not key.get_secret_value():
            raise scrapfly.ProviderError(scrapfly.ProviderErrorKind.AUTH, f"{scrapfly.ENV_KEY} is not set")
        failure: str | None = None
        try:
            self._browser = await self._pw.chromium.connect_over_cdp(
                scrapfly.ws_endpoint(cfg, key), timeout=cfg.connect_timeout_s * 1000
            )
        except PlaywrightError as exc:
            failure = " ".join(scrapfly.redact(str(exc), key).split())[:500]
        if failure is not None:  # raised outside the handler: the unredacted error is not chained
            self.event("ERROR", "PROVIDER_CONNECT_FAILED", failure)
            raise scrapfly.ProviderError(scrapfly.classify_connect_error(failure), failure)
        assert self._browser is not None
        contexts = self._browser.contexts
        if not contexts:
            raise scrapfly.ProviderError(scrapfly.ProviderErrorKind.PROVIDER, "no browser context supplied")
        self.context = contexts[0]
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        self.meter = scrapfly.CreditMeter(scrapfly.rate_per_mb(cfg), cfg.bandwidth_overhead_factor)
        meter_source = await self._attach_meter(self.context, self.page)
        if self._cdp is not None:
            try:  # requests a service worker would make itself could pass the resource policy unseen
                await self._cdp.send("Network.setBypassServiceWorker", {"bypass": True})
            except Exception as exc:
                self.event("WARN", "SERVICE_WORKER_BYPASS_FAILED", f"{type(exc).__name__}")
        self._configure_page(self.page)
        try:
            user_agent = await asyncio.wait_for(self.page.evaluate("navigator.userAgent"), 15)
        except Exception:  # informational only
            user_agent = None
        self.event(
            "INFO",
            "BROWSER_STARTED",
            "Scrapfly Cloud Browser (provider pilot, ADR-008)",
            {
                "provider": "scrapfly",
                "session_id": self.session_id,
                "endpoint": scrapfly.public_endpoint(cfg),
                "version": self._browser.version,
                "user_agent": user_agent,
                "meter": meter_source,
                "max_credits": self.max_credits,
            },
        )

    async def _attach_meter(self, context: BrowserContext, page: Page) -> str:
        """Count received bytes per response from CDP ``Network.loadingFinished`` events."""
        try:
            cdp = await context.new_cdp_session(page)
            self._cdp = cdp
            cdp.on("Network.requestWillBeSent", self._on_cdp_request)
            cdp.on("Network.responseReceived", self._on_cdp_response)
            cdp.on("Network.loadingFinished", self._on_cdp_finished)
            cdp.on("Network.loadingFailed", self._on_cdp_failed)
            await cdp.send("Network.enable")
            return "cdp"
        except Exception as exc:  # fall back to Playwright's per-request sizes
            self.event("WARN", "METER_FALLBACK", f"{type(exc).__name__}: {str(exc)[:200]}")
            page.on("requestfinished", lambda req: self._track(self._meter_request(req)))
            return "playwright"

    def _on_cdp_request(self, params: dict[str, Any]) -> None:
        req = params.get("request") or {}
        rid, url = str(params.get("requestId")), str(req.get("url") or "")
        self._request_urls[rid] = url
        if self._trace is not None and self._trace_match is not None and self._trace_match(url):
            entry = {
                "t_ms": int((monotonic() - self._trace_t0) * 1000),
                "method": str(req.get("method") or "GET"),
                "url": trace_url(url),
                "type": params.get("type"),
                "status": None,
                "bytes": None,
                "failed": None,
            }
            self._trace.append(entry)
            self._trace_ids[rid] = entry
        if self._current is not None and classify_url(url) is not None:
            self._cdp_capture[rid] = {
                "url": url,
                "method": str(req.get("method") or "GET"),
                "request_headers": {str(k): str(v) for k, v in (req.get("headers") or {}).items()},
                "fetch": self._current,
            }

    def _on_cdp_response(self, params: dict[str, Any]) -> None:
        """Keep every document response (status, type, allowlisted headers): the status is known even
        when Playwright's navigation returns no response object. Data requests being captured get
        their status and headers here too."""
        r = params.get("response") or {}
        traced = self._trace_ids.get(str(params.get("requestId")))
        if traced is not None:
            traced["status"] = r.get("status")
        entry = self._cdp_capture.get(str(params.get("requestId")))
        if entry is not None:
            entry["status"] = r.get("status")
            entry["response_headers"] = {str(k): str(v) for k, v in (r.get("headers") or {}).items()}
        if params.get("type") != "Document":
            return
        headers = {str(k): str(v) for k, v in (r.get("headers") or {}).items()}
        self.documents.append(
            {
                "url": str(r.get("url") or ""),
                "status": r.get("status"),
                "mime_type": r.get("mimeType"),
                "headers": redact_headers(headers, DOCUMENT_HEADER_ALLOWLIST),
                "observed_at": iso(utcnow()),
            }
        )

    def document_for(self, *urls: str) -> dict[str, Any] | None:
        """The latest document response seen for any of ``urls``."""
        wanted = {u for u in urls if u}
        return next((d for d in reversed(self.documents) if d["url"] in wanted), None)

    def _on_cdp_failed(self, params: dict[str, Any]) -> None:
        traced = self._trace_ids.pop(str(params.get("requestId")), None)
        if traced is not None:
            traced["failed"] = str(params.get("blockedReason") or params.get("errorText") or "failed")[:80]

    def start_trace(self, match: Callable[[str], bool]) -> None:
        """Record the requests whose URL ``match`` accepts (method, address without its query, type,
        status, bytes, failure) until :meth:`stop_trace`: a diagnosis of what the page itself sent."""
        self._trace, self._trace_match, self._trace_ids = [], match, {}
        self._trace_t0 = monotonic()

    def stop_trace(self) -> list[dict[str, Any]]:
        trace = self._trace or []
        self._trace, self._trace_match, self._trace_ids = None, None, {}
        return trace

    def _on_cdp_finished(self, params: dict[str, Any]) -> None:
        rid = str(params.get("requestId"))
        traced = self._trace_ids.pop(rid, None)
        if traced is not None:
            traced["bytes"] = int(params.get("encodedDataLength") or 0)
        if self.meter is not None:
            url = self._request_urls.pop(rid, "")
            self.meter.add(url, int(params.get("encodedDataLength") or 0))
        entry = self._cdp_capture.pop(rid, None)
        if entry is not None:
            self._track(self._capture_cdp(rid, entry))

    async def _capture_cdp(self, rid: str, entry: dict[str, Any]) -> None:
        """A data response read over the session's own CDP connection (``Network.getResponseBody``):
        through the cloud browser, Playwright's response objects never complete."""
        fetch: PageFetch = entry["fetch"]
        url = entry["url"]
        kind = classify_url(url) or "atlas_other"
        self._seq += 1
        seq = self._seq
        rec = CapturedResponse(
            seq=seq,
            fetch_id=fetch.fetch_id,
            kind=kind,
            url=url,
            method=entry["method"],
            status=int(entry.get("status") or 0),
            request_location_id=next(iter(query_values(url, "filter.locationId")), None),
            request_taxonomies=query_values(url, "filter.taxonomies"),
            request_headers=redact_headers(entry["request_headers"], REQUEST_HEADER_ALLOWLIST),
            response_headers=redact_headers(entry.get("response_headers") or {}, RESPONSE_HEADER_ALLOWLIST),
            body_sha256=None,
            body_bytes=0,
            artifact_key=None,
            observed_at=iso(utcnow()),
        )
        try:
            res = await asyncio.wait_for(self._cdp.send("Network.getResponseBody", {"requestId": rid}), 15)
            raw = str(res.get("body") or "")
            body = base64.b64decode(raw) if res.get("base64Encoded") else raw.encode("utf-8")
            self.cdp_bytes += len(body)
            rec.body_sha256 = hashlib.sha256(body).hexdigest()
            rec.body_bytes = len(body)
            if blocked_response(body):
                rec.extra["challenge"] = "bot_manager_block_response"
            try:
                json.loads(body)
                rec.json_ok = True
            except ValueError:
                rec.json_ok = False
            key = f"{self.prefix}/raw/{fetch.fetch_id}.{seq:04d}.{kind}.json.gz"
            self.storage.put_bytes(key, gzip_bytes(body), "application/gzip")
            rec.artifact_key = key
        except Exception as exc:  # evicted, redirected or aborted: no body
            rec.error = f"{type(exc).__name__}: {str(exc)[:200]}"
        fetch.captured.append(rec)
        self.captured.append(rec)

    async def _meter_request(self, req: Any) -> None:
        if self.meter is None:
            return
        try:
            sizes = await req.sizes()
            self.meter.add(req.url, sizes["responseBodySize"] + sizes["responseHeadersSize"])
        except Exception:
            pass

    def _track(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def _configure_page(self, page: Page) -> None:
        page.set_default_navigation_timeout(self.settings.page_load_timeout_s * 1000)
        page.set_default_timeout(self.settings.response_wait_timeout_s * 1000)
        if self.provider is not BrowserProvider.SCRAPFLY:  # the cloud browser captures over CDP
            page.on("response", self._on_response)

    async def __aexit__(self, *exc: object) -> None:
        await self._shutdown()

    async def _shutdown(self) -> None:
        """Always runs to the end: drain captures, close the browser (for Scrapfly this disconnects and
        the provider stops the session: ``auto_close=true``), stop Playwright."""
        try:
            await self.drain()
        except Exception as exc:
            self.event("WARN", "DRAIN_FAILED", f"{type(exc).__name__}")
        if self._browser is not None:
            try:
                await asyncio.wait_for(self._browser.close(), 30)
                self.closed_at = iso(utcnow())
                self.event("INFO", "BROWSER_CLOSED", self.provider.value, self.cost_snapshot())
            except Exception as exc:
                text = scrapfly.redact(str(exc), self._provider_key)[:300]
                self.event("WARN", "BROWSER_CLOSE_FAILED", f"{type(exc).__name__}: {text}")
            self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception as exc:
                self.event("WARN", "PLAYWRIGHT_STOP_FAILED", f"{type(exc).__name__}")
            self._pw = None

    def cost_snapshot(self) -> dict[str, Any]:
        if self.meter is None:
            return {}
        return {
            "session_id": self.session_id,
            "estimate": self.meter.estimate().as_dict(),
            "responses": self.meter.responses,
            "connection_bytes_read": self.cdp_bytes,  # not counted in the estimate (see ADR-008)
            "requests_blocked": dict(self.blocked),
            "requests_routed": self.routed,
            "bytes_by_host": self.meter.top_hosts(),
        }

    # -- traffic controls --------------------------------------------------------------------------

    async def set_resource_policy(self, policy: ResourcePolicy | None) -> None:
        """From now on the page may make only the requests ``policy`` allows (``None``: all). Refused
        requests are aborted in the browser, so they cost no traffic; they are counted in ``blocked``."""
        self._policy = policy
        if policy is not None:
            await self._ensure_route()

    async def set_byte_ceiling(self, ceiling: int | None) -> None:
        """Abort every request once the metered bytes reach ``ceiling`` (responses already on their way
        still land: the session's credit room keeps headroom for them)."""
        self.byte_ceiling = ceiling
        if ceiling is not None:
            await self._ensure_route()

    async def _ensure_route(self) -> None:
        if not self._routed and self.page is not None:
            await self.page.route("**/*", self._route)
            self._routed = True

    async def _route(self, route: Route) -> None:
        req = route.request
        self.routed += 1
        reason = ""
        ceiling = self.byte_ceiling
        if ceiling is not None and self.meter is not None and self.meter.bytes_seen >= ceiling:
            reason = "traffic_ceiling"
        elif self._policy is not None and not self._policy(req.url, req.resource_type):
            reason = "policy"
        try:
            if reason:
                key = f"{reason}:{req.resource_type}"
                self.blocked[key] = self.blocked.get(key, 0) + 1
                await route.abort("blockedbyclient")
            else:
                await route.continue_()
        except PlaywrightError:
            pass  # the page or the request went away meanwhile

    def projected_step_bytes(self) -> int:
        """What the next step may receive: the heaviest step is the first page (it loads the site's
        scripts) and is not assumed to repeat; the second heaviest, or a third of the heaviest, is."""
        sizes = sorted(self._step_sizes, reverse=True)
        if not sizes:
            return 0
        return max(sizes[1] if len(sizes) > 1 else 0, sizes[0] // 3)

    def check_budget(self) -> None:
        """Refuse the next step if it could take the estimate past ``max_credits``."""
        if self.meter is None or self.max_credits is None:
            return
        projected = self.meter.estimate(extra_bytes=self.projected_step_bytes(), extra_s=30)
        if projected.credits > self.max_credits:
            data = {"projected": projected.as_dict(), "max_credits": self.max_credits}
            self.event("WARN", "PROVIDER_BUDGET_REACHED", "credit cap would be exceeded", data)
            raise scrapfly.ProviderError(
                scrapfly.ProviderErrorKind.BUDGET,
                f"next step could reach {projected.credits:.0f} credits (cap {self.max_credits})",
            )

    def _step_bytes(self, before: int) -> int:
        if self.meter is None:
            return 0
        step = self.meter.bytes_seen - before
        self._step_sizes.append(step)
        return step

    def event(self, level: str, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        self.events.append(Event(iso(utcnow()), level, code, message, data or {}))

    # -- robots ------------------------------------------------------------------------------------

    async def load_robots(self, url: str) -> RobotsPolicy:
        """Fetch robots.txt *through the browser page*, so every request carries the same stock
        Chromium identity (§3.3). Playwright's APIRequestContext would send a Chrome user-agent over
        Node's own HTTP/TLS stack, which is not the browser's identity."""
        assert self.page is not None
        self.check_budget()
        await self.pacer.wait_turn()
        fetch = self._new_fetch("robots", url)
        t0 = monotonic()
        before = self.meter.bytes_seen if self.meter else 0
        try:
            resp = await self.page.goto(url, wait_until="domcontentloaded")
        except PlaywrightError as exc:
            # Connection reset/refused, TLS or DNS failure: no robots.txt, so no crawling (fail closed).
            fetch.duration_ms = int((monotonic() - t0) * 1000)
            fetch.notes["network_error"] = self._error_text(exc)
            fetch.notes["error_side"] = scrapfly.classify_navigation_error(fetch.notes["network_error"])
            self.event("WARN", "ROBOTS_UNREACHABLE", url, {"error": fetch.notes["network_error"]})
            raise RobotsUnreachable(f"robots.txt unreachable: {fetch.notes['network_error']}") from None
        status: int | None
        retry_after: str | None
        if resp is not None:
            text = await resp.text()
            status, fetch.final_url, retry_after = resp.status, resp.url, resp.headers.get("retry-after")
        else:
            # Some remote browsers serve the document without Playwright seeing the navigation request:
            # the status then comes from the CDP network events and the text from the rendered document.
            await self.page.wait_for_timeout(500)
            fetch.final_url = self.page.url
            doc = self.document_for(url, fetch.final_url)
            fetch.notes["response_object"] = "missing; status from CDP network events" if doc else "missing"
            if doc is None:
                await self.save_evidence(fetch, await self.page.content(), screenshot=True)
                self.event("WARN", "ROBOTS_NO_RESPONSE", url, {"fetch_id": fetch.fetch_id})
                raise NoDocumentResponse("robots.txt navigation gave no response and no document was seen")
            fetch.notes["document"] = doc
            status, retry_after = doc["status"], doc["headers"].get("retry-after")
            text = str(await self.page.evaluate("() => document.body ? document.body.innerText : ''"))
        fetch.status = status
        fetch.duration_ms = int((monotonic() - t0) * 1000)
        if self.meter is not None:
            await self.page.wait_for_timeout(500)  # let the byte count of this response arrive
            fetch.notes["bytes_received"] = self._step_bytes(before)
        key = f"{self.prefix}/robots/{fetch.fetch_id}.status{status}.txt"
        self.storage.put_bytes(key, text.encode("utf-8"), "text/plain")
        fetch.dom_key = key
        if status != 200:
            # Fail closed: an unreadable robots.txt never means "allow all" here. A 401/403/429 or a
            # denial page is a challenge and stops the run before any page is requested.
            fetch.challenge = detect_document_challenge(status, text, expect_initial_state=False)
            self.event(
                "WARN",
                "CHALLENGE_DETECTED" if fetch.challenge.is_challenge else "ROBOTS_UNAVAILABLE",
                url,
                {"status": status, "reasons": list(fetch.challenge.reasons)},
            )
            if fetch.challenge.is_challenge:
                raise _refusal(fetch, retry_after)
            raise RobotsDisallowed(f"robots.txt unavailable (HTTP {status}); refusing to crawl")
        self.robots_text = text
        self.robots = parse_robots(text)
        self.event(
            "INFO",
            "ROBOTS_FETCHED",
            url,
            {
                "status": status,
                "sha256": self.robots.sha256,
                "disallow": self.robots.disallowed_patterns(),
            },
        )
        return self.robots

    def check_allowed(self, url: str) -> None:
        if self.robots is None:
            raise RobotsDisallowed("robots.txt not loaded; refusing to navigate")
        if not self.robots.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")

    # -- capture -----------------------------------------------------------------------------------

    def _on_response(self, resp: Response) -> None:
        kind = classify_url(resp.url)
        if kind is None or self._current is None:
            return
        task = asyncio.ensure_future(self._capture(resp, kind, self._current))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _capture(self, resp: Response, kind: str, fetch: PageFetch) -> None:
        self._seq += 1
        seq = self._seq
        req = resp.request
        rec = CapturedResponse(
            seq=seq,
            fetch_id=fetch.fetch_id,
            kind=kind,
            url=resp.url,
            method=req.method,
            status=resp.status,
            request_location_id=next(iter(query_values(resp.url, "filter.locationId")), None),
            request_taxonomies=query_values(resp.url, "filter.taxonomies"),
            request_headers={},
            response_headers={},
            body_sha256=None,
            body_bytes=0,
            artifact_key=None,
            observed_at=iso(utcnow()),
        )
        try:
            rec.request_headers = redact_headers(await req.all_headers(), REQUEST_HEADER_ALLOWLIST)
            rec.response_headers = redact_headers(await resp.all_headers(), RESPONSE_HEADER_ALLOWLIST)
            body = await resp.body()
            self.cdp_bytes += len(body)
            rec.body_sha256 = hashlib.sha256(body).hexdigest()
            rec.body_bytes = len(body)
            if blocked_response(body):
                rec.extra["challenge"] = "bot_manager_block_response"
            try:
                json.loads(body)
                rec.json_ok = True
            except ValueError:
                rec.json_ok = False
            key = f"{self.prefix}/raw/{fetch.fetch_id}.{seq:04d}.{kind}.json.gz"
            self.storage.put_bytes(key, gzip_bytes(body), "application/gzip")
            rec.artifact_key = key
        except Exception as exc:  # bodies of redirects/aborted requests are unavailable
            rec.error = f"{type(exc).__name__}: {exc}"[:300]
        fetch.captured.append(rec)
        self.captured.append(rec)

    async def drain(self, timeout_s: float = 20) -> None:
        """Wait for pending captures, at most ``timeout_s``; slower ones are abandoned and reported."""
        if not self._pending:
            return
        _, late = await asyncio.wait(list(self._pending), timeout=timeout_s)
        for task in late:
            task.cancel()
        if late:
            await asyncio.gather(*late, return_exceptions=True)
            self.event("WARN", "CAPTURE_ABANDONED", f"{len(late)} response captures after {timeout_s:.0f} s")

    async def _content(self, timeout_s: float = 60) -> str:
        assert self.page is not None
        try:
            return await asyncio.wait_for(self.page.content(), timeout_s)
        except TimeoutError:
            raise scrapfly.ProviderError(
                scrapfly.ProviderErrorKind.SESSION, f"page content not available within {timeout_s:.0f} s"
            ) from None

    # -- navigation and actions --------------------------------------------------------------------

    def _new_fetch(self, purpose: str, url: str) -> PageFetch:
        f = PageFetch(fetch_id=new_id(), purpose=purpose, url=url, started_at=iso(utcnow()))
        self.fetches.append(f)
        self._current = f
        return f

    def _error_text(self, exc: BaseException) -> str:
        return scrapfly.redact(
            str(exc).splitlines()[0] if str(exc) else type(exc).__name__, self._provider_key
        )[:300]

    async def navigate(
        self, url: str, purpose: str, *, settle_ms: int = 3000, expect_initial_state: bool = True
    ) -> PageFetch:
        assert self.page is not None
        self.check_allowed(url)
        self.check_budget()
        await self.pacer.wait_turn()
        fetch = self._new_fetch(purpose, url)
        t0 = monotonic()
        before = self.meter.bytes_seen if self.meter else 0
        try:
            resp = await self.page.goto(url, wait_until="domcontentloaded")
        except PlaywrightError as exc:
            fetch.duration_ms = int((monotonic() - t0) * 1000)
            fetch.notes["network_error"] = self._error_text(exc)
            fetch.notes["error_side"] = scrapfly.classify_navigation_error(fetch.notes["network_error"])
            fetch.notes["bytes_received"] = self._step_bytes(before)
            self.event(
                "WARN",
                "NAVIGATION_FAILED",
                url,
                {"fetch_id": fetch.fetch_id, "error": fetch.notes["network_error"]},
            )
            raise NavigationFailed(fetch, fetch.notes["network_error"]) from None
        try:
            await self.page.wait_for_load_state("networkidle", timeout=settle_ms + 10_000)
        except Exception:
            fetch.notes["networkidle_timeout"] = True
        await self.page.wait_for_timeout(settle_ms)  # let late XHRs land (part of the politeness gap)
        fetch.duration_ms = int((monotonic() - t0) * 1000)
        fetch.final_url = self.page.url
        retry_after: str | None = None
        if resp is not None:
            fetch.status, retry_after = resp.status, resp.headers.get("retry-after")
        else:  # as in load_robots: the status from the CDP network events, when they show the document
            doc = self.document_for(url, fetch.final_url)
            fetch.notes["response_object"] = "missing; status from CDP network events" if doc else "missing"
            if doc is not None:
                fetch.notes["document"] = doc
                fetch.status, retry_after = doc["status"], doc["headers"].get("retry-after")
        html = await self._content()
        fetch.challenge = detect_document_challenge(
            fetch.status, html, expect_initial_state=expect_initial_state, state_marker=self.state_marker
        )
        provider_code = scrapfly.provider_error_in_document(html) if self.meter is not None else None
        if provider_code:
            fetch.notes["provider_error"] = provider_code
        await self.save_evidence(fetch, html, screenshot=True)  # the page copy first, whatever follows
        await self.drain()
        self._blocked_responses(fetch)
        if self.meter is not None:
            fetch.notes["bytes_received"] = self._step_bytes(before)
        self.event(
            "WARN" if fetch.challenge.is_challenge else "INFO",
            "CHALLENGE_DETECTED" if fetch.challenge.is_challenge else "PAGE_CAPTURED",
            url,
            {
                "fetch_id": fetch.fetch_id,
                "status": fetch.status,
                "ms": fetch.duration_ms,
                "captured": len(fetch.captured),
                "reasons": list(fetch.challenge.reasons),
                **({"bytes": fetch.notes["bytes_received"]} if "bytes_received" in fetch.notes else {}),
            },
        )
        if provider_code:
            raise scrapfly.ProviderError(scrapfly.ProviderErrorKind.PROVIDER, f"{provider_code} on {url}")
        if fetch.challenge.is_challenge:
            raise _refusal(fetch, retry_after)
        return fetch

    async def act(
        self,
        purpose: str,
        action: Callable[[Page], Awaitable[Any]],
        *,
        settle_ms: int = 3000,
        check_challenge: bool = True,
        screenshot: bool = True,
    ) -> PageFetch:
        """A UI interaction (click, type). Paced like a navigation; its XHRs are captured. The page copy
        is always saved; ``screenshot=False`` skips the picture (repeated steps of one page), except when
        the step shows a challenge, which is always photographed."""
        assert self.page is not None
        self.check_budget()
        await self.pacer.wait_turn()
        fetch = self._new_fetch(purpose, self.page.url)
        t0 = monotonic()
        before = self.meter.bytes_seen if self.meter else 0
        result = await action(self.page)
        fetch.notes["result"] = (
            result if isinstance(result, (str, int, float, bool, type(None), dict, list)) else str(result)
        )
        await self.page.wait_for_timeout(settle_ms)
        fetch.duration_ms = int((monotonic() - t0) * 1000)
        fetch.final_url = self.page.url
        html = await self._content()
        if check_challenge:
            fetch.challenge = detect_document_challenge(
                None, html, expect_initial_state=False, state_marker=self.state_marker
            )
        await self.save_evidence(fetch, html, screenshot=screenshot or fetch.challenge.is_challenge)
        await self.drain()
        if check_challenge:
            self._blocked_responses(fetch)
        if self.meter is not None:
            fetch.notes["bytes_received"] = self._step_bytes(before)
        self.event(
            "WARN" if fetch.challenge.is_challenge else "INFO",
            "CHALLENGE_DETECTED" if fetch.challenge.is_challenge else "ACTION_CAPTURED",
            purpose,
            {"fetch_id": fetch.fetch_id, "captured": len(fetch.captured), "url": fetch.final_url},
        )
        if fetch.challenge.is_challenge:
            raise ChallengeDetected(fetch)
        return fetch

    def _blocked_responses(self, fetch: PageFetch) -> None:
        """A data request of the step answered by the bot manager's block makes the step a challenge."""
        blocked = [c.url for c in fetch.captured if c.extra.get("challenge")]
        if blocked and not fetch.challenge.is_challenge:
            reasons = (*fetch.challenge.reasons, "bot_manager_block_response")
            fetch.challenge = ChallengeVerdict(
                True, tuple(dict.fromkeys(reasons)), fetch.challenge.http_status
            )
            fetch.notes["blocked_requests"] = [u[:300] for u in blocked]

    async def save_evidence(self, fetch: PageFetch, html: str, *, screenshot: bool) -> None:
        assert self.page is not None
        self.cdp_bytes += len(html.encode("utf-8"))
        sanitized, _ = self.sanitizer(html)
        dom_key = f"{self.prefix}/dom/{fetch.fetch_id}.html.gz"
        self.storage.put_bytes(dom_key, gzip_bytes(sanitized.encode("utf-8")), "application/gzip")
        fetch.dom_key = dom_key
        if screenshot:
            try:
                if self.meter is not None:  # cloud browser: a smaller JPEG travels over the connection
                    img = await asyncio.wait_for(
                        self.page.screenshot(full_page=False, type="jpeg", quality=70), 30
                    )
                    shot_key, ctype = f"{self.prefix}/screens/{fetch.fetch_id}.jpg", "image/jpeg"
                else:
                    img = await asyncio.wait_for(self.page.screenshot(full_page=False), 30)
                    shot_key, ctype = f"{self.prefix}/screens/{fetch.fetch_id}.png", "image/png"
            except Exception as exc:  # the page copy is kept; the missing picture is noted
                fetch.notes["screenshot_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
                return
            self.cdp_bytes += len(img)
            self.storage.put_bytes(shot_key, img, ctype)
            fetch.screenshot_key = shot_key

    async def current_html(self) -> str:
        return await self._content()
