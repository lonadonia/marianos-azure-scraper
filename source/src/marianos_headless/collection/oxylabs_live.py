"""Live collection through the Oxylabs Web API (release 1.3.0).

The same run pipeline, records, checks and exports as the browser collector (:mod:`.live`); only the way
pages are obtained differs. No browser runs on the collector's side: Oxylabs' Mariano's scraper loads each
page with the store and the fulfillment given as request parameters (``store_id``, ``fulfillment_type``), and
every page is checked as in the browser collector (the page state's store, address, ZIP and active
fulfillment) plus three checks of its own: the request named the store and fulfillment, the page's search
was made for them (``search.searchAll.requestVars``), and every product's displayed prices are for the store
(``price.storePrices.sourceLocationId``).

A listing is read page by page (release 1.8.0, ``listing_route`` ``listing``): the listing's own ``/pl/`` page
with ``?page=N``, rendered, each response judged by :mod:`marianos_headless.collection.pagination` and its
products recorded through the same pipeline as page 1, in the transaction that records the page. The next page
comes from the source's own count; progress lives in the ``listing_pages`` table, so a resume continues at the
first page not completed and asks for no completed page again. A listing larger than the source's window
(``availableCount``) is read through the child listings its page's own filter tree names; a leaf above the
window stays incomplete ("accessible pages exhausted; coverage incomplete").

What the provider serves depends on the context. At store 53100502, Pickup (probes of 2026-11-02): ``/pl/``
pages and their later pages; the search route's page 2 repeats page 1 in another order; product pages are
refused (``500 REQUEST_FAILED_AFTER_TOO_MANY_RETRIES``, not charged). At store 53100503, In Store (probes of
2026-10-28), ``/pl/`` pages were refused too, and ``listing_route: search`` keeps the old reading for such a
context: the first page of the retailer's search for the listing's name, each product recorded under a planned
listing only when its own website taxonomy is that listing's ID, the listing never complete.

Spending: each submission is reserved in the ledger (``provider_usage``) against the operator's ceiling
before it is sent (:mod:`marianos_headless.acquisition.oxylabs`); the run's credit limits count
submissions.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from time import monotonic
from typing import Any, NoReturn, cast

import httpx
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from marianos_headless.acquisition import oxylabs
from marianos_headless.acquisition.browser import BrowserSession, ChallengeDetected, PageFetch
from marianos_headless.acquisition.oxylabs_session import PRODUCT_TERMS, OxylabsPageSession, search_url
from marianos_headless.assembly.offers import text_key
from marianos_headless.collection import pagination, reask
from marianos_headless.collection.limits import StopCode, credit_room, first_stop
from marianos_headless.collection.live import (
    AbnormalPage,
    ListingView,
    LiveCollector,
    NodeState,
    StepResult,
    T,
    grid_cards,
    index_captures,
)
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.pagination import Judgement, PageFacts, PageVerdict
from marianos_headless.collection.reconciliation import FINISHED_NODE
from marianos_headless.core.ids import new_id
from marianos_headless.core.settings import BrowserProvider
from marianos_headless.core.timeutil import iso
from marianos_headless.db.models import CategorySource, DeferredRequest, ListingPage, Run
from marianos_headless.sites.marianos.dom_parsers import CardObservation, parse_page
from marianos_headless.sites.marianos.initial_state import InitialStateNotFound, parse_initial_state
from marianos_headless.sites.marianos.search_state import (
    SearchSummary,
    brand_facets,
    listing_children,
    price_location,
    search_summary,
    state_products,
    taxonomy_ids,
)
from marianos_headless.worker.retry import FailureKind, TaskFailure
from marianos_headless.worker.runner import CancelledByOperator, RunStop, TaskContext, TaskDeferred, Timer
from marianos_headless.worker.runs import event
from marianos_headless.worker.store_selection import StoreCheck, StoreVerification, verify_store

# Provider failures in a row, on any listings: this many stop the run (resumable): the provider, not a page,
# is
# then failing.
MAX_FAILED_LISTINGS_IN_A_ROW = 3
# Pages at the verified store that show no product cards although their count says they should (a layout the
# parser does not read): this many in a row stop the run (not resumable): the pages are then abnormal.
MAX_ABNORMAL_LISTINGS_IN_A_ROW = 3
# Failures that leave a page unread (the listing stays unfinished); every other kind stops the run.
LISTING_FAILURES = frozenset(
    {"provider_failed_free", "provider_failure", "timeout", "transport", "empty_result", "rate_limit"}
)
SEARCH_ROUTE_REASON = (
    "accessible pages exhausted; coverage incomplete: the listing page {url} is read through the first page "
    "of the retailer's search for {query!r} ({cards} cards of {total} search results; the search route's "
    "page 2 repeats page 1), {members} of them in this listing by their own website taxonomy; the listing's "
    "own total is not known"
)


@dataclass(frozen=True)
class PageContext:
    """The response being recorded: what the page's row needs inside the products' transaction."""

    page: int
    url: str
    facts: PageFacts
    judgement: Judgement
    attempt: int
    store_check: str
    children: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Reasked:
    """A request being asked again (release 1.10.0, C1): its record, which re-ask this is, the request as
    it was set aside, and the listing's distinct products before the answer."""

    row_id: str
    ordinal: int
    asked: Mapping[str, Any]
    kind: str
    unique_before: int


# What a listing-page row's transaction also writes for C1: (session, the row's id, its attempt number) ->
# the request's record after it.
PageHook = Callable[[Session, str, int], DeferredRequest]


def query_of(node: Node) -> str:
    """The search a planned listing is read through: the site menu's title for it, else the client's
    category name (a CSV row that is itself a listing)."""
    return (node.sub_category or node.category).strip()


