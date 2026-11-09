"""Pages served by the Oxylabs Web API to the live collector (release 1.3.0): no browser runs anywhere on
the collector's side, the provider loads the page with the store and fulfillment given as request
parameters (``store_id``, ``fulfillment_type``).

The session offers what the live collector reads from a browser session: ``load_robots``, ``navigate``
(here a search query or a page URL), ``fetches``, ``events``, ``robots`` and ``closed_at``. Each page is kept
like a browser page (the sanitized markup, gzip, under ``<run>/live/dom/``); the product objects of the page
state are kept as a ``products_v2`` data artifact named after the page (``#page-state``), since the page
itself carries what the browser collector read from the site's data responses. A refusal by the retailer
or the provider stops the page as a challenge would; nothing is retried here beyond the transport's own
attempts.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from typing import Any
from urllib.parse import quote_plus

from marianos_headless.acquisition.browser import (
    ChallengeDetected,
    Event,
    PageFetch,
    RobotsDisallowed,
    _refusal,
)
from marianos_headless.acquisition.capture import CapturedResponse, gzip_bytes
from marianos_headless.acquisition.challenge import MARIANOS_STATE_MARKER, detect_document_challenge
from marianos_headless.acquisition.oxylabs import (
    FULFILLMENT,
    Answer,
    OxylabsClient,
    OxylabsError,
    page_body,
    robots_body,
    search_body,
)
from marianos_headless.acquisition.robots import RobotsPolicy, parse_robots
from marianos_headless.core.ids import new_id
from marianos_headless.core.settings import AcquisitionSettings, StoreConfig
from marianos_headless.core.timeutil import iso, utcnow
from marianos_headless.sites.marianos.initial_state import InitialStateNotFound, parse_initial_state
from marianos_headless.sites.marianos.pdp_savings import savings_document
from marianos_headless.sites.marianos.sanitize import sanitize_html
from marianos_headless.sites.marianos.search_state import state_products
from marianos_headless.sites.marianos.source_json import PDP_SAVINGS
from marianos_headless.storage.base import StorageAdapter

STATE_ARTIFACT_KIND = "products_v2"
# Release 1.9.0 (M4): the purpose of a product's own page read for its coupons' complete terms, and the kind
# of the capture artifact holding that page's Savings section.
PRODUCT_TERMS = "product_terms"
SAVINGS_ARTIFACT_KIND = PDP_SAVINGS
_PDP_UPC = re.compile(r"/p/[^?#]*/(\d{13})(?:[?#]|$)")


def rendered_by_provider(result_metadata: Any) -> bool | None:
    """The provider's own statement that it ran the page's scripts (``results[0].metadata.run_js``): a page
    requested with ``run_js`` can come back without it (stage O1, 2026-11-06: 13 of 14 product pages). None
    when the answer does not say."""
    value = result_metadata.get("run_js") if isinstance(result_metadata, dict) else None
    return value if isinstance(value, bool) else None


STATE_SUFFIX = "#page-state:calypso.domains.products"


class _Count:
    def __init__(self) -> None:
        self.count = 0


def search_url(base: str, query: str) -> str:
    """The retailer's own address of the search page the provider loads for ``query``."""
    return f"{base}/search?query={quote_plus(query)}&searchType=default_search"


def answer_record(a: Answer) -> dict[str, Any]:
    """What is kept of a provider answer (no page content, no key)."""
    return {
        "provider": "oxylabs",
        "endpoint": a.endpoint,
        "request": a.body,
        "status": a.status,
        "kind": a.kind,
        "request_id": a.meta.get("request_id"),
        "attempts": a.attempts,
        "usd": round(a.cost_usd, 6),
        "cost_unknown": a.cost_unknown,
        "seconds": a.seconds,
        "result_metadata": a.meta.get("result_metadata"),
        "problem": {k: a.meta[k] for k in ("title", "detail", "errors") if k in a.meta},
    }