class OxylabsCollector(LiveCollector):
    LISTING_SETTLE_MS = 0
    STEP_SETTLE_MS = 0

    def __init__(
        self,
        pipe: Any,
        run_id: str,
        *,
        api_key: SecretStr | None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Any = asyncio.sleep,
        timer: Timer | None = None,
        **kwargs: Any,
    ):
        super().__init__(pipe, run_id, api_key=None, **kwargs)
        # Release 1.10.0 (C1): the task queue's clock and wait (the real ones unless a test supplies its own),
        # and how often a request set aside is asked again (``limits.max_reasks_per_request``; 0: never).
        self.timer = timer or Timer()
        self.reask = reask.Policy(
            self.cfg.limits.max_reasks_per_request or 0,
            self.cfg.limits.reask_min_wait_seconds or reask.MIN_WAIT_S,
        )
        self._reasked: Reasked | None = None
        acq = pipe.settings.acquisition.model_copy(update={"browser_provider": BrowserProvider.OXYLABS})
        self.settings = pipe.settings.model_copy(update={"acquisition": acq})
        self.ox_key = api_key
        self.ledger = oxylabs.Ledger(self.factory, acq.oxylabs)
        self.transport = transport
        self.sleep = sleep
        self.ox: OxylabsPageSession | None = None
        self._session_lock = asyncio.Lock()
        self.failed_in_a_row = 0
        self.abnormal_in_a_row = 0
        # The page being recorded: each product's website taxonomy IDs, price location and placement.
        self._tax: dict[str, list[str]] = {}
        self._price_loc: dict[str, str | None] = {}
        self._sponsored: set[str] = set()
        self._ranks: dict[str, int] = {}
        self._children: list[dict[str, Any]] = []
        self._brands: list[dict[str, Any]] = []
        self._summary: SearchSummary | None = None
        self._query = ""
        self._reading: PageContext | None = None
        self.route = acq.oxylabs.listing_route
        # Release 1.9.0 (M4): product pages read for coupon terms in this execution, and why reading
        # stopped.
        self.term_reads = 0
        self.term_ceiling: str | None = None
        self._by_tax: dict[str, list[Node]] = {}
        for n in self.plan:
            self._by_tax.setdefault(n.taxonomy_id, []).append(n)

    # -- account and limits -----------------------------------------------------------------------------

    async def open_account(self) -> tuple[str, str] | None:
        """No balance API exists for the Oxylabs Web API: the operator's ceiling in the ledger is the
        account the collector may spend (``set-ceiling``)."""
        if self.ox_key is None:
            return (
                StopCode.NO_API_KEY,
                f"no Oxylabs Web API key: set {oxylabs.ENV_KEY} or {oxylabs.ENV_KEY_FILE}",
            )
        with self.factory() as s:
            left, info = oxylabs.room(s)
        if left is None:
            return (
                StopCode.SPENDING_CEILING,
                "no Oxylabs spending ceiling is set: run 'marianos-collector set-ceiling --provider "
                "oxylabs' first",
            )
        if left <= 0:
            cap = info["ceiling"]
            return (
                StopCode.SPENDING_CEILING,
                f"the Oxylabs ceiling of {cap['submissions']} submissions (USD {cap['usd']}) is used up",
            )
        self.account_start = left
        return None

    async def account_remaining_now(self) -> int | None:
        with self.factory() as s:
            left, _ = oxylabs.room(s)
        return left

    def segment_credits(self) -> float:
        return self.closed_credits + (self.ox.client.submissions if self.ox is not None else 0)

    def step_credits(self) -> float:
        return 1.0

    def limit_stop(self, *, opening: bool = False) -> tuple[str, str] | None:
        """The run's limits, with one submission as the unit (the ledger refuses anything past the
        operator's ceiling on its own)."""
        if self.window_end is not None and self.clock() >= self.window_end:
            return StopCode.SCHEDULE_WINDOW_END, f"the daily window ended at {self.window_end.isoformat()}"
        usage = self.usage()
        stop = first_stop(
            self.cfg.limits, usage, account_remaining=self.account_remaining(), min_step_credits=0
        )
        if stop is not None and stop[0] == StopCode.CREDITS_EXHAUSTED:
            # The "account" here is the operator's ceiling (no balance API): say so.
            return (
                StopCode.SPENDING_CEILING,
                f"the Oxylabs ceiling leaves no submission ({self.account_start} left when the segment "
                f"started, {self.segment_credits():.0f} sent since)",
            )
        if stop is not None:
            return stop
        _, self.binding = credit_room(self.cfg.limits, usage, self.account_remaining())
        return None

    def selection_text(self) -> str:
        return "requested from Oxylabs with its store_id and fulfillment_type and verified on the page"

    # -- the provider session ---------------------------------------------------------------------------

    async def open_session(self, ctx: TaskContext) -> None:
        stop = self.limit_stop(opening=True)
        if stop is not None:
            raise RunStop(stop[0], stop[1], resumable=True)
        assert self.ox_key is not None
        client = oxylabs.OxylabsClient(
            self.settings.acquisition.oxylabs,
            self.ox_key,
            self.ledger,
            run_id=self.run_id,
            segment_id=self.segment_id,
            transport=self.transport,
            sleep=self.sleep,
        )
        ox = OxylabsPageSession(self.settings.acquisition, self.storage, self.prefix, client, self.store)
        await ox.__aenter__()
        self.ox, self.session = ox, cast(BrowserSession, ox)
        self.session_opened = monotonic()
        self.sessions_opened += 1
        policy = await ox.load_robots(f"{self.base}/robots.txt")
        with self.factory() as s:
            run = s.get(Run, self.run_id)
            assert run is not None
            run.robots_sha256 = policy.sha256
            self.persist(s, ctx)
            event(
                s,
                self.run_id,
                "INFO",
                "PROVIDER_SESSION_OPENED",
                "Oxylabs Web API: robots.txt read through the provider",
                {"session": self.sessions_opened, "robots_sha256": policy.sha256, "provider": "oxylabs"},
            )
            s.commit()

    async def close_session(self) -> None:
        ox, self.ox = self.ox, None
        self.session = None
        if ox is None:
            return
        try:
            await ox.__aexit__(None, None, None)
        finally:
            self.closed_credits += ox.client.submissions
            self.sessions_closed += 1
            self.ready = None
            with self.factory() as s:
                for ev in ox.events:
                    event(
                        s,
                        self.run_id,
                        ev.level,
                        f"SESSION_{ev.code}"[:48],
                        ev.message[:500],
                        {**ev.data, "at": ev.ts},
                    )
                event(
                    s,
                    self.run_id,
                    "INFO",
                    "PROVIDER_SESSION_CLOSED",
                    "Oxylabs Web API session closed",
                    {"submissions": ox.client.submissions, "pages": ox.pacer.count},
                )
                s.commit()

    def query_url(self, node: Node, page: int = 1) -> str:
        if self.route == "search":
            return search_url(self.base, query_of(node))
        return pagination.page_url(node.url, page)

    async def ensure_session(self, ctx: TaskContext, node: Node) -> bool:
        if self.ox is None or self.ox.robots is None:
            # 1.9.0 (M8): lanes never open two sessions, and a lane waits until the session another lane is
            # opening has read robots.txt (the session object exists before that: a race seen in the lanes
            # test, where the waiting lane met a session without its robots policy).
            async with self._session_lock:
                if self.ox is None:
                    await self.open_session(ctx)
        assert self.ox is not None and self.ox.robots is not None
        return self.ox.robots.allowed(self.query_url(node))

    async def _page(
        self, ctx: TaskContext, node: Node, purpose: str, page: int = 1, *, attempts: int | None = None
    ) -> PageFetch:
        assert self.ox is not None
        self.check(ctx)
        if self.route == "search":
            fetch = await self.ox.navigate(self.query_url(node), purpose, query=query_of(node))
        else:
            fetch = await self.ox.navigate(
                self.query_url(node, page),
                purpose,
                run_js=self.settings.acquisition.oxylabs.listing_run_js,
                attempts=attempts,
            )
        self.steps += 1
        return fetch

    async def select_store(self, ctx: TaskContext, node: Node) -> None:
        """The first page: the store is a request parameter; the page must show it (no picker)."""
        fetch = await self._page(ctx, node, "listing")
        v = self.verify(fetch)
        with self.factory() as s:
            self.persist(s, ctx)
            if not self._attested(s) or not v.passed:
                self.attest(s, v, "preflight" if not self._attested(s) else "task_start")
            s.commit()
        if not v.passed:
            raise RunStop(
                StopCode.STORE_NOT_VERIFIED,
                "the page Oxylabs served is not priced for the store and fulfillment: "
                + ("; ".join(v.failures()) or "store context incomplete"),
                resumable=False,
            )
        self.ready = (node.url, fetch, v)

    def verify(self, fetch: PageFetch) -> StoreVerification:
        html = self.html(fetch)
        v = verify_store(
            self.store,
            self.settings,
            html,
            fetch_id=fetch.fetch_id,
            purpose=fetch.purpose,
            url=fetch.final_url or fetch.url,
        )
        loc, modality = self.store.location_id, self.store.modality.value
        req = (fetch.notes.get("provider") or {}).get("request") or {}
        v.checks.append(
            StoreCheck(
                "provider_request",
                req.get("store_id") == loc and req.get("fulfillment_type") == oxylabs.FULFILLMENT[modality],
                {"store_id": req.get("store_id"), "fulfillment_type": req.get("fulfillment_type")},
                {"store_id": loc, "fulfillment_type": oxylabs.FULFILLMENT[modality]},
                note="the store and fulfillment the page was requested for (Oxylabs Web API parameters)",
            )
        )
        try:
            state = parse_initial_state(html)
        except (InitialStateNotFound, ValueError):
            state = {}
        summary = search_summary(state)
        if summary is not None:
            v.checks.append(
                StoreCheck(
                    "search_request",
                    summary.location_id == loc and summary.modality == modality,
                    {"locationId": summary.location_id, "activeModalityType": summary.modality},
                    {"locationId": loc, "activeModalityType": modality},
                    note="the page's own search request (search.searchAll.requestVars)",
                )
            )
        products = state_products(state)
        locs = Counter(price_location(p) for p in products)
        stated = set(locs) - {None}
        # Every price a page states must be the store's. A product whose data states no price (``price``
        # empty, the card showing "Prices May Vary": temporarily out of stock at the store; live
        # 2026-10-29, the search for "Fresh Herbs") has no price to check, as in the record checks: it is
        # exported with empty prices, never valid. A page that shows no product (a search that found
        # nothing, the Coupons page) has none either; its store and fulfillment are still checked above,
        # and the listing step tells an empty search from an abnormal page. A page that shows cards
        # without their product data cannot be checked: it fails.
        shows = fetch.purpose != "coupons" and bool(products or grid_cards(html)[1])
        ok = (stated == {loc}) if stated else (False if shows and not products else None)
        v.checks.append(
            StoreCheck(
                "price_locations",
                ok,
                {k or "no price stated": n for k, n in locs.items()},
                loc,
                required=ok is not None,
                note="the store each price a page states is for (price.storePrices.sourceLocationId);"
                " not applicable to a product that states no price or a page that shows no product (the"
                " Coupons page, a search that found nothing)",
            )
        )
        return v

    async def _guard(self, ctx: TaskContext, work: Awaitable[T]) -> T:
        try:
            return await super()._guard(ctx, work)
        except oxylabs.CeilingReached as exc:
            self._persist_now(ctx)
            raise RunStop(StopCode.SPENDING_CEILING, str(exc), resumable=True) from None
        except oxylabs.OxylabsError as exc:
            self._persist_now(ctx)
            text = oxylabs.redact(str(exc), self.ox_key)[:500]
            if exc.kind == "auth":
                raise RunStop(StopCode.PROVIDER_AUTH, text, resumable=True) from None
            if exc.kind == "entitlement":
                raise RunStop(StopCode.ACCOUNT_UNAVAILABLE, text, resumable=True) from None
            if exc.kind == "quota":
                raise RunStop(StopCode.CREDITS_EXHAUSTED, text, resumable=True) from None
            if exc.kind == "bad_request":
                raise RunStop(StopCode.ABNORMAL_RESULT, text, resumable=False) from None
            raise RunStop(StopCode.PROVIDER_ERROR, text, resumable=True) from None

    # -- the Coupons route ----------------------------------------------------------------------------------

    async def h_preflight(self, ctx: TaskContext) -> dict[str, Any]:
        out = await super().h_preflight(ctx)
        with self.factory() as s:
            run = s.get(Run, self.run_id)
            done = run is not None and (run.counts or {}).get("coupons_route") is not None
        if not done:
            async with self.keepalive(ctx):
                await self._with_reconnects(ctx, lambda: self.coupons_route(ctx))
        return out

    async def coupons_route(self, ctx: TaskContext) -> None:
        """The client's Coupons row (offer discovery): its page read once per run, rendered (its coupon cards
        appear only then), for the same store and fulfillment. The cards name each coupon's wording, terms
        and expiry; the page does not list the products a coupon applies to, so coupons reach records only
        through the coupon a product's own card shows."""
        with self.factory() as s:
            url = s.scalar(
                select(CategorySource.url).where(
                    CategorySource.csv_row_index == 0, CategorySource.category_name == "Coupons"
                )
            )
        if not url:
            return
        assert self.ox is not None
        summary: dict[str, Any] = {"url": url, "provider": "oxylabs", "run_js": True}
        if not self.ox.robots or not self.ox.robots.allowed(url):
            summary["status"] = "SKIPPED: robots.txt does not allow the page"
        else:
            self.check(ctx)
            try:
                fetch = await self.ox.navigate(
                    url, "coupons", run_js=self.settings.acquisition.oxylabs.coupons_run_js
                )
            except oxylabs.OxylabsError as exc:
                if exc.kind not in LISTING_FAILURES:
                    raise
                summary["status"] = f"NOT READ: the provider brought no page ({exc.kind})"
            else:
                self.steps += 1
                v = self.verify(fetch)
                coupons = parse_page(self.html(fetch)).coupons
                summary.update(
                    {
                        "status": "READ" if v.passed else "STORE_NOT_VERIFIED",
                        "fetch_id": fetch.fetch_id,
                        "store_check": "PASS" if v.passed else "; ".join(v.failures())[:500],
                        "coupon_cards": len(coupons),
                        "coupons": [
                            {
                                "coupon_id": c.coupon_id,
                                "brand": c.brand,
                                "title": c.title,
                                "description": c.description,
                                "expiry_text": c.expiry_text,
                                "savings_tag": c.savings_tag,
                                "other_tags": list(c.other_tags),
                            }
                            for c in coupons
                        ],
                        "products_listed": False,
                    }
                )
        with self.factory() as s:
            self.persist(s, ctx)
            run = s.get(Run, self.run_id)
            assert run is not None
            run.counts = {**(run.counts or {}), "coupons_route": summary}
            event(
                s,
                self.run_id,
                "INFO" if summary.get("status") == "READ" else "WARN",
                "COUPONS_ROUTE",
                f"Coupons page: {summary.get('status')}; {summary.get('coupon_cards', 0)} coupon cards",
                {k: v for k, v in summary.items() if k != "coupons"},
            )
            s.commit()

    # -- complete coupon terms (release 1.9.0, M4) ---------------------------------------------------------

    @staticmethod
    def shows_coupon(card: CardObservation) -> bool:
        """The card's savings zone shows a digital coupon: a clip checkbox, or a "Coupon" / "Cash Back"
        label."""
        z = card.zone
        if z is None or not z.text:
            return False
        return z.requires_clip or z.label.strip().casefold() in {"coupon", "cash back", "digital coupon"}

    def _terms(self, upc: str, status: str, reason: str, **extra: Any) -> None:
        self.term_status[upc] = {"status": status, "reason": reason, **extra}

    async def read_terms(self, ctx: TaskContext, view: ListingView) -> None:
        """The product's own page, rendered, for each card of a verified page step that shows a digital coupon
        (once per product and run), before the step's records are built: its Savings section names each
        coupon's ID, headline, complete terms, displayed expiry, clipping instruction and qualifying products
        (``sites.marianos.pdp_savings``). Each outcome is kept with the product's record:

        ``read``: the page was rendered and shows the card's coupon (its terms join the record);
        a tile (release 1.9.0rc3) is read whether or not it shows a coupon, since tiles omit coupons that
        the product's own page shows: ``read`` (the page shows coupons; they join the record) or
        ``none_on_page`` (rendered, no coupon);
        ``conflict``: the page was rendered but shows no coupon, or other coupons than the card (both kept);
        ``unread_not_rendered``: the provider brought the page without running its scripts (its own answer
        says so), and the coupons load only then: nothing is learnt about them;
        ``request_failed`` (sent once, never retried), ``store_unverified``, ``unread_limit`` (the run's
        ``max_product_term_reads``), ``unread_ceiling`` (the spending ceiling or another run limit was reached
        first), ``unread_robots``.
        A refusal (challenge) page stops the run as on any page. Off unless
        ``coverage.read_product_terms``."""
        if not self.settings.coverage.read_product_terms:
            return
        assert self.ox is not None
        limit = self.cfg.limits.max_product_term_reads
        for card in view.cards:
            upc = card.upc
            tile_unshown = card.layout == "tile" and not self.shows_coupon(card)
            if not upc or not card.url or not (tile_unshown or self.shows_coupon(card)):
                continue
            if upc in self.term_status or upc in self.recorded:
                continue
            if limit is not None and self.term_reads >= limit:
                self._terms(
                    upc, "unread_limit", f"the run's limit of {limit} product page read(s) was reached"
                )
                continue
            if self.term_ceiling is not None:
                self._terms(upc, "unread_ceiling", self.term_ceiling)
                continue
            if self.ox.robots is None or not self.ox.robots.allowed(card.url):
                self._terms(upc, "unread_robots", "robots.txt does not allow the product page")
                continue
            # The operator's Pause/Stop stops at once. A limit (the spending ceiling, the run's own limits,
            # the window) leaves this read unmade but keeps the page step already paid for: its records are
            # built and the next listing page meets the same limit and stops the run as usual.
            if ctx.cancelled():
                raise CancelledByOperator()
            stop = self.limit_stop()
            if stop is not None:
                self.term_ceiling = f"{stop[0]}: {stop[1]}"
                self._terms(upc, "unread_ceiling", self.term_ceiling)
                continue
            ctx.heartbeat()
            self._terms(upc, "pending", "being read")
            self.term_reads += 1
            try:
                # Sent once: a failed read is recorded, never retried automatically (no repeated requests
                # for one product's terms).
                fetch = await self.ox.navigate(
                    card.url,
                    PRODUCT_TERMS,
                    run_js=self.settings.acquisition.oxylabs.product_terms_run_js,
                    attempts=1,
                )
            except oxylabs.CeilingReached as exc:
                # Nothing was sent. The records of this page step are still built (the page is paid for);
                # the next listing page meets the same ceiling and stops the run as usual.
                self.term_ceiling = (
                    "the spending ceiling was reached: " + oxylabs.redact(str(exc), self.ox_key)[:300]
                )
                self._terms(upc, "unread_ceiling", self.term_ceiling)
                continue
            except ChallengeDetected as exc:
                self._terms(
                    upc,
                    "blocked",
                    "the product page was a refusal page",
                    fetch_id=exc.fetch.fetch_id if exc.fetch is not None else None,
                )
                self._persist_now(ctx)
                raise
            except oxylabs.OxylabsError as exc:
                if exc.kind not in LISTING_FAILURES:
                    raise
                self._terms(
                    upc,
                    "request_failed",
                    f"the provider brought no page ({exc.kind}): "
                    + oxylabs.redact(str(exc), self.ox_key)[:300],
                )
                continue
            self.steps += 1
            # This page's sources are indexed here, once, and only when its store check passes.
            self.indexed.add(fetch.fetch_id)
            v = self.verify(fetch)
            provider = fetch.notes.get("provider") or {}
            base = {"fetch_id": fetch.fetch_id, "url": card.url, "request_id": provider.get("request_id")}
            rendered = fetch.notes.get("rendered")
            if not v.passed:
                self._terms(
                    upc,
                    "store_unverified",
                    "the product page is not for the configured store and fulfillment: "
                    + ("; ".join(v.failures()) or "store context incomplete")[:400],
                    rendered=rendered,
                    **base,
                )
                continue
            index_captures(self.sources, fetch, self._read)
            read = self.sources.terms_read(upc)
            if rendered is not True or read is None:
                self._terms(
                    upc,
                    "unread_not_rendered",
                    "the provider brought the page without running its scripts (its answer states run_js "
                    f"{rendered!r}); the page's coupons load only then, so nothing is learnt about them",
                    rendered=rendered,
                    **base,
                )
                continue
            if tile_unshown:
                found = [self.sources.coupons[i] for i in read.coupon_ids if i in self.sources.coupons]
                self._terms(
                    upc,
                    "read" if found else "none_on_page",
                    "the rendered product page shows " + "; ".join(repr(c.text) for c in found)
                    if found
                    else "the rendered product page shows no coupon",
                    rendered=True,
                    coupon_ids=list(read.coupon_ids),
                    **base,
                )
                continue
            shown = card.zone.text if card.zone is not None else ""
            on_page = [self.sources.coupons[i] for i in read.coupon_ids if i in self.sources.coupons]
            if any(text_key(c.text) == text_key(shown) for c in on_page):
                self._terms(
                    upc,
                    "read",
                    "the rendered product page shows the card's coupon with its terms",
                    rendered=True,
                    coupon_ids=list(read.coupon_ids),
                    **base,
                )
            elif on_page:
                self._terms(
                    upc,
                    "conflict",
                    "the rendered product page shows other coupons than the card ("
                    + "; ".join(repr(c.text) for c in on_page)
                    + f") while the card shows {shown!r}",
                    rendered=True,
                    coupon_ids=list(read.coupon_ids),
                    **base,
                )
            else:
                self._terms(
                    upc,
                    "conflict",
                    f"the rendered product page shows no coupon while the card shows {shown!r}",
                    rendered=True,
                    coupon_ids=[],
                    **base,
                )

    # -- a listing ----------------------------------------------------------------------------------------

    def _view(self, fetch: PageFetch) -> ListingView:
        html = self.html(fetch)
        grid, cards, _, displayed = grid_cards(html)
        try:
            state = parse_initial_state(html)
        except (InitialStateNotFound, ValueError):
            state = {}
        summary = search_summary(state)
        subs = summary.sub_commodities if summary is not None else {}
        self._tax = {
            str(p.get("upc") or p.get("id")): taxonomy_ids(p, subs.get(str(p.get("upc") or p.get("id")), ()))
            for p in state_products(state)
        }
        self._price_loc = {str(p.get("upc") or p.get("id")): price_location(p) for p in state_products(state)}
        self._sponsored = set(summary.sponsored) if summary is not None else set()
        self._ranks = dict(summary.ranks) if summary is not None else {}
        self._query = summary.query or "" if summary is not None else ""
        self._summary = summary
        self._children = (
            listing_children(state, summary.taxonomy_id)
            if summary is not None and summary.taxonomy_id
            else []
        )
        self._brands = brand_facets(state)
        searches: list[dict[str, Any]] = (
            [
                {
                    "offset": ((summary.page or 1) - 1) * pagination.PAGE_SIZE,
                    "size": len(summary.upcs),
                    "location_id": summary.location_id,
                    "status": 200,
                    "total": summary.total,
                    "available": summary.available,
                    "children": self._children,
                }
            ]
            if summary is not None
            else []
        )
        # Sponsored placements are not left out here: a product is recorded once (first placement wins)
        # when its own taxonomy puts it in a planned listing and its prices are the store's.
        return ListingView(grid, cards, set(), displayed, searches)

    def assign(self, card: CardObservation, node: Node) -> Node | None:
        upc = card.upc or ""
        ids = self._tax.get(upc, [])
        if node.taxonomy_id in ids:
            return node
        if self.route == "listing" and self._ranks.get(upc):
            return node  # a result of the listing itself: the site puts it there
        for tax in ids:  # most specific first
            if tax in self._by_tax:
                return self._by_tax[tax][0]
        return None

    def sponsored_placement(self, card: CardObservation) -> bool:
        """A placement with rank 0, or a product the page's ``sponsoredItems`` names: a sponsored product can
        keep a rank of its own (ranks 6 and 9 on the search capture of 2026-10-28), and it is then a result
        of the
        listing as well. Whether it is a result is decided by its rank (:meth:`assign`), never by this."""
        upc = card.upc or ""
        return self._ranks.get(upc) == 0 or upc in self._sponsored

    def membership(self, card: CardObservation, node: Node, target: Node) -> dict[str, Any]:
        upc = card.upc or ""
        rank = self._ranks.get(upc)
        listed = self.route == "listing" and bool(rank) and target.taxonomy_id == node.taxonomy_id
        return {
            "membership": {
                "rule": "a result of the listing's own page"
                if listed
                else "the product's own website taxonomy is the listing's ID",
                "taxonomy_ids": self._tax.get(upc, []),
                "listing": target.taxonomy_id,
                "read_through": {
                    "provider": "oxylabs",
                    "route": self.route,
                    "listing_url": node.url,
                    **({"search": self._query} if self.route == "search" else {}),
                    **({"page": self._reading.page} if self._reading is not None else {}),
                },
                "rank": rank,
                "placement": "sponsored" if self.sponsored_placement(card) else "organic",
                "price_location": self._price_loc.get(upc),
            }
        }

    async def h_listing(self, ctx: TaskContext) -> dict[str, Any]:
        node = Node.from_dict(ctx.cursor["node"])
        state = NodeState.from_cursor(ctx.cursor)
        if self.ready is not None and self.ready[0] == node.url and state.status not in FINISHED_NODE:
            # The page brought for the store check: recorded without another submission, so the spending
            # limits do not apply to it (the operator's stop still does).
            if ctx.cancelled():
                raise CancelledByOperator()
            async with self.keepalive(ctx):
                return await self._with_reconnects(ctx, lambda: self.collect_node(ctx, node, state))
        return await super().h_listing(ctx)

    async def collect_node(self, ctx: TaskContext, node: Node, state: NodeState) -> dict[str, Any]:
        if not await self.ensure_session(ctx, node):
            state.status, state.reason = "SKIPPED", "robots.txt does not allow this listing's page"
            return self._finish_node(node, state)
        if self.route == "search":
            return await self.read_search(ctx, node, state)
        return await self.read_listing(ctx, node, state)

    # -- the page loop --------------------------------------------------------------------------------------

    @staticmethod
    def _pkey(node: Node) -> str:
        """The page rows' partition key: a filtered reading's full identity digest ("" for a listing)."""
        desc = pagination.node_filter(node.partition_filter)
        return pagination.partition_digest(desc) if desc else ""

    def _restore(self, node: Node, state: NodeState) -> list[ListingPage]:
        """The listing's durable progress: the task's cursor may be one page behind the table (a worker killed
        between the page's commit and its checkpoint), never ahead."""
        with self.factory() as s:
            done = pagination.completed_pages(
                pagination.rows_of(
                    s, self.run_id, node.category_source_id, node.taxonomy_id, self._pkey(node)
                )
            )
            s.expunge_all()
        state.steps_done = len(done)
        if done:
            seen = dict.fromkeys(state.seen)
            for r in done:
                seen.update(dict.fromkeys(r.identities or []))
            state.seen = list(seen)
            state.total = done[-1].total
            state.available = done[-1].available
            state.last_offset = (done[-1].requested_page - 1) * pagination.PAGE_SIZE
        return done

    def _page_row(
        self,
        s: Session,
        node: Node,
        fetch: PageFetch | None,
        *,
        page: int,
        url: str,
        facts: PageFacts | None,
        verdict: PageVerdict,
        detail: str,
        state_name: str,
        attempt: int,
        store_check: str,
        res: StepResult | None = None,
        duplicates: int = 0,
        children: Sequence[Mapping[str, Any]] = (),
        binding: Mapping[str, Any] | None = None,
    ) -> str:
        provider = (fetch.notes.get("provider") or {}) if fetch is not None else {}
        observed = (
            datetime.fromisoformat(fetch.started_at.replace("Z", "+00:00"))
            if fetch is not None
            else self.clock()
        )
        row_id = new_id()
        s.add(
            ListingPage(
                id=row_id,
                run_id=self.run_id,
                category_source_id=node.category_source_id,
                csv_row_index=node.row_index,
                taxonomy_id=node.taxonomy_id,
                parent_taxonomy_id=node.parent,
                partition_key=self._pkey(node),
                requested_filter=pagination.node_filter(node.partition_filter) or {},
                binding=dict(binding or {}),
                url=url[:4000],
                route=self.route,
                requested_page=page,
                requested_offset=(page - 1) * pagination.PAGE_SIZE,
                returned_page=facts.returned_page if facts is not None else None,
                loaded_pages=list(facts.loaded_pages) if facts is not None else [],
                provider_request_id=provider.get("request_id"),
                page_fetch_id=fetch.fetch_id
                if fetch is not None and fetch.fetch_id in self.persisted
                else None,
                response_sha256=sha256(self._read(fetch.dom_key)).hexdigest()
                if fetch is not None and fetch.dom_key
                else None,
                location_id=facts.location_id if facts is not None else None,
                modality=facts.modality if facts is not None else None,
                returned_taxonomy_id=facts.taxonomy_id if facts is not None else None,
                store_check=store_check,
                total=facts.total if facts is not None else None,
                available=facts.available if facts is not None else None,
                identities=list(facts.organic) if facts is not None else [],
                sponsored=list(facts.sponsored) if facts is not None else [],
                children=list(children),
                new_count=res.new_cards if res is not None else 0,
                duplicates=res.duplicates if res is not None else duplicates,
                excluded=res.excluded if res is not None else 0,
                conflicts=res.conflicts if res is not None else 0,
                state=state_name,
                verdict=verdict.value,
                detail=detail[:2000],
                segment_id=self.segment_id,
                attempt=attempt,
                observed_at=observed,
            )
        )
        return row_id

    def page_recorded(self, s: Session, node: Node, fetch: PageFetch, res: StepResult) -> None:
        """The page's row, in the transaction of its products. A page the product limit cut short is not
        completed: its remaining cards wait for a resume, which reads it again.

        Release 1.10.0 (C1): when the page is a request asked again, its record is closed in this same
        transaction (``recovered`` with the page completed; a page the product limit cut short is not
        completed, so the request stays unanswered and its re-ask stays counted)."""
        r = self._reading
        if r is None:
            return
        row_id = self._page_row(
            s,
            node,
            fetch,
            page=r.page,
            url=r.url,
            facts=r.facts,
            verdict=r.judgement.verdict,
            detail=r.judgement.detail,
            state_name="capped" if res.capped is not None else "completed",
            attempt=r.attempt,
            store_check=r.store_check,
            res=res,
            children=r.children,
            binding=r.judgement.binding,
        )
        again = self._reasked
        if again is not None:
            done = res.capped is None
            new = len(r.judgement.new)
            hook = self._settles(
                again,
                node,
                fetch,
                facts=r.facts,
                judgement=r.judgement,
                verdict=r.judgement.verdict.value,
                detail=r.judgement.detail or f"{new} products new to the listing",
                store_check=r.store_check,
                new=new,
                counted=done,
                recovered=done,
                outcome=f"counted: {new} products new to the listing; the listing goes on from page "
                f"{r.page + 1}"
                if done
                else "answered properly, but the run's product limit cut the page short: not completed",
            )
            hook(s, row_id, r.attempt)

    def _page_refused(
        self,
        ctx: TaskContext,
        node: Node,
        fetch: PageFetch | None,
        *,
        page: int,
        url: str,
        facts: PageFacts | None,
        verdict: PageVerdict,
        detail: str,
        state_name: str,
        store_check: str = "N/A",
        duplicates: int = 0,
        binding: Mapping[str, Any] | None = None,
        children: Sequence[Mapping[str, Any]] = (),
        hook: PageHook | None = None,
        code: str = "PAGE_NOT_COUNTED",
    ) -> DeferredRequest | None:
        """A response that does not count: its row, its event, nothing else. Release 1.10.0 (C1): ``hook``
        writes the request's record (set aside, or a re-ask's answer) in the row's own transaction, so
        neither exists without the other; the record is returned as it stands after it."""
        held: DeferredRequest | None = None
        with self.factory() as s:
            self.persist(s, ctx)
            s.flush()
            attempt = pagination.next_attempt(
                s, self.run_id, node.category_source_id, node.taxonomy_id, page, self._pkey(node)
            )
            row_id = self._page_row(
                s,
                node,
                fetch,
                page=page,
                url=url,
                facts=facts,
                verdict=verdict,
                detail=detail,
                state_name=state_name,
                attempt=attempt,
                store_check=store_check,
                duplicates=duplicates,
                binding=binding,
                children=children,
            )
            if hook is not None:
                held = hook(s, row_id, attempt)
            event(
                s,
                self.run_id,
                "WARN" if code == "PAGE_NOT_COUNTED" else "INFO",
                code,
                f"{node.category} › {node.sub_category}: page {page} {verdict.value}: {detail}"[:500],
                {
                    "node": node.taxonomy_id,
                    "page": page,
                    "verdict": verdict.value,
                    "attempt": attempt,
                    "rendered": fetch.notes.get("rendered") if fetch is not None else None,
                    **(
                        {
                            "deferred_request": held.id,
                            "request_state": held.state,
                            "reasks_sent": held.reasks_dispatched,
                            "not_before": iso(held.not_before),
                        }
                        if held is not None
                        else {}
                    ),
                },
            )
            s.commit()
        return held

    def _unread(self, ctx: TaskContext, node: Node, page: int, why: str) -> NoReturn:
        """The page stays unread and the listing unfinished. The task waits and comes back (the run's bounded
        retries); once they are spent, or when pages keep failing on any listing, the run stops resumably, and
        the resume starts at this page."""
        self.failed_in_a_row += 1
        text = f"{node.url}: page {page} not read: {why}"[:600]
        if self.failed_in_a_row >= MAX_FAILED_LISTINGS_IN_A_ROW:
            raise RunStop(
                StopCode.PROVIDER_ERROR,
                f"{self.failed_in_a_row} pages in a row not read; last: {text}",
                resumable=True,
            )
        if ctx.lease.attempts >= self.settings.retries.max_attempts_per_task:
            raise RunStop(StopCode.PROVIDER_ERROR, text, resumable=True)
        raise TaskFailure(FailureKind.TRANSIENT, text)

    # -- requests set aside and asked again (release 1.10.0, C1; collection.reask) -------------------------

    def _key(self, node: Node, page: int) -> reask.Key:
        return reask.Key(self.run_id, node.category_source_id, node.taxonomy_id, self._pkey(node), page)

    def _entry(
        self,
        ordinal: int,
        asked: Mapping[str, Any],
        fetch: PageFetch | None,
        *,
        facts: PageFacts | None,
        judgement: Judgement | None,
        verdict: str,
        detail: str,
        store_check: str,
        unique_before: int,
        new: int,
        counted: bool,
        listing_page_id: str | None,
        attempt: int | None,
        subdivisions: Sequence[Mapping[str, Any]] | None = None,
        overlap: int | None = None,
        outcome: str = "",
    ) -> dict[str, Any]:
        """One answer of a request set aside, as its record keeps it."""
        provider = (fetch.notes.get("provider") or {}) if fetch is not None else {}
        return {
            **reask.answer_entry(
                ordinal=ordinal,
                asked=asked,
                facts=facts,
                judgement=judgement,
                verdict=verdict,
                detail=detail,
                store_check=store_check,
                unique_before=unique_before,
                new=new,
                counted=counted,
                observed_at=datetime.fromisoformat(fetch.started_at.replace("Z", "+00:00"))
                if fetch is not None
                else None,
                response_sha256=sha256(self._read(fetch.dom_key)).hexdigest()
                if fetch is not None and fetch.dom_key
                else None,
                page_fetch_id=fetch.fetch_id
                if fetch is not None and fetch.fetch_id in self.persisted
                else None,
                listing_page_id=listing_page_id or None,
                listing_page_attempt=attempt or None,
                provider_request_id=provider.get("request_id"),
                subdivisions=subdivisions,
                overlap=overlap,
                outcome=outcome,
            ),
            "recorded_at": iso(self.timer.now()),
            "rendered_by_provider": fetch.notes.get("rendered")
            if fetch is not None
            else reask.unavailable("no page was brought"),
        }

    def _sets_aside(
        self,
        node: Node,
        page: int,
        url: str,
        fetch: PageFetch,
        *,
        facts: PageFacts,
        judgement: Judgement,
        store_check: str,
        unique_before: int,
        reason: str,
    ) -> PageHook:
        """A later page answered with products of earlier pages: its request's record, created with the
        answer's own row."""
        asked = reask.requested(node, page, url, self.store)

        def hook(s: Session, listing_page_id: str, attempt: int) -> DeferredRequest:
            first = self._entry(
                0,
                asked,
                fetch,
                facts=facts,
                judgement=judgement,
                verdict=judgement.verdict.value,
                detail=judgement.detail,
                store_check=store_check,
                unique_before=unique_before,
                new=0,
                counted=False,
                listing_page_id=listing_page_id,
                attempt=attempt,
            )
            row = reask.set_aside(
                s,
                key=self._key(node, page),
                node=node,
                url=url,
                kind=reask.REPEATED_PAGE,
                store=self.store,
                policy=self.reask,
                now=self.timer.now(),
                original_verdict=judgement.verdict.value,
                original_reason=reason,
                original_listing_page_id=listing_page_id,
                first=first,
            )
            self._request_event(s, node, row, "REQUEST_SET_ASIDE")
            return row

        return hook

    def _settles(
        self,
        again: Reasked,
        node: Node,
        fetch: PageFetch | None,
        *,
        facts: PageFacts | None,
        judgement: Judgement | None,
        verdict: str,
        detail: str,
        store_check: str,
        new: int,
        counted: bool,
        recovered: bool,
        outcome: str = "",
        subdivisions: Sequence[Mapping[str, Any]] | None = None,
        overlap: int | None = None,
    ) -> PageHook:
        """A re-ask's answer, kept with the answer's own row; the request's record then stands recovered,
        waiting for its next re-ask, or exhausted."""

        def hook(s: Session, listing_page_id: str, attempt: int) -> DeferredRequest:
            entry = self._entry(
                again.ordinal,
                again.asked,
                fetch,
                facts=facts,
                judgement=judgement,
                verdict=verdict,
                detail=detail,
                store_check=store_check,
                unique_before=again.unique_before,
                new=new,
                counted=counted,
                listing_page_id=listing_page_id,
                attempt=attempt,
                subdivisions=subdivisions,
                overlap=overlap,
                outcome=outcome,
            )
            row = reask.settle(
                s,
                again.row_id,
                again.ordinal,
                entry,
                recovered=recovered,
                now=self.timer.now(),
                outcome=outcome,
            )
            self._request_event(
                s,
                node,
                row,
                "REQUEST_RECOVERED"
                if row.state == reask.RECOVERED
                else "REQUEST_NOT_ANSWERED"
                if row.state == reask.EXHAUSTED
                else "REQUEST_SET_ASIDE",
            )
            return row

        return hook

    def _request_event(self, s: Session, node: Node, row: DeferredRequest, code: str) -> None:
        text = {
            "REQUEST_SET_ASIDE": f"asked again not before {iso(row.not_before)}",
            "REQUEST_RECOVERED": row.outcome,
            "REQUEST_NOT_ANSWERED": row.outcome,
        }[code]
        event(
            s,
            self.run_id,
            "INFO" if code == "REQUEST_RECOVERED" else "WARN",
            code,
            f"{node.category} › {node.sub_category}: page {row.requested_page} ({row.kind}): {text}"[:500],
            {
                "node": node.taxonomy_id,
                "page": row.requested_page,
                "kind": row.kind,
                "deferred_request": row.id,
                "state": row.state,
                "reasks_sent": row.reasks_dispatched,
                "max_reasks": row.max_reasks,
                "not_before": iso(row.not_before),
            },
        )

    def _settle_alone(self, again: Reasked, node: Node, *, verdict: str, detail: str) -> None:
        """A re-ask that ends without a page row of its own (a failure that stops the run, or one met after
        its answer came): kept, counted, never recovered. Nothing is written when its answer is already
        recorded."""
        with self.factory() as s:
            if reask.pending(s, again.row_id, again.ordinal):
                hook = self._settles(
                    again,
                    node,
                    None,
                    facts=None,
                    judgement=None,
                    verdict=verdict,
                    detail=detail[:400],
                    store_check="N/A",
                    new=0,
                    counted=False,
                    recovered=False,
                )
                hook(s, "", 0)
            s.commit()

    def _not_sent(self, again: Reasked, why: str) -> None:
        """The spending ceiling (or the account gate) refused the re-ask before anything was sent: it is not
        counted."""
        with self.factory() as s:
            reask.release(s, again.row_id, again.ordinal, why, self.timer.now())
            s.commit()

    def _wait(self, ctx: TaskContext, node: Node, state: NodeState, held: DeferredRequest) -> NoReturn:
        """The listing's task waits for the request's time: its progress is kept, the run's other listings
        go first, and the task comes back once the time has come."""
        text = (
            f"{node.category} › {node.sub_category}: page {held.requested_page} set aside "
            f"({held.kind}); asked again not before {iso(held.not_before)} ({held.reasks_dispatched} of "
            f"{held.max_reasks} re-asks sent)"
        )
        state.status = "IN_PROGRESS"
        state.reason = f"{held.original_reason}; set aside: asked again not before {iso(held.not_before)}"
        state.extra = {
            **state.extra,
            "set_aside": {
                "deferred_request": held.id,
                "page": held.requested_page,
                "kind": held.kind,
                "not_before": iso(held.not_before),
                "reasks_sent": held.reasks_dispatched,
                "max_reasks": held.max_reasks,
            },
        }
        with self.factory() as s:
            self.persist(s, ctx)
            self.coverage(s, node, state)
            s.commit()
        ctx.checkpoint(state.cursor(node))
        raise TaskDeferred(held.not_before, text)

    def _again(
        self, ctx: TaskContext, node: Node, state: NodeState, page: int, url: str, unique_before: int
    ) -> Reasked | str | None:
        """Before a later page is asked: was this very request set aside? ``None``: no, it is asked as
        usual. A text: its re-asks are spent (or it cannot be asked again), and the listing ends incomplete
        with that reason. Otherwise the re-ask to send now, already counted in the database. While the
        request's wait runs the task is set aside again (:class:`TaskDeferred`); a limit or the operator's
        stop is met before a re-ask is counted."""
        asked = reask.requested(node, page, url, self.store)
        with self.factory() as s:
            row = reask.find(s, self._key(node, page), lock=True)
            if row is None:
                return None
            now = self.timer.now()
            reask.close_unanswered(row, now)
            decision = reask.gate(row, now)
            s.commit()
        if decision == reask.EXHAUSTED:
            return row.outcome or reask.final_reason(row)
        if decision == reask.RECOVERED:
            # Its page was completed in the same transaction; a page still to read here is a contradiction.
            return (
                f"{row.original_reason}; the request is recorded as answered on a re-ask but the page is "
                f"not among the listing's completed pages: not asked again; {reask.NOT_EXHAUSTED}"
            )
        if decision == "wait":
            self._wait(ctx, node, state, row)
        self.check(ctx)  # the operator's stop and every limit, before the re-ask is counted
        with self.factory() as s:
            ordinal = reask.reserve(s, row.id, asked=asked, now=self.timer.now())
            event(
                s,
                self.run_id,
                "INFO",
                "REQUEST_ASKED_AGAIN",
                f"{node.category} › {node.sub_category}: page {page} ({row.kind}): re-ask {ordinal} of "
                f"{row.max_reasks}"[:500],
                {"node": node.taxonomy_id, "page": page, "deferred_request": row.id, "reask": ordinal},
            )
            s.commit()
        return Reasked(row.id, ordinal, asked, row.kind, unique_before)

    def _provider_failed_again(self, url: str, page: int, why: str) -> None:
        """A re-ask the provider brought no page for counts among the pages not read in a row (the run stops
        resumably when the provider keeps failing), but it is never retried on its own."""
        self.failed_in_a_row += 1
        if self.failed_in_a_row >= MAX_FAILED_LISTINGS_IN_A_ROW:
            raise RunStop(
                StopCode.PROVIDER_ERROR,
                f"{self.failed_in_a_row} pages in a row not read; last: {url}: page {page} asked again, "
                f"not read: {why}"[:600],
                resumable=True,
            )

    async def _facets_again(
        self, ctx: TaskContext, node: Node, state: NodeState, first_page: Sequence[str]
    ) -> list[dict[str, Any]]:
        """The first page of a listing above the source's window named no child listing and no brand, so
        the listing cannot be subdivided. Its products are kept (the page is the listing's page 1, counted
        as before). The same first page is asked again later for its filters, as any request set aside.
        Returns the subdivisions an answer named, each to be read and checked against its own filter as
        usual; or nothing when no answer named any, and the listing is then read page by page to the
        window and stays incomplete, as before.

        An answer asked again for its filters counts no product, whatever it lists: the subdivisions read
        every product through their own pages."""
        url = self.query_url(node, 1)
        asked = reask.requested(node, 1, url, self.store)
        requested = pagination.node_filter(node.partition_filter)
        seen = set(first_page)
        with self.factory() as s:
            row = reask.find(s, self._key(node, 1), lock=True)
            now = self.timer.now()
            if row is None:
                done = pagination.completed_pages(
                    pagination.rows_of(
                        s, self.run_id, node.category_source_id, node.taxonomy_id, self._pkey(node)
                    )
                )
                first = done[0]
                entry = {
                    **reask.answer_entry(
                        ordinal=0,
                        asked=asked,
                        facts=reask.facts_of(first),
                        judgement=None,
                        verdict=first.verdict,
                        detail="the listing's first page, counted; it names no child listing and no brand",
                        store_check=first.store_check,
                        unique_before=0,
                        new=len(first.identities or []),
                        counted=True,
                        observed_at=first.observed_at,
                        response_sha256=first.response_sha256,
                        page_fetch_id=first.page_fetch_id,
                        listing_page_id=first.id,
                        listing_page_attempt=first.attempt,
                        provider_request_id=first.provider_request_id,
                        subdivisions=[],
                    ),
                    "recorded_at": iso(now),
                }
                row = reask.set_aside(
                    s,
                    key=self._key(node, 1),
                    node=node,
                    url=url,
                    kind=reask.MISSING_FACETS,
                    store=self.store,
                    policy=self.reask,
                    now=now,
                    original_verdict=first.verdict,
                    original_reason=reask.NO_FACETS.format(total=state.total, available=state.available),
                    original_listing_page_id=first.id,
                    first=entry,
                )
                self._request_event(s, node, row, "REQUEST_SET_ASIDE")
            else:
                reask.close_unanswered(row, now)
            decision = reask.gate(row, now)
            named = reask.recovered_children(s, row) if decision == reask.RECOVERED else []
            s.commit()
        if decision == reask.RECOVERED:
            return named
        if decision == reask.EXHAUSTED:
            state.extra = {**state.extra, "not_subdivided": row.outcome or reask.final_reason(row)}
            return []
        if decision == "wait":
            self._wait(ctx, node, state, row)
        self.check(ctx)  # the operator's stop and every limit, before the re-ask is counted
        with self.factory() as s:
            ordinal = reask.reserve(s, row.id, asked=asked, now=self.timer.now())
            event(
                s,
                self.run_id,
                "INFO",
                "REQUEST_ASKED_AGAIN",
                f"{node.category} › {node.sub_category}: page 1 ({row.kind}): re-ask {ordinal} of "
                f"{row.max_reasks}"[:500],
                {"node": node.taxonomy_id, "page": 1, "deferred_request": row.id, "reask": ordinal},
            )
            s.commit()
        again = Reasked(row.id, ordinal, asked, row.kind, len(seen))
        held: DeferredRequest | None
        try:
            fetch = await self._page(ctx, node, "listing", 1, attempts=1)
        except ChallengeDetected as exc:
            self._page_refused(
                ctx,
                node,
                exc.fetch,
                page=1,
                url=url,
                facts=None,
                verdict=PageVerdict.BLOCKED,
                detail=str(exc),
                state_name="refused",
                hook=self._settles(
                    again,
                    node,
                    exc.fetch,
                    facts=None,
                    judgement=None,
                    verdict=PageVerdict.BLOCKED.value,
                    detail=str(exc)[:400],
                    store_check="N/A",
                    new=0,
                    counted=False,
                    recovered=False,
                ),
            )
            raise
        except oxylabs.CeilingReached as exc:
            self._not_sent(again, oxylabs.redact(str(exc), self.ox_key))
            raise
        except oxylabs.OxylabsError as exc:
            text = oxylabs.redact(str(exc), self.ox_key)
            if exc.kind not in LISTING_FAILURES:
                self._settle_alone(again, node, verdict=PageVerdict.FAILED.value, detail=text)
                raise
            held = self._page_refused(
                ctx,
                node,
                None,
                page=1,
                url=url,
                facts=None,
                verdict=PageVerdict.FAILED,
                detail=text,
                state_name="failed",
                hook=self._settles(
                    again,
                    node,
                    None,
                    facts=None,
                    judgement=None,
                    verdict=PageVerdict.FAILED.value,
                    detail=text[:400],
                    store_check="N/A",
                    new=0,
                    counted=False,
                    recovered=False,
                ),
            )
            self._provider_failed_again(url, 1, f"the provider brought no page ({exc.kind})")
            return self._facets_after(ctx, node, state, held)
        v = self.verify(fetch)
        view = self._view(fetch)
        facts = pagination.page_facts(1, self._summary, len(view.cards))
        store_problem = "; ".join(v.failures())
        # Judged as a first page in its own right: store, page, listing and filters as asked, and products.
        j = pagination.judge(
            facts,
            taxonomy=pagination.listing_id(node.taxonomy_id),
            earlier=[],
            store_verified=v.passed,
            store_problem=store_problem,
            requested_filter=requested,
        )
        named = []
        if j.accepted:
            named = view.children or pagination.brand_partitions(
                node.url,
                node.taxonomy_id,
                self._brands,
                store_id=self.store.location_id,
                modality=self.store.modality.value,
            )
        organic = set(facts.organic)
        detail = (
            (j.detail + "; " if j.detail else "")
            + "asked again for the listing's filters: "
            + (
                f"the answer names {len(named)} subdivision(s) ("
                + ("child listings" if view.children else "brands")
                + ")"
                if named
                else "the answer names no child listing and no brand"
                if j.accepted
                else "the answer does not count as the listing's first page"
            )
        )
        held = self._page_refused(
            ctx,
            node,
            fetch,
            page=1,
            url=url,
            facts=facts,
            verdict=j.verdict,
            detail=detail,
            state_name="reasked" if j.accepted else "refused",
            store_check="PASS" if v.passed else "FAIL",
            duplicates=len(organic & seen),
            binding=j.binding,
            children=named,
            code="PAGE_ASKED_AGAIN" if j.accepted else "PAGE_NOT_COUNTED",
            hook=self._settles(
                again,
                node,
                fetch,
                facts=facts,
                judgement=j,
                verdict=j.verdict.value,
                detail=detail,
                store_check="PASS" if v.passed else "FAIL",
                new=len(organic - seen),
                counted=False,
                recovered=bool(named),
                subdivisions=named,
                overlap=len(organic & seen),
                outcome=f"the listing is subdivided by the {len(named)} subdivision(s) this answer names; "
                "the answer itself counts no product"
                if named
                else "",
            ),
        )
        if j.verdict is PageVerdict.WRONG_CONTEXT:
            raise RunStop(
                StopCode.STORE_NOT_VERIFIED,
                f"{url}: {store_problem or 'store context incomplete'}",
                resumable=False,
            )
        if named:
            self.failed_in_a_row = 0
            self.abnormal_in_a_row = 0
            return named
        if j.verdict in (PageVerdict.EMPTY, PageVerdict.MALFORMED):
            self.abnormal_in_a_row += 1
            if self.abnormal_in_a_row >= MAX_ABNORMAL_LISTINGS_IN_A_ROW:
                raise AbnormalPage(f"{url}: {j.detail}")
        return self._facets_after(ctx, node, state, held)

    def _facets_after(
        self, ctx: TaskContext, node: Node, state: NodeState, held: DeferredRequest | None
    ) -> list[dict[str, Any]]:
        """After a re-ask for a listing's filters that named none: wait for the next one, or go on without
        subdivisions (the listing then stays incomplete beyond the window, with the reason)."""
        assert held is not None
        if held.state == reask.WAITING:
            self._wait(ctx, node, state, held)
        state.extra = {**state.extra, "not_subdivided": held.outcome or reask.final_reason(held)}
        return []

    async def read_listing(self, ctx: TaskContext, node: Node, state: NodeState) -> dict[str, Any]:
        """Every page of one listing, from the first page not completed, until the source's own count says the
        reachable pages were read, or a page stops the read.

        Release 1.10.0 (C1, ``limits.max_reasks_per_request`` above 0): a later page that lists only products
        of earlier pages, and the first page of a listing above the window that names no subdivision, are set
        aside and asked again later in the run (:mod:`marianos_headless.collection.reask`)."""
        if pagination.legacy_partition(node.taxonomy_id, node.partition_filter):
            # Release 1.9.0 (M1): such a reading's ID was "<listing>~<brand>" cut at 64 characters, so two
            # brands could share one ID, one task and one set of page rows. It is never resumed or merged.
            raise RunStop(
                StopCode.ABNORMAL_RESULT,
                f"{node.taxonomy_id!r}: a brand reading planned by a release before 1.9.0, whose ID could be "
                "shared by two brands; this release does not resume it: start a new run (its pages, if any, "
                "stay in this run's records)",
                resumable=False,
            )
        requested = pagination.node_filter(node.partition_filter)
        pkey = self._pkey(node)
        done = self._restore(node, state)
        earlier = [tuple(r.identities or []) for r in done]
        totals = [r.total for r in done if r.total is not None]
        children = list(done[0].children or []) if done else []
        while True:
            page = len(earlier) + 1
            above_window = (
                self.settings.coverage.partition_large_listings
                and state.total is not None
                and state.available is not None
                and state.total > state.available
            )
            if (
                page == 2
                and not children
                and above_window
                and self.reask.enabled
                and pagination.FILTER_MARK not in node.taxonomy_id
            ):
                # 1.10.0 (C1): the first page named nothing to subdivide the listing by: it is asked again
                # later for its filters (the task waits meanwhile); with none, the pages go on as before.
                children = await self._facets_again(ctx, node, state, earlier[0])
            if (
                page == 2
                and children
                and self.settings.coverage.partition_large_listings
                and state.total is not None
                and state.available is not None
                and state.total > state.available
            ):
                # The window hides results: page 1 is kept and the rest is read through the subdivisions the
                # page itself names (each a task of its own, checked as usual).
                self._partition(ctx, node, state, children)
                break
            end = pagination.last_page(state.total, state.available)
            if earlier and end is not None and page > end:
                with self.factory() as s:
                    rows = pagination.completed_pages(
                        pagination.rows_of(s, self.run_id, node.category_source_id, node.taxonomy_id, pkey)
                    )
                    unique = len({u for r in rows for u in (r.identities or [])})
                state.status, state.reason = pagination.outcome(len(earlier), totals, state.available, unique)
                break
            limit = self.cfg.limits.max_pages_per_listing
            if limit is not None and page > limit:
                state.status = "INCOMPLETE"
                state.reason = (
                    f"stopped at the declared limit of {limit} page(s) per listing: coverage incomplete"
                )
                break
            url = self.query_url(node, page)
            ready = self.ready if page == 1 and self.ready is not None and self.ready[0] == node.url else None
            unique_before = len({u for rows in earlier for u in rows})
            again: Reasked | None = None
            if self.reask.enabled and page > 1:
                # 1.10.0 (C1): this very request may have been set aside earlier in the run.
                due = self._again(ctx, node, state, page, url, unique_before)
                if isinstance(due, str):
                    state.status, state.reason = "INCOMPLETE", due
                    break
                again = due
            if ready is not None:
                _, fetch, v = ready
                self.ready = None
            else:
                try:
                    # A re-ask is sent once: no transport retry of its own beyond the two re-asks.
                    fetch = await self._page(
                        ctx, node, "listing", page, attempts=1 if again is not None else None
                    )
                except ChallengeDetected as exc:
                    self._page_refused(
                        ctx,
                        node,
                        exc.fetch,
                        page=page,
                        url=url,
                        facts=None,
                        verdict=PageVerdict.BLOCKED,
                        detail=str(exc),
                        state_name="refused",
                        hook=self._settles(
                            again,
                            node,
                            exc.fetch,
                            facts=None,
                            judgement=None,
                            verdict=PageVerdict.BLOCKED.value,
                            detail=str(exc)[:400],
                            store_check="N/A",
                            new=0,
                            counted=False,
                            recovered=False,
                        )
                        if again is not None
                        else None,
                    )
                    raise
                except oxylabs.CeilingReached as exc:
                    if again is not None:
                        self._not_sent(again, oxylabs.redact(str(exc), self.ox_key))
                    raise
                except oxylabs.OxylabsError as exc:
                    text = oxylabs.redact(str(exc), self.ox_key)
                    if exc.kind not in LISTING_FAILURES:
                        if again is not None:
                            self._settle_alone(again, node, verdict=PageVerdict.FAILED.value, detail=text)
                        raise
                    held = self._page_refused(
                        ctx,
                        node,
                        None,
                        page=page,
                        url=url,
                        facts=None,
                        verdict=PageVerdict.FAILED,
                        detail=text,
                        state_name="failed",
                        hook=self._settles(
                            again,
                            node,
                            None,
                            facts=None,
                            judgement=None,
                            verdict=PageVerdict.FAILED.value,
                            detail=text[:400],
                            store_check="N/A",
                            new=0,
                            counted=False,
                            recovered=False,
                        )
                        if again is not None
                        else None,
                    )
                    if again is None or held is None:
                        self._unread(ctx, node, page, f"the provider brought no page ({exc.kind})")
                    self._provider_failed_again(url, page, f"the provider brought no page ({exc.kind})")
                    if held.state == reask.WAITING:
                        self._wait(ctx, node, state, held)
                    state.status, state.reason = "INCOMPLETE", held.outcome
                    break
                v = self.verify(fetch)
            view = self._view(fetch)
            facts = pagination.page_facts(page, self._summary, len(view.cards))
            store_problem = "; ".join(v.failures())
            j = pagination.judge(
                facts,
                taxonomy=pagination.listing_id(node.taxonomy_id),
                earlier=earlier,
                store_verified=v.passed,
                store_problem=store_problem,
                requested_filter=requested,
            )
            check = "PASS" if v.passed else "FAIL"
            # Release 1.9.0rc2: the provider sometimes runs a listing page's scripts, asked or not, and such a
            # page carries no product tile while its state lists the products (stages S1 and O2, 2026-11-06:
            # 2 of 2 rendered answers, 0 of 5 unrendered ones). That is a failure to bring the server's page,
            # not an abnormal listing: the page is asked for again, and the run stops resumably if it keeps
            # happening.
            rendered_without_tiles = (
                j.verdict is PageVerdict.MALFORMED
                and facts.cards == 0
                and fetch.notes.get("rendered") is True
            )
            detail = j.detail
            if rendered_without_tiles:
                detail += (
                    "; the provider ran the page's scripts (its answer states run_js true), and a rendered "
                    "listing page carries no product tile: asked for again"
                )
            if j.verdict is PageVerdict.EMPTY and page == 1 and facts.total == 0:
                self._reading = None
                state.last_offset = -1
                self._step(ctx, node, fetch, v, view, state, 0, replay=False, first=True)
                state.total = 0
                return self._finish_node(node, state)
            if not j.accepted:
                hook: PageHook | None = None
                if again is not None:
                    # A re-ask's answer that does not count either: kept; another re-ask, or none is left.
                    hook = self._settles(
                        again,
                        node,
                        fetch,
                        facts=facts,
                        judgement=j,
                        verdict=j.verdict.value,
                        detail=detail,
                        store_check=check,
                        new=0,
                        counted=False,
                        recovered=False,
                    )
                elif self.reask.enabled and page > 1 and j.verdict in pagination.REPEATS:
                    # 1.10.0 (C1): nothing new, whatever page number, ranks and search ID the answer states:
                    # the request is set aside and asked again later, exactly.
                    hook = self._sets_aside(
                        node,
                        page,
                        url,
                        fetch,
                        facts=facts,
                        judgement=j,
                        store_check=check,
                        unique_before=unique_before,
                        reason=f"{pagination.GAP}: page {page}: {j.detail}"[:1000],
                    )
                held = self._page_refused(
                    ctx,
                    node,
                    fetch,
                    page=page,
                    url=url,
                    facts=facts,
                    verdict=j.verdict,
                    detail=detail,
                    state_name="stopped" if j.verdict in pagination.REPEATS else "refused",
                    store_check=check,
                    duplicates=len(j.duplicates),
                    binding=j.binding,
                    hook=hook,
                )
                if j.verdict is PageVerdict.WRONG_CONTEXT:
                    raise RunStop(
                        StopCode.STORE_NOT_VERIFIED,
                        f"{url}: {store_problem or 'store context incomplete'}",
                        resumable=False,
                    )
                if held is not None:
                    if again is not None and j.verdict in (PageVerdict.EMPTY, PageVerdict.MALFORMED):
                        self.abnormal_in_a_row += 1
                        if self.abnormal_in_a_row >= MAX_ABNORMAL_LISTINGS_IN_A_ROW:
                            raise AbnormalPage(f"{url}: {j.detail}")
                    if held.state == reask.WAITING:
                        self._wait(ctx, node, state, held)
                    # The re-asks are spent. The listing is incomplete for the reason it had; nothing says
                    # its pages were exhausted.
                    state.status, state.reason = "INCOMPLETE", held.outcome
                    break
                if rendered_without_tiles:
                    self._unread(ctx, node, page, detail)
                if j.verdict in (PageVerdict.EMPTY, PageVerdict.MALFORMED) or (
                    j.verdict in pagination.FILTER_VERDICTS and j.retry
                ):
                    self.abnormal_in_a_row += 1
                    if self.abnormal_in_a_row >= MAX_ABNORMAL_LISTINGS_IN_A_ROW:
                        raise AbnormalPage(f"{url}: {j.detail}")
                    self._unread(ctx, node, page, j.detail)
                state.status = "INCOMPLETE"
                state.reason = f"{pagination.GAP}: page {page}: {j.detail}"[:1000]
                break
            self.failed_in_a_row = 0
            self.abnormal_in_a_row = 0
            with self.factory() as s:
                attempt = pagination.next_attempt(
                    s, self.run_id, node.category_source_id, node.taxonomy_id, page, pkey
                )
            subdivisions: list[dict[str, Any]] = []
            if page == 1:
                subdivisions = view.children or (
                    []
                    if pagination.FILTER_MARK in node.taxonomy_id
                    else pagination.brand_partitions(
                        node.url,
                        node.taxonomy_id,
                        self._brands,
                        store_id=self.store.location_id,
                        modality=self.store.modality.value,
                    )
                )
            try:
                await self.read_terms(ctx, view)
                self._reading = PageContext(page, url, facts, j, attempt, check, tuple(subdivisions))
                self._reasked = again  # its record is closed in the page's own transaction (page_recorded)
                state.last_offset = -1 if page == 1 else (page - 2) * pagination.PAGE_SIZE
                try:
                    self._step(ctx, node, fetch, v, view, state, page - 1, replay=False, first=page == 1)
                finally:
                    self._reading = None
                    self._reasked = None
            except BaseException as exc:
                if again is not None:
                    # The answer came and counted for nothing yet: kept as it is, its re-ask stays counted.
                    self._settle_alone(
                        again,
                        node,
                        verdict=j.verdict.value,
                        detail=f"answered properly; not recorded: {type(exc).__name__}",
                    )
                raise
            if again is not None:
                state.extra = {k: x for k, x in state.extra.items() if k != "set_aside"}
            earlier.append(facts.organic)
            state.steps_done = page
            if facts.total is not None:
                state.total = facts.total
                totals.append(facts.total)
            if facts.available is not None:
                state.available = facts.available
            state.extra = {**state.extra, "route": "listing", "pages_read": page}
            if page == 1:
                children = subdivisions
            ctx.checkpoint(state.cursor(node))
        state.extra = {k: x for k, x in state.extra.items() if k != "set_aside"}
        note = state.extra.get("not_subdivided")
        if note and state.status == "INCOMPLETE" and str(note) not in state.reason:
            state.reason = f"{state.reason}; {note}"[:1900]
        return self._finish_node(node, state)

    async def read_search(self, ctx: TaskContext, node: Node, state: NodeState) -> dict[str, Any]:
        """The first page of the retailer's search for the listing's name, for a context whose listing pages
        are refused. Such a listing is never complete."""
        url = self.query_url(node)
        if self.ready is not None and self.ready[0] == node.url:
            _, fetch, v = self.ready
            self.ready = None
        else:
            try:
                fetch = await self._page(ctx, node, "listing")
            except oxylabs.OxylabsError as exc:
                if exc.kind not in LISTING_FAILURES:
                    raise
                self._page_refused(
                    ctx,
                    node,
                    None,
                    page=1,
                    url=url,
                    facts=None,
                    verdict=PageVerdict.FAILED,
                    detail=oxylabs.redact(str(exc), self.ox_key),
                    state_name="failed",
                )
                self._persist_now(ctx)
                self._unread(ctx, node, 1, f"the provider brought no page ({exc.kind})")
            v = self.verify(fetch)
        self.failed_in_a_row = 0
        view = self._view(fetch)
        facts = pagination.page_facts(1, self._summary, len(view.cards))
        with self.factory() as s:
            attempt = pagination.next_attempt(s, self.run_id, node.category_source_id, node.taxonomy_id, 1)
        self._reading = PageContext(
            1,
            url,
            facts,
            Judgement(PageVerdict.NEW, "first page of a search"),
            attempt,
            "PASS" if v.passed else "FAIL",
        )
        state.last_offset = -1
        if v.passed:
            await self.read_terms(ctx, view)
        try:
            self._step(ctx, node, fetch, v, view, state, 0, replay=False, first=True)
        except AbnormalPage as exc:
            self.abnormal_in_a_row += 1
            if self.abnormal_in_a_row >= MAX_ABNORMAL_LISTINGS_IN_A_ROW:
                raise
            state.status, state.reason = "INCOMPLETE", f"not read: {exc}"[:600]
            state.extra = {
                **state.extra,
                "abnormal_page": str(exc)[:300],
                "query": query_of(node),
                "query_url": url,
            }
            return self._finish_node(node, state)
        finally:
            self._reading = None
        self.abnormal_in_a_row = 0
        query_total = state.total
        state.extra = {
            **state.extra,
            "read_through": "oxylabs search, first page",
            "query": query_of(node),
            "query_url": url,
            "query_total": query_total,
            "query_available": state.available,
            "cards": len(view.cards),
            "members": len(state.seen),
        }
        # The search's count is not the listing's: the listing's own total stays unknown.
        state.total = None
        if state.status not in FINISHED_NODE or state.status == "EMPTY":
            state.status = "INCOMPLETE"
            state.reason = SEARCH_ROUTE_REASON.format(
                url=node.url,
                query=query_of(node),
                cards=len(view.cards),
                total=query_total if query_total is not None else "?",
                members=len(state.seen),
            )
        state.steps_done = 1
        return self._finish_node(node, state)