class OxylabsPageSession:
    def __init__(
        self,
        settings: AcquisitionSettings,
        storage: StorageAdapter,
        run_prefix: str,
        client: OxylabsClient,
        store: StoreConfig,
    ):
        self.session_id = new_id()
        self.settings = settings
        self.storage = storage
        self.prefix = run_prefix.rstrip("/")
        self.client = client
        self.store = store
        self.fulfillment = FULFILLMENT[store.modality.value]
        self.robots: RobotsPolicy | None = None
        self.robots_text: str | None = None
        self.events: list[Event] = []
        self.fetches: list[PageFetch] = []
        self.captured: list[CapturedResponse] = []
        self.pacer = _Count()
        self.meter = None  # no browser meter: spending is the ledger's submissions
        self.max_credits: float | None = None
        self.closed_at: str | None = None
        self.last_html = ""
        self.pending_fetches: set[str] = set()

    async def __aenter__(self) -> OxylabsPageSession:
        self.event(
            "INFO",
            "PROVIDER_SESSION_STARTED",
            "Oxylabs Web API (no browser)",
            {
                "provider": "oxylabs",
                "session_id": self.session_id,
                "api_base": self.settings.oxylabs.api_base,
                "store_id": self.store.location_id,
                "fulfillment_type": self.fulfillment,
            },
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.client.aclose()
        self.closed_at = iso(utcnow())
        self.event(
            "INFO",
            "PROVIDER_SESSION_CLOSED",
            "oxylabs",
            {
                "session_id": self.session_id,
                "submissions": self.client.submissions,
            },
        )

    def event(self, level: str, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        self.events.append(Event(iso(utcnow()), level, code, message, data or {}))

    def projected_step_bytes(self) -> int:
        return 0

    async def drain(self, timeout_s: float = 20) -> None:
        return None

    async def current_html(self) -> str:
        return self.last_html

    def check_allowed(self, url: str) -> None:
        if self.robots is None:
            raise RobotsDisallowed("robots.txt not loaded; refusing to request pages")
        if not self.robots.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")

    def _new_fetch(self, purpose: str, url: str) -> PageFetch:
        f = PageFetch(fetch_id=new_id(), purpose=purpose, url=url, started_at=iso(utcnow()))
        self.fetches.append(f)
        # Release 1.9.0rc4: until its answer is processed the fetch is pending, and the collector does not
        # write it to the database. With two listing lanes the other lane saves the session's fetches while
        # this request is out (stage S5b, 2026-11-09: such rows were written without their page, status or
        # duration and never completed, and G13 rejected the run).
        self.pending_fetches.add(f.fetch_id)
        return f

    async def load_robots(self, url: str) -> RobotsPolicy:
        """robots.txt through the provider (the retailer's edge drops direct connections from this
        collector's host: probe of 2026-10-28)."""
        fetch = self._new_fetch("robots", url)
        try:
            return await self._load_robots(fetch, url)
        finally:
            self.pending_fetches.discard(fetch.fetch_id)

    async def _load_robots(self, fetch: PageFetch, url: str) -> RobotsPolicy:
        self.pacer.count += 1
        body = robots_body(self.settings.oxylabs, url=url)
        answer = await self.client.fetch(
            self.settings.oxylabs.page_endpoint, body, purpose="robots", target=url
        )
        fetch.notes["provider"] = answer_record(answer)
        fetch.duration_ms = int(answer.seconds * 1000)
        if not answer.ok or answer.html is None:
            # The provider brought nothing: a provider failure, not an answer from the site.
            self.event("WARN", "ROBOTS_NOT_BROUGHT", url, {"kind": answer.kind, "status": answer.status})
            raise OxylabsError(
                answer.kind or "provider_failure",
                f"robots.txt not brought by Oxylabs ({answer.kind}, HTTP {answer.status})",
            )
        text = answer.html
        # The provider wraps a text document in a minimal HTML page when it renders one.
        if "<pre" in text[:2000].lower():
            from selectolax.lexbor import LexborHTMLParser

            pre = LexborHTMLParser(text).css_first("pre")
            text = pre.text(deep=True) if pre is not None else text
        status = (answer.meta.get("result_metadata") or {}).get("status_code") or 200
        fetch.status = int(status) if isinstance(status, int | str) and str(status).isdigit() else 200
        key = f"{self.prefix}/robots/{fetch.fetch_id}.status{fetch.status}.txt"
        self.storage.put_bytes(key, text.encode("utf-8"), "text/plain")
        fetch.dom_key = key
        if fetch.status != 200 or "user-agent" not in text.lower():
            fetch.challenge = detect_document_challenge(fetch.status, text, expect_initial_state=False)
            self.event("WARN", "ROBOTS_UNAVAILABLE", url, {"status": fetch.status})
            if fetch.challenge.is_challenge:
                raise _refusal(fetch, None)
            raise RobotsDisallowed(f"robots.txt unavailable (HTTP {fetch.status}); refusing to crawl")
        self.robots_text = text
        self.robots = parse_robots(text)
        self.event(
            "INFO",
            "ROBOTS_FETCHED",
            url,
            {
                "status": fetch.status,
                "sha256": self.robots.sha256,
                "disallow": self.robots.disallowed_patterns(),
                "via": "oxylabs",
            },
        )
        return self.robots

    async def navigate(
        self,
        url: str,
        purpose: str,
        *,
        settle_ms: int = 0,
        expect_initial_state: bool = True,
        query: str | None = None,
        run_js: bool = False,
        attempts: int | None = None,
    ) -> PageFetch:
        """One page: a search for ``query`` (``url`` is then the retailer's address of that search page),
        else the page at ``url``. Raises :class:`ChallengeDetected` on a refusal page and
        :class:`OxylabsError` when the provider brought no page."""
        self.check_allowed(url)
        fetch = self._new_fetch(purpose, url)
        try:
            return await self._navigate(
                fetch,
                url,
                purpose,
                expect_initial_state=expect_initial_state,
                query=query,
                run_js=run_js,
                attempts=attempts,
            )
        finally:
            self.pending_fetches.discard(fetch.fetch_id)

    async def _navigate(
        self,
        fetch: PageFetch,
        url: str,
        purpose: str,
        *,
        expect_initial_state: bool,
        query: str | None,
        run_js: bool,
        attempts: int | None,
    ) -> PageFetch:
        self.pacer.count += 1
        ox = self.settings.oxylabs
        if query is not None:
            endpoint = ox.search_endpoint
            body = search_body(ox, query=query, store_id=self.store.location_id, fulfillment=self.fulfillment)
        else:
            endpoint = ox.page_endpoint
            body = page_body(
                ox, url=url, store_id=self.store.location_id, fulfillment=self.fulfillment, run_js=run_js
            )
        answer = await self.client.fetch(endpoint, body, purpose=purpose, target=url, attempts=attempts)
        fetch.notes["provider"] = answer_record(answer)
        fetch.duration_ms = int(answer.seconds * 1000)
        fetch.final_url = url
        if not answer.ok or answer.html is None:
            self.event(
                "WARN",
                "PROVIDER_NO_PAGE",
                url,
                {
                    "fetch_id": fetch.fetch_id,
                    "kind": answer.kind,
                    "status": answer.status,
                    "attempts": answer.attempts,
                },
            )
            raise OxylabsError(
                answer.kind or "provider_failure",
                f"no page from Oxylabs for {url}: {answer.kind} (HTTP {answer.status})",
            )
        html = answer.html
        status = (answer.meta.get("result_metadata") or {}).get("status_code")
        fetch.status = int(status) if isinstance(status, int) else 200
        fetch.challenge = detect_document_challenge(
            fetch.status, html, expect_initial_state=expect_initial_state, state_marker=MARIANOS_STATE_MARKER
        )
        sanitized, _ = sanitize_html(html)
        dom_key = f"{self.prefix}/dom/{fetch.fetch_id}.html.gz"
        dom_gz = gzip_bytes(sanitized.encode("utf-8"))
        self.storage.put_bytes(dom_key, dom_gz, "application/gzip")
        fetch.dom_key = dom_key
        self.last_html = sanitized
        rendered = rendered_by_provider(answer.meta.get("result_metadata"))
        fetch.notes["rendered"] = rendered
        if purpose == PRODUCT_TERMS:
            # Only the page's Savings section is kept as a source (the product's data comes from the listing
            # page that showed the card); it is read from the stored page, so it can be checked again.
            self._savings(fetch, sanitized, dom_gz, rendered=rendered, requested_run_js=run_js)
        else:
            self._state_products(fetch, html)
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
                "request_id": answer.meta.get("request_id"),
                # Release 1.9.0: whether the provider ran the page's scripts, as it states it (None: unsaid).
                "run_js_requested": bool(run_js) if query is None else None,
                "rendered": rendered,
            },
        )
        if fetch.challenge.is_challenge:
            raise _refusal(fetch, None)
        return fetch

    def _savings(
        self, fetch: PageFetch, html: str, dom_gz: bytes, *, rendered: bool | None, requested_run_js: bool
    ) -> None:
        m = _PDP_UPC.search(fetch.url)
        doc = savings_document(
            html, upc=m.group(1) if m else "", rendered=rendered, requested_run_js=requested_run_js
        )
        doc["data"]["dom_key"] = fetch.dom_key
        doc["data"]["dom_gz_sha256"] = hashlib.sha256(dom_gz).hexdigest()
        body = json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")
        seq = len(self.captured) + 1
        key = f"{self.prefix}/raw/{fetch.fetch_id}.{seq:04d}.{SAVINGS_ARTIFACT_KIND}.json.gz"
        self.storage.put_bytes(key, gzip_bytes(body), "application/gzip")
        rec = CapturedResponse(
            seq=seq,
            fetch_id=fetch.fetch_id,
            kind=SAVINGS_ARTIFACT_KIND,
            url=fetch.url + "#savings",
            method="PAGE",
            status=200,
            request_location_id=None,
            request_taxonomies=[],
            request_headers={},
            response_headers={},
            body_sha256=hashlib.sha256(body).hexdigest(),
            body_bytes=len(body),
            artifact_key=key,
            observed_at=fetch.started_at,
            json_ok=True,
            extra={
                "source": "product page Savings section",
                "rows": len(doc["data"]["rows"]),
                "rendered": rendered,
            },
        )
        fetch.captured.append(rec)
        self.captured.append(rec)

    def _state_products(self, fetch: PageFetch, html: str) -> None:
        try:
            state = parse_initial_state(html)
        except (InitialStateNotFound, ValueError):
            return
        products = state_products(state)
        if not products:
            return
        body = json.dumps({"data": {"products": products}}, ensure_ascii=False).encode("utf-8")
        seq = len(self.captured) + 1
        key = f"{self.prefix}/raw/{fetch.fetch_id}.{seq:04d}.{STATE_ARTIFACT_KIND}.json.gz"
        self.storage.put_bytes(key, gzip_bytes(body), "application/gzip")
        rec = CapturedResponse(
            seq=seq,
            fetch_id=fetch.fetch_id,
            kind=STATE_ARTIFACT_KIND,
            url=fetch.url + STATE_SUFFIX,
            method="PAGE",
            status=200,
            request_location_id=None,
            request_taxonomies=[],
            request_headers={},
            response_headers={},
            body_sha256=hashlib.sha256(body).hexdigest(),
            body_bytes=len(body),
            artifact_key=key,
            observed_at=fetch.started_at,
            json_ok=True,
            extra={"source": "page state", "products": len(products)},
        )
        fetch.captured.append(rec)
        self.captured.append(rec)

    @staticmethod
    def html_of(storage: StorageAdapter, fetch: PageFetch) -> str:
        return gzip.decompress(storage.get_bytes(fetch.dom_key)).decode("utf-8") if fetch.dom_key else ""


__all__ = ["ChallengeDetected", "OxylabsError", "OxylabsPageSession", "search_url"]
