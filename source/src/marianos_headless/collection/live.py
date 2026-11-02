"""Live collection of one store through Scrapfly's Cloud Browser, on the run pipeline's tasks.

A live run has a ``preflight`` task, one ``listing_node`` task per planned subcategory listing page,
then ``assemble``, ``validate`` and ``export``. The collector opens a cloud browser session, loads
robots.txt (fail closed), opens a listing page and selects the configured store with the site's own
store picker (as recorded live on 2026-10-20). Every page it reads must pass the store check
(:func:`marianos_headless.worker.store_selection.verify_store`: location ID, name, address, ZIP,
fulfillment, an
explicit selection in this session, and the store of every data request the page made).

Paging: a listing shows 24 products and a "Load More Results" button inside
``[data-testid="paginate-items"]``, the only paging control on the saved live pages. Each click is a
paced step whose new products count only when the step passed the store check and the page requested
them with a later ``page.offset`` for the configured store. Products are read from the grid's cards (a
sponsored card only when the site's own product data places it in the listing, release 1.5.0); records
are built at once from the displayed values and saved idempotently (first placement wins), so retries,
reconnects and resumed runs never count a product twice. The task's checkpoint keeps the steps done and
the products seen; a resumed task opens the page again and repeats the clicks up to that point.

Before every navigation or click the run's limits are checked (verified products per run and per day,
active minutes, estimated API credits per run and per day, the account's reserve, the schedule window)
and the operator's Pause/Stop. A limit stops the run resumably (:class:`RunStop`); the cloud browser is
closed when the worker stops. A refusal by the site, a page not priced for the store, or an abnormal
page stops the run for review; nothing is retried with another identity (ADR-007/ADR-008).
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import hashlib
import json
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from time import monotonic
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from pydantic import SecretStr
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from marianos_headless import __version__
from marianos_headless.acquisition import scrapfly
from marianos_headless.acquisition.browser import (
    BrowserSession,
    ChallengeDetected,
    NavigationFailed,
    NoDocumentResponse,
    PageFetch,
    RobotsDisallowed,
    RobotsUnreachable,
)
from marianos_headless.acquisition.capture import CapturedResponse, query_values
from marianos_headless.acquisition.challenge import detect_document_challenge
from marianos_headless.acquisition.pacing import NavigationBudgetExceeded
from marianos_headless.assembly.offers import format_description, offer_terms, restriction_reason
from marianos_headless.assembly.record_builder import (
    EXPORTED_RECORD_STATUSES,
    BuiltRecord,
    CategoryAssignment,
    FieldSource,
    RecordStatus,
    StoreFields,
    build_product_record,
)
from marianos_headless.checks import source_check
from marianos_headless.collection import pagination, reconciliation, recovery, retention, scrapfly_account
from marianos_headless.collection.config import CollectionConfig
from marianos_headless.collection.limits import (
    StopCode,
    Usage,
    credit_room,
    first_stop,
    product_limit_code,
    product_room,
    segment_totals,
    snapshot_provider,
    verified_in_run,
    verified_on_day,
)
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.reconciliation import FINISHED_NODE
from marianos_headless.collection.schedule import day_bounds, local_day
from marianos_headless.config_file import CanaryConfig, HistoricalConfig
from marianos_headless.core.findings import DataMode
from marianos_headless.core.ids import new_id
from marianos_headless.core.paths import PARSER_VERSION
from marianos_headless.core.schema import ordered_record
from marianos_headless.core.settings import BrowserProvider, Settings, StoreConfig
from marianos_headless.core.timeutil import iso, store_local_date, utcnow
from marianos_headless.core.version import source_version
from marianos_headless.db import queue
from marianos_headless.db.models import (
    Artifact,
    CategorySource,
    CollectionSegment,
    MembershipRow,
    NodeCoverage,
    OfferObservationRow,
    ProductObservation,
    RecordRow,
    Run,
    StoreAttestation,
    Task,
)
from marianos_headless.db.models import CapturedResponse as CapturedRow
from marianos_headless.db.models import PageFetch as PageFetchRow
from marianos_headless.publishing.exports import record_sha256
from marianos_headless.sites.marianos.dom_parsers import (
    CardObservation,
    HeaderStore,
    parse_cards,
    parse_header_store,
)
from marianos_headless.sites.marianos.initial_state import InitialStateNotFound, parse_initial_state
from marianos_headless.sites.marianos.observations import (
    OfferDetails,
    card_evidence,
    offer_details,
    store_fields,
)
from marianos_headless.sites.marianos.serialize import card_to_dict
from marianos_headless.sites.marianos.source_json import COUPONS, PRODUCTS, ResponseRef, SourceIndex
from marianos_headless.sites.marianos.store_context import (
    StoreDetails,
    request_location_id,
    store_context_from_state,
)
from marianos_headless.validation.gates import (
    AttestationSummary,
    CategoryOutcome,
    RunEvidence,
    field_completeness,
    run_gates,
)
from marianos_headless.worker.runner import CancelledByOperator, Handler, RunStop, TaskContext
from marianos_headless.worker.runs import event, record_validation, transition
from marianos_headless.worker.store_selection import (
    LISTING_SELECTORS,
    StoreSelector,
    StoreVerification,
    base_of,
    picker_confirmed_before,
    verify_store,
)

T = TypeVar("T")

GRID_CSS = '[data-testid="paginate-items"]'
# A grid card: "product-card-N", or (live 2026-11-02, from 12:30Z at 53100502 Pickup) "mini-product-card-N"
# (class MiniProductCard), the same product card with the same inner test ids (release 1.8.0rc3).
CARD_CSS = '[data-testid^="product-card-"], [data-testid^="mini-product-card-"]'
LOAD_MORE_CSS = '[data-testid="paginate-items"] button.LoadMore__load-more-button'
RESULTS_CSS = '[data-testid="SearchHeader-heading"]'
GRID_SELECTORS = replace(LISTING_SELECTORS, card_root=CARD_CSS)
_RESULTS = re.compile(r"^\s*([\d,]+)\s+results?\s*$", re.I)
PAGE_SIZE = 24  # products per Load More step on the live site (page.size=24); bounds the clicks only
EXTRA_STEPS = 3
UNKNOWN_TOTAL_MAX_STEPS = 200
MIN_SESSION_CREDITS = 40.0  # no cloud browser is opened with less credit room than this
ROTATE_SESSION_AFTER = 0.6  # of the provider's session timeout: a new session before the next page
MAX_RECONNECTS = 2  # per segment, when the cloud browser goes away
# The task's lease (120 s) is renewed this often while a handler works: a slow page or the store
# picker's steps (live 2026-10-22: 32 s for the first page, then five picker steps of about 15 s each)
# must not outlive it.
KEEPALIVE_S = 30.0
CARDS_GREW_JS = (
    '(n) => document.querySelectorAll(\'[data-testid="paginate-items"] [data-testid^="product-card-"], '
    '[data-testid="paginate-items"] [data-testid^="mini-product-card-"]\').length > n'
)


# -- listing pages ------------------------------------------------------------------------------------


def segment_window_end(occ: Mapping[str, Any], now: datetime, tz: ZoneInfo) -> datetime:
    """When this execution of a scheduled run must stop: the end of its occurrence's daily window on the
    occurrence's own day; on a later day (a continuation), the same daily window's end on that day (local
    clock times; daylight-saving changes handled by ``zoneinfo``)."""
    end = datetime.fromisoformat(str(occ["window_end"])).astimezone(tz)
    if now.astimezone(tz) < end:
        return end
    start = datetime.fromisoformat(str(occ.get("window_start") or occ["start"])).astimezone(tz)
    day = now.astimezone(tz).date()
    days_after = (end.date() - start.date()).days  # 1 when the window ends at midnight
    return datetime.combine(day + timedelta(days=days_after), end.time(), tzinfo=tz)


@dataclass
class ListingView:
    grid: bool
    cards: list[CardObservation]
    sponsored: set[str]
    displayed_total: int | None
    searches: list[dict[str, Any]]  # products-search requests of the step: offset, store, total, available

    @property
    def total(self) -> int | None:
        totals = [s["total"] for s in self.searches if isinstance(s.get("total"), int)]
        return totals[-1] if totals else self.displayed_total

    @property
    def available(self) -> int | None:
        """How many of the results the site's search lets the page reach (``availableCount``)."""
        found = [s["available"] for s in self.searches if isinstance(s.get("available"), int)]
        return found[-1] if found else None

    @property
    def children(self) -> list[dict[str, Any]]:
        """The child listings the site's category facet names for this listing (id, name, slug, count)."""
        found = [s["children"] for s in self.searches if s.get("children")]
        return list(found[-1]) if found else []


def displayed_total(tree: LexborHTMLParser) -> int | None:
    node = tree.css_first(RESULTS_CSS)
    m = _RESULTS.match(node.text(deep=True) or "") if node is not None else None
    return int(m.group(1).replace(",", "")) if m else None


def grid_cards(html: str) -> tuple[bool, list[CardObservation], set[str], int | None]:
    """(grid present, its product cards in page order, sponsored card IDs, the displayed result count).

    Only cards inside the paginated grid count: carousels elsewhere on the page (recommendations,
    sponsored banners) belong to other listings."""
    tree = LexborHTMLParser(html)
    total = displayed_total(tree)
    grid = tree.css_first(GRID_CSS)
    if grid is None:
        return False, [], set(), total
    sub = LexborHTMLParser(grid.html or "")
    cards = parse_cards(sub, GRID_SELECTORS)
    sponsored = {
        n.attributes.get("data-testid") or ""
        for n in sub.css(CARD_CSS)
        if "sponsored" in (n.text(deep=True) or "").lower()
    }
    return True, cards, sponsored, total


def search_requests(
    captured: Sequence[CapturedResponse], read: Callable[[str], bytes]
) -> list[dict[str, Any]]:
    """The products-search requests a page step made: offset, size, store and the total it reported."""
    out = []
    for c in captured:
        if c.kind != "products_search":
            continue
        children: list[dict[str, Any]] = []
        offset = next((int(v) for v in query_values(c.url, "page.offset") if v.isdigit()), None)
        size = next((int(v) for v in query_values(c.url, "page.size") if v.isdigit()), None)
        total = available = None
        if c.artifact_key and c.status == 200:
            try:
                body = json.loads(gzip.decompress(read(c.artifact_key)))
                meta = (body.get("meta") or {}).get("productsSearch") or {}
                total = meta.get("totalCount") if isinstance(meta.get("totalCount"), int) else None
                # The site's own window: the results its search lets the page reach (250 on 2026-10-23).
                count = meta.get("availableCount")
                available = count if isinstance(count, int) else None
                taxonomy = next(iter(query_values(c.url, "filter.taxonomies")), "")
                children = facet_children((meta.get("facets") or {}).get("category"), taxonomy)
            except (KeyError, ValueError, OSError, AttributeError):
                total = available = None
        out.append(
            {
                "offset": offset,
                "size": size,
                "location_id": request_location_id(c.url),
                "status": c.status,
                "total": total,
                "available": available,
                "children": children,
            }
        )
    return out


def facet_children(tree: Any, taxonomy: str) -> list[dict[str, Any]]:
    """The children of ``taxonomy`` in a products-search response's ``facets.category`` tree (each with the
    id, name, slug and count the site states). Only true descendants (ids starting with the parent's)
    count."""
    if not taxonomy or not isinstance(tree, list):
        return []
    stack = list(tree)
    while stack:
        n = stack.pop()
        if not isinstance(n, dict):
            continue
        if str(n.get("id")) == taxonomy:
            return [
                {"id": str(c.get("id")), "name": str(c.get("name") or ""), "slug": str(c.get("slug") or ""),
                 "count": c.get("count") if isinstance(c.get("count"), int) else None}
                for c in n.get("children") or []
                if isinstance(c, dict)
                and str(c.get("id", "")).startswith(taxonomy)
                and str(c.get("id")) != taxonomy
                and c.get("slug")
            ]  # fmt: skip
        stack.extend(n.get("children") or [])
    return []


def window_reason(total: int | None, available: int | None, seen: int) -> str | None:
    """Why a listing whose Load More ended is not complete: the site reports more results than its search
    lets the page reach. None when nothing says so (the listing was read to its end)."""
    if total is None or available is None or available >= total or seen >= total:
        return None
    return (
        f"the site's search lets the page reach {available} of the {total} results it reports for this "
        f"listing (availableCount); {seen} products were read, the rest are not reachable through its "
        "Load More (a narrower listing or filter is needed)"
    )


def max_steps(total: int | None) -> int:
    return UNKNOWN_TOTAL_MAX_STEPS if total is None else math.ceil(total / PAGE_SIZE) + EXTRA_STEPS


async def obstruction_challenge(page: Page) -> list[str]:
    """The challenge signals of the page as it is now (a CAPTCHA frame, an interstitial, a denial), empty when
    the page shows none. A page that cannot be read counts as a challenge: nothing is clicked blind."""
    try:
        html = await asyncio.wait_for(page.content(), 15)
    except Exception:
        return ["page_unreadable"]
    verdict = detect_document_challenge(None, html, expect_initial_state=False)
    return list(verdict.reasons) if verdict.is_challenge else []


def click_problem(exc: BaseException) -> str:
    """A browser click error in one line: its first line and the last entry of its call log (what the
    browser was waiting for, e.g. another element receiving the click)."""
    lines = [ln.strip(" -") for ln in str(exc).splitlines() if ln.strip(" -")]
    if not lines:
        return type(exc).__name__
    last = lines[-1] if len(lines) > 1 else ""
    return (lines[0] + (f" ({last})" if last else ""))[:300]


def after_store_confirmed(fetches: Sequence[PageFetch]) -> list[PageFetch]:
    """A browser session's page steps from its store confirmation on. Once the store is confirmed the page
    requests its products' data for that store (live: during the ``confirm_store`` step itself, and the
    next listing load used it), so these responses describe the selected store; each product's response
    still names the store its price is for, which the record's source check verifies."""
    out: list[PageFetch] = []
    for f in fetches:
        if out or f.purpose == "confirm_store":
            out.append(f)
    return out


def index_captures(sources: SourceIndex, fetch: PageFetch, read: Callable[[str], bytes]) -> int:
    """Add the product and coupon responses of one page step to ``sources``."""
    n = 0
    for c in fetch.captured:
        if c.kind not in (PRODUCTS, COUPONS) or c.status != 200 or not c.artifact_key:
            continue
        try:
            body = gzip.decompress(read(c.artifact_key))
        except (OSError, KeyError, EOFError):
            continue
        n += sources.add(c.kind, body, ResponseRef(c.kind, fetch.fetch_id, c.body_sha256, c.observed_at))
    return n


@dataclass(frozen=True)
class CardBuild:
    built: BuiltRecord
    details: OfferDetails


def build_card(
    card: CardObservation,
    *,
    fetch_id: str,
    observed_at: str,
    store: StoreConfig,
    store_values: StoreFields,
    store_provenance: dict[str, FieldSource],
    category: CategoryAssignment,
    crawl_date: str,
    settings: Settings,
    detector: Any,
    sources: SourceIndex,
) -> CardBuild:
    """The record of one grid card of a verified page step: its displayed values, the offer details and
    store check from the site's own responses, and why each empty field is empty."""
    modality = store.modality.value
    details = offer_details(card, sources, store=store.location_id, modality=modality, tz=store.timezone)
    ev = card_evidence(
        card,
        fetch_id=fetch_id,
        observed_at=observed_at,
        location_attested=True,
        details=details,
        sel=GRID_SELECTORS,
    )
    built = build_product_record(
        ev,
        store=store_values,
        category=category,
        crawl_date=crawl_date,
        settings=settings.records,
        detector=detector,
        configured_modality=modality,
        store_provenance=store_provenance,
    )
    return CardBuild(built, details)


def offer_summaries(built: BuiltRecord, settings: Settings) -> list[dict[str, Any]]:
    fmt = settings.records.deal_description_format
    return [
        {
            "sources": [s.value for s in (c.offer.sources or (c.offer.source,))],
            "kind": c.kind.value,
            "tag": c.offer.tag,
            "text": c.offer.text,
            "terms": c.offer.terms,
            "expiry_text": c.offer.expiry_text,
            "requires_clip": c.requires_clip,
            "explicit_price": c.explicit_price,
            "modalities": sorted(c.restricted_to) if c.restricted_to else [],
            "conditions": offer_terms(c),
            "description": format_description(c.offer, fmt),
            "flags": [f.value for f in c.flags],
            # Why the offer is not in the record's deal fields, when it is not (release 1.4.0).
            "left_out": restriction_reason(c),
        }
        for c in built.deals.classified
    ]


def page_store(html: str, store: StoreConfig) -> tuple[StoreDetails | None, HeaderStore, str | None]:
    header = parse_header_store(LexborHTMLParser(html))
    try:
        ctx = store_context_from_state(parse_initial_state(html))
    except (InitialStateNotFound, ValueError):
        return None, header, None
    return ctx.store(store.location_id), header, ctx.site_version


# -- state ----------------------------------------------------------------------------------------------


@dataclass
class StepResult:
    new_cards: int = 0  # cards not seen before on this listing page
    new_records: int = 0
    new_verified: int = 0
    duplicates: int = 0
    sponsored: int = 0
    # Sponsored cards whose own product data does not place them in the listing: placement kept, no record.
    sponsored_elsewhere: int = 0
    without_upc: int = 0
    other_listing: int = 0  # recorded under another planned listing they belong to (assign)
    off_plan: int = 0  # belonging to no planned listing: not recorded (assign)
    excluded: int = 0  # recorded and left out of the export (approximate weight, ...)
    conflicts: int = 0  # recorded with a price conflict
    capped: StopCode | None = None


@dataclass
class NodeState:
    steps_done: int = 0
    seen: list[str] = field(default_factory=list)
    total: int | None = None
    last_offset: int = -1
    status: str = "IN_PROGRESS"
    reason: str = ""
    available: int | None = None  # the site's availableCount (cursors written before 1.2.0 have none)
    partitions: list[dict[str, Any]] = field(default_factory=list)  # child listings read instead (1.2.1)
    extra: dict[str, Any] = field(default_factory=dict)  # what a provider's collector adds (1.3.0)

    @classmethod
    def from_cursor(cls, cursor: Mapping[str, Any]) -> NodeState:
        return cls(
            int(cursor.get("steps_done") or 0),
            list(cursor.get("seen") or []),
            cursor.get("total"),
            int(cursor.get("last_offset", -1)),
            str(cursor.get("status") or "IN_PROGRESS"),
            str(cursor.get("reason") or ""),
            cursor.get("available"),
            list(cursor.get("partitions") or []),
            dict(cursor.get("extra") or {}),
        )

    def cursor(self, node: Node) -> dict[str, Any]:
        return {
            "node": node.as_dict(),
            "steps_done": self.steps_done,
            "seen": self.seen,
            "total": self.total,
            "available": self.available,
            "partitions": self.partitions,
            "extra": self.extra,
            "last_offset": self.last_offset,
            "status": self.status,
            "reason": self.reason,
        }


class _SessionLost(Exception):
    """The cloud browser went away (the provider ended the session, or it stopped answering)."""


class AbnormalPage(Exception):
    pass


# -- the collector ------------------------------------------------------------------------------------


class LiveCollector:
    LISTING_SETTLE_MS = 4000  # late data requests of a listing page (as in the pilot)
    STEP_SETTLE_MS = 1500  # after the new cards of a Load More step appeared
    # The site's own data responses kept with the run (product and coupon data for the record checks).
    CAPTURE_KINDS: tuple[str, ...] = ("products_search", PRODUCTS, COUPONS)
    # Fields every exported record must fill (validation G8): Mariano's shows a UPC on every card.
    REQUIRED_FIELDS: tuple[str, ...] = ("product_title", "url", "upc", "category")

    def __init__(
        self,
        pipe: Any,  # marianos_headless.worker.pipeline.Pipeline
        run_id: str,
        *,
        api_key: SecretStr | None,
        config: CollectionConfig,
        trigger: str,
        account_get: Callable[..., Any] | None = None,
        clock: Callable[[], datetime] = utcnow,
        canary: CanaryConfig | None = None,
        historical: HistoricalConfig | None = None,
    ):
        self.pipe = pipe
        self.canary_cfg = canary or CanaryConfig()
        self.historical_cfg = historical or HistoricalConfig()
        self.run_id = run_id
        self.key = api_key
        self.cfg = config
        self.trigger = trigger
        self.account_get = account_get
        self.clock = clock
        self.store: StoreConfig = pipe.store_cfg
        self.factory = pipe.factory
        self.storage = pipe.storage
        acq = pipe.settings.acquisition.model_copy(update={"browser_provider": BrowserProvider.SCRAPFLY})
        self.settings: Settings = pipe.settings.model_copy(update={"acquisition": acq})
        self.session: BrowserSession | None = None
        self.selector: StoreSelector | None = None
        self.session_opened: float | None = None
        self.segment_id: str | None = None
        self.segment_started = monotonic()
        self.closed_credits = 0.0
        self.sessions_opened = 0
        self.sessions_closed = 0
        self.steps = 0
        self.account_start: int | None = None
        self.reconnects = 0
        self.binding: StopCode | None = None
        self.ready: tuple[str, PageFetch, StoreVerification] | None = None
        self.persisted: set[str] = set()
        # Product and coupon responses since the store was confirmed: offer details and per-product checks.
        self.sources = SourceIndex()
        self.indexed: set[str] = set()
        self.verified_at_start = 0
        self.window_end: datetime | None = None
        with self.factory() as s:
            run = s.get(Run, run_id)
            assert run is not None
            self.store_id = run.store_id
            snap = run.config_snapshot or {}
            self.run_provider = snapshot_provider(snap)  # the unit of its credits (release 1.7.0)
            occ = snap.get("occurrence") or {}
            if run.trigger == "schedule" and occ.get("window_end"):
                self.window_end = segment_window_end(occ, self.clock(), self.cfg.tz)
            self.plan = [Node.from_dict(n) for n in (snap.get("plan") or {}).get("nodes", [])]
            self.recorded: set[str] = set(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))
            self.canary_done = ((run.counts or {}).get("canary") or {}).get("status") == "passed"

    # -- wiring ---------------------------------------------------------------------------------

    def handlers(self) -> dict[str, Handler]:
        return {
            "preflight": self.h_preflight,
            "listing_node": self.h_listing,
            "assemble": self.h_assemble,
            "validate": self.h_validate,
            "export": self.pipe.h_export,
        }

    @property
    def prefix(self) -> str:
        return f"{self.pipe.prefix(self.run_id)}/live"

    @property
    def base(self) -> str:
        return base_of(self.plan[0].url) if self.plan else "https://www.marianos.com"

    def _read(self, key: str) -> bytes:
        data: bytes = self.storage.get_bytes(key)
        return data

    def html(self, fetch: PageFetch) -> str:
        return gzip.decompress(self._read(fetch.dom_key)).decode("utf-8") if fetch.dom_key else ""

    # -- segment --------------------------------------------------------------------------------

    def _collection_left(self, s: Session) -> bool:
        return (
            s.scalar(
                select(Task.id)
                .where(
                    Task.run_id == self.run_id,
                    Task.kind.in_(("preflight", "listing_node")),
                    Task.state.not_in(tuple(queue.TERMINAL_STATES)),
                )
                .limit(1)
            )
            is not None
        )

    async def _read_account(self) -> scrapfly.AccountUsage:
        assert self.key is not None
        usage = await asyncio.to_thread(
            scrapfly.read_account, self.settings.acquisition.scrapfly, self.key, self.account_get
        )
        with self.factory() as s:
            scrapfly_account.remember_balance(s, usage, "collector", self.key)
            s.commit()
        return usage

    async def begin(self) -> tuple[str, str] | None:
        """Before the worker starts. With listing work left: the key, the account (reachable, not
        suspended, credits left) and the limits; then a collection segment is opened. Returns a stop."""
        now = self.clock()
        with self.factory() as s:
            # Segments a worker left open (a forced kill): closed as abandoned with their observed bounds;
            # their unsettled provider requests are kept as possibly billed (recovery.py). The store's run
            # lock is held, so no other worker can still be writing to them. First of all: a dead worker's
            # reservation must not be what refuses the room for a resume.
            abandoned = recovery.recover_abandoned(s, self.store_id, now=now)
            s.commit()
        with self.factory() as s:
            if not self._collection_left(s):
                return None  # only assembling, checking and exporting are left: the stop reason stays
            run = s.get(Run, self.run_id)
            assert run is not None
            run.stop_code, run.stop_detail = None, None  # a new stretch of collection starts
            s.commit()
        stop = await self.open_account()
        if stop is not None:
            return stop
        now = self.clock()
        with self.factory() as s:
            seg = CollectionSegment(
                run_id=self.run_id,
                store_id=self.store_id,
                trigger=self.trigger[:16],
                day=local_day(now, self.cfg.tz).isoformat(),
                started_at=now,
                heartbeat_at=now,
                account_remaining_start=self.account_start,
            )
            s.add(seg)
            s.flush()
            self.segment_id = seg.id
            self.verified_at_start = verified_in_run(s, self.run_id)
            # The code of each execution: a run resumed by a newer build says so in its own record.
            event(
                s,
                self.run_id,
                "INFO",
                "SEGMENT_STARTED",
                f"collection segment {seg.id} started ({self.trigger})",
                {
                    "segment": seg.id,
                    "code": {"version": __version__, "parser_version": PARSER_VERSION, **source_version()},
                    "account_remaining": self.account_start,
                    "verified_so_far": self.verified_at_start,
                    "abandoned_segments_recovered": [a["segment"] for a in abandoned],
                },
            )
            s.commit()
        self.segment_started = monotonic()
        stop = self.limit_stop(opening=True)
        if stop is not None:
            await self.end(stop[0], stop[1])
            return stop
        return None

    async def open_account(self) -> tuple[str, str] | None:
        """The provider account before a collection segment (here Scrapfly): a key, the account reachable
        and not suspended, credits left. Sets :attr:`account_start`; returns a stop."""
        if self.key is None:
            return StopCode.NO_API_KEY, "Save the client's Scrapfly API key in Settings > Scrapfly first."
        usage = await self._read_account()
        connection, message = scrapfly_account.classify(usage)
        if connection in ("invalid_key", "suspended"):
            return StopCode.PROVIDER_AUTH, message
        if connection == "unavailable":
            return StopCode.ACCOUNT_UNAVAILABLE, message
        if connection == "exhausted":
            return StopCode.CREDITS_EXHAUSTED, message
        self.account_start = usage.credits_remaining
        return None

    async def account_remaining_now(self) -> int | None:
        """The account's remaining credits when a segment ends (None when they cannot be read)."""
        if self.key is None:
            return None
        try:
            usage = await self._read_account()
        except Exception:  # the segment is closed whatever the account says
            return None
        return usage.credits_remaining if usage.http_status == 200 else None

    async def end(self, code: str | None = None, detail: str | None = None) -> None:
        """Always: close the cloud browser, read the account, close the segment."""
        await self.close_session()
        if self.segment_id is None:
            return
        remaining_end = await self.account_remaining_now()
        with self.factory() as s:
            seg = s.get(CollectionSegment, self.segment_id)
            run = s.get(Run, self.run_id)
            # A segment another worker already closed as abandoned keeps that record (its lease was lost).
            if seg is not None and seg.end_state is None:
                seg.end_state = "ended"
                seg.ended_at = self.clock()
                seg.heartbeat_at = seg.ended_at
                seg.active_s = monotonic() - self.segment_started
                seg.credits_estimated = self.closed_credits
                seg.browser_sessions, seg.browsers_closed = self.sessions_opened, self.sessions_closed
                seg.steps = self.steps
                seg.products_verified = verified_in_run(s, self.run_id) - self.verified_at_start
                seg.account_remaining_end = remaining_end
                seg.stop_code = code or (run.stop_code if run else None)
                seg.stop_detail = ((detail or (run.stop_detail if run else None) or "")[:2000]) or None
            s.commit()
        self.segment_id = None

    def heartbeat(self, s: Session) -> None:
        """The segment's progress, written only while it is still open: a segment another worker closed as
        abandoned (this worker was presumed dead) stops this worker instead (fencing)."""
        if self.segment_id is None:
            return
        res = s.execute(
            update(CollectionSegment)
            .where(CollectionSegment.id == self.segment_id, CollectionSegment.end_state.is_(None))
            .values(
                heartbeat_at=self.clock(),
                active_s=monotonic() - self.segment_started,
                credits_estimated=self.segment_credits(),
                browser_sessions=self.sessions_opened,
                browsers_closed=self.sessions_closed,
                steps=self.steps,
                products_verified=verified_in_run(s, self.run_id) - self.verified_at_start,
            )
        )
        if getattr(res, "rowcount", 1) == 0:
            s.rollback()
            raise RunStop(
                StopCode.LEASE_LOST,
                f"collection segment {self.segment_id} was closed by another worker: this one stops",
                resumable=False,
            )

    # -- limits -----------------------------------------------------------------------------------

    def segment_credits(self) -> float:
        current = self.session.meter.estimate().credits if self.session and self.session.meter else 0.0
        return self.closed_credits + current

    def usage(self) -> Usage:
        day = local_day(self.clock(), self.cfg.tz)
        start, end = day_bounds(day, self.cfg.tz)
        with self.factory() as s:
            run_products = verified_in_run(s, self.run_id)
            day_products = verified_on_day(s, self.store_id, start, end)
            active, credits, day_credits = segment_totals(
                s,
                self.run_id,
                self.store_id,
                day.isoformat(),
                provider=self.run_provider,
                exclude=self.segment_id,
            )
        live = self.segment_credits()
        return Usage(
            run_products,
            day_products,
            active + (monotonic() - self.segment_started),
            credits + live,
            day_credits + live,
            monotonic() - self.segment_started,
        )

    def account_remaining(self) -> float | None:
        return None if self.account_start is None else self.account_start - self.segment_credits()

    def step_credits(self) -> float:
        s = self.session
        if s is None or s.meter is None:
            return MIN_SESSION_CREDITS
        now = s.meter.estimate().credits
        return max(0.0, s.meter.estimate(extra_bytes=s.projected_step_bytes(), extra_s=30).credits - now)

    def limit_stop(self, *, opening: bool = False) -> tuple[str, str] | None:
        if self.window_end is not None and self.clock() >= self.window_end:
            return StopCode.SCHEDULE_WINDOW_END, f"the daily window ended at {self.window_end.isoformat()}"
        usage = self.usage()
        need = MIN_SESSION_CREDITS if opening or self.session is None else self.step_credits()
        stop = first_stop(
            self.cfg.limits, usage, account_remaining=self.account_remaining(), min_step_credits=need
        )
        if stop is not None:
            return stop
        room, self.binding = credit_room(self.cfg.limits, usage, self.account_remaining())
        if self.session is not None and self.session.meter is not None:
            # The browser itself then refuses a step that could cross the remaining room (check_budget).
            self.session.max_credits = None if room is None else self.session.meter.estimate().credits + room
        return None

    def check(self, ctx: TaskContext) -> None:
        """Before every navigation or click: the operator's Pause/Stop, then the limits."""
        if ctx.cancelled():
            raise CancelledByOperator()
        stop = self.limit_stop()
        if stop is not None:
            raise RunStop(stop[0], stop[1], resumable=True)
        ctx.heartbeat()

    # -- browser session --------------------------------------------------------------------------

    async def close_session(self) -> None:
        if self.session is None:
            return
        session, self.session = self.session, None
        try:
            await session.__aexit__(None, None, None)
        finally:
            estimate = session.meter.estimate().credits if session.meter else 0.0
            self.closed_credits += estimate
            if session.closed_at is not None:
                self.sessions_closed += 1
            self.selector, self.ready = None, None
            with self.factory() as s:
                # The session's own record (browser version and user agent, the public connection
                # parameters, challenges with their signals, cost snapshot): kept with the run.
                for ev in session.events:
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
                    "INFO" if session.closed_at else "WARN",
                    "BROWSER_CLOSED" if session.closed_at else "BROWSER_CLOSE_FAILED",
                    "cloud browser session closed"
                    if session.closed_at
                    else "the cloud browser did not confirm closing (the provider ends it at its timeout)",
                    {"estimated_credits": round(estimate, 1), "navigations": session.pacer.count},
                )
                s.commit()

    def _store_selected(self) -> bool:
        log = self.selector.log if self.selector else []
        return any(e.get("step") == "confirm_store" and e.get("found") for e in log)

    async def open_session(self, ctx: TaskContext) -> None:
        """A new cloud browser with robots.txt loaded (the store is selected on the first page)."""
        stop = self.limit_stop(opening=True)
        if stop is not None:
            raise RunStop(stop[0], stop[1], resumable=True)
        room, _ = credit_room(self.cfg.limits, self.usage(), self.account_remaining())
        session = BrowserSession(
            self.settings.acquisition, self.storage, self.prefix, provider_key=self.key, max_credits=room
        )
        await session.__aenter__()
        self.session, self.session_opened = session, monotonic()
        self.selector = StoreSelector(session, self.store)
        self.sessions_opened += 1
        policy = await session.load_robots(f"{self.base}/robots.txt")
        entry = self.settings.acquisition.entry_url
        if entry:
            # The configured entry page first, as a visitor arriving at the site would (a challenge or a
            # refusal here stops the run like on any page).
            self.check(ctx)
            await session.navigate(entry, "entry_page", settle_ms=self.LISTING_SETTLE_MS)
            self.steps += 1
        with self.factory() as s:
            run = s.get(Run, self.run_id)
            assert run is not None
            run.robots_sha256 = policy.sha256
            self.persist(s, ctx)
            event(
                s,
                self.run_id,
                "INFO",
                "BROWSER_OPENED",
                "cloud browser session opened; robots.txt loaded",
                {"session": self.sessions_opened, "robots_sha256": policy.sha256},
            )
            s.commit()

    async def select_store(self, ctx: TaskContext, node: Node) -> None:
        """Open ``node`` and, unless it is already priced for the store after a selection in this
        session, select the store with the site's picker and open it again. Stops if it still fails."""
        assert self.session is not None and self.selector is not None
        self.check(ctx)
        fetch = await self.session.navigate(node.url, "listing", settle_ms=self.LISTING_SETTLE_MS)
        self.steps += 1
        v = self.verify(fetch)
        if not v.passed and await self.selector.via_store_picker():
            self.check(ctx)
            fetch = await self.session.navigate(
                node.url, "listing_after_selection", settle_ms=self.LISTING_SETTLE_MS
            )
            self.steps += 1
            v = self.verify(fetch)
        with self.factory() as s:
            self.persist(s, ctx)
            if not v.passed:
                self.attest(s, v, "preflight" if not self._attested(s) else "task_start")
                s.commit()
                raise RunStop(
                    StopCode.STORE_NOT_VERIFIED,
                    "the store could not be selected and verified: "
                    + ("; ".join(v.failures()) or "store context incomplete"),
                    resumable=False,
                )
            if not self._attested(s):
                self.attest(s, v, "preflight")
            s.commit()
        self.ready = (node.url, fetch, v)

    async def ensure_session(self, ctx: TaskContext, node: Node) -> bool:
        """A session with robots.txt, rotated before the provider's timeout, and the store selected.
        Returns False when robots.txt does not allow ``node`` (the caller skips it)."""
        if self.session is not None and self.session_opened is not None:
            limit = self.settings.acquisition.scrapfly.session_timeout_s * ROTATE_SESSION_AFTER
            if monotonic() - self.session_opened > limit:
                await self.close_session()
        if self.session is None:
            await self.open_session(ctx)
        assert self.session is not None and self.session.robots is not None
        if not self.session.robots.allowed(node.url):
            return False
        if not self._store_selected():
            await self.select_store(ctx, node)
        return True

    def verify(self, fetch: PageFetch) -> StoreVerification:
        assert self.session is not None and self.selector is not None
        data = [c for c in fetch.captured if c.kind in ("products_search", "products_v2")]
        order = [f.fetch_id for f in self.session.fetches]
        return verify_store(
            self.store,
            self.settings,
            self.html(fetch),
            fetch_id=fetch.fetch_id,
            purpose=fetch.purpose,
            url=fetch.final_url or fetch.url,
            data_request_urls=[c.url for c in data],
            data_request_headers=[c.request_headers for c in data],
            selected_before=picker_confirmed_before(self.selector.log, order, fetch.fetch_id),
        )

    async def _with_reconnects(self, ctx: TaskContext, work: Callable[[], Awaitable[T]]) -> T:
        """Run ``work`` with failures mapped to stops; when the cloud browser goes away, a new session
        (at most MAX_RECONNECTS per segment) and ``work`` again from the task's checkpoint."""
        while True:
            try:
                return await self._guard(ctx, work())
            except _SessionLost as lost:
                await self.close_session()
                self.reconnects += 1
                with self.factory() as s:
                    event(
                        s,
                        self.run_id,
                        "WARN",
                        "BROWSER_RECONNECT",
                        str(lost)[:300],
                        {"reconnects": self.reconnects},
                    )
                    s.commit()
                if self.reconnects > MAX_RECONNECTS:
                    raise RunStop(
                        StopCode.PROVIDER_ERROR,
                        f"the cloud browser went away {self.reconnects} times; last: {lost}",
                        resumable=True,
                    ) from None

    async def _guard(self, ctx: TaskContext, work: Awaitable[T]) -> T:
        """Browser, site and provider failures as stops (session losses as :class:`_SessionLost`)."""
        try:
            return await work
        except (RunStop, CancelledByOperator, _SessionLost):
            raise
        except ChallengeDetected as exc:
            self._persist_now(ctx)
            raise RunStop(StopCode.SITE_REFUSAL, str(exc)[:500], resumable=False) from None
        except NavigationFailed as exc:
            self._persist_now(ctx)
            side = str(exc.fetch.notes.get("error_side"))
            if side == "provider":
                raise _SessionLost(exc.message) from None
            if side == "client":  # aborted in the browser by the collector itself, never by the site
                s = self.session
                ceiling = s.byte_ceiling if s is not None else None
                if (
                    s is not None
                    and s.meter is not None
                    and ceiling is not None
                    and s.meter.bytes_seen >= ceiling
                ):
                    raise RunStop(
                        self.binding or StopCode.RUN_CREDIT_LIMIT,
                        "the session's traffic ceiling was reached while a page loaded",
                        resumable=True,
                    ) from None
                raise RunStop(
                    StopCode.ABNORMAL_RESULT,
                    f"the collector's own resource policy refused the page: {exc.message}",
                    resumable=False,
                ) from None
            if side == "origin_network":
                raise RunStop(
                    StopCode.SITE_REFUSAL,
                    f"the connection to the site failed: {exc.message}",
                    resumable=False,
                ) from None
            raise RunStop(
                StopCode.PROVIDER_ERROR, f"the page did not load in time: {exc.message}", resumable=True
            ) from None
        except NoDocumentResponse as exc:
            raise RunStop(StopCode.PROVIDER_ERROR, str(exc), resumable=True) from None
        except RobotsUnreachable as exc:
            raise RunStop(StopCode.SITE_REFUSAL, str(exc), resumable=False) from None
        except RobotsDisallowed as exc:
            raise RunStop(StopCode.ABNORMAL_RESULT, str(exc), resumable=False) from None
        except NavigationBudgetExceeded as exc:
            raise RunStop(StopCode.PROVIDER_ERROR, str(exc), resumable=True) from None
        except scrapfly.ProviderError as exc:
            text = scrapfly.redact(str(exc), self.key)[:500]
            if exc.kind is scrapfly.ProviderErrorKind.BUDGET:
                raise RunStop(self.binding or StopCode.RUN_CREDIT_LIMIT, text, resumable=True) from None
            if exc.kind is scrapfly.ProviderErrorKind.AUTH:
                raise RunStop(StopCode.PROVIDER_AUTH, text, resumable=True) from None
            if exc.kind is scrapfly.ProviderErrorKind.QUOTA:
                raise RunStop(StopCode.CREDITS_EXHAUSTED, text, resumable=True) from None
            if exc.kind is scrapfly.ProviderErrorKind.SESSION:
                raise _SessionLost(text) from None
            raise RunStop(StopCode.PROVIDER_ERROR, text, resumable=True) from None
        except AbnormalPage as exc:
            raise RunStop(StopCode.ABNORMAL_RESULT, str(exc), resumable=False) from None

    # -- evidence and records in the database -------------------------------------------------------

    def _artifact(self, s: Session, key: str | None, content_type: str) -> str | None:
        if not key:
            return None
        art = s.scalar(select(Artifact).where(Artifact.key == key))
        if art is None:
            data = self._read(key)
            art = Artifact(
                run_id=self.run_id,
                key=key,
                sha256=hashlib.sha256(data).hexdigest(),
                size=len(data),
                content_type=content_type,
            )
            s.add(art)
            s.flush()
        return art.id

    def _persist_now(self, ctx: TaskContext) -> None:
        with self.factory() as s:
            self.persist(s, ctx)
            s.commit()

    def persist(self, s: Session, ctx: TaskContext) -> None:
        """Page fetches of this session not yet in the database (robots, store picker, pages, steps)."""
        if self.session is None:
            return
        for f in self.session.fetches:
            if f.fetch_id in self.persisted:
                continue
            dom_type = "application/gzip" if (f.dom_key or "").endswith(".gz") else "text/plain"
            shot_type = "image/jpeg" if (f.screenshot_key or "").endswith(".jpg") else "image/png"
            s.add(
                PageFetchRow(
                    id=f.fetch_id,
                    run_id=self.run_id,
                    task_id=ctx.lease.task_id,
                    url=(f.final_url or f.url)[:4000],
                    purpose=f.purpose[:32],
                    http_status=f.status,
                    started_at=datetime.fromisoformat(f.started_at.replace("Z", "+00:00")),
                    duration_ms=f.duration_ms,
                    challenge=f.challenge.is_challenge,
                    dom_artifact_id=self._artifact(s, f.dom_key, dom_type),
                    screenshot_artifact_id=self._artifact(s, f.screenshot_key, shot_type),
                )
            )
            s.flush()
            for c in f.captured:
                if c.kind not in self.CAPTURE_KINDS or not c.artifact_key or not c.body_sha256:
                    continue
                s.add(
                    CapturedRow(
                        run_id=self.run_id,
                        page_fetch_id=f.fetch_id,
                        kind=c.kind,
                        url=c.url[:4000],
                        status=c.status,
                        request_location_id=c.request_location_id,
                        request_taxonomies=list(c.request_taxonomies),
                        body_sha256=c.body_sha256,
                        artifact_id=self._artifact(s, c.artifact_key, "application/gzip"),
                        schema_ok=c.json_ok,
                        observed_at=datetime.fromisoformat(c.observed_at.replace("Z", "+00:00")),
                    )
                )
            self.persisted.add(f.fetch_id)

    def _attested(self, s: Session) -> bool:
        found = s.scalar(select(StoreAttestation.id).where(StoreAttestation.run_id == self.run_id).limit(1))
        return found is not None

    def attest(self, s: Session, v: StoreVerification, phase: str) -> None:
        ctx = v.context
        stores = [x for x in ctx.get("stores") or [] if x.get("location_id") == self.store.location_id]
        details = stores[0] if stores else {}
        checks = [
            {**c, "check": c["name"], "status": "PASS" if c["ok"] else "FAIL" if c["ok"] is False else "N/A"}
            for c in v.as_dict()["checks"]
        ]
        s.add(
            StoreAttestation(
                run_id=self.run_id,
                mode=DataMode.LIVE.value,
                phase=phase,
                observed_location_id=details.get("location_id"),
                observed_name=(ctx.get("header") or {}).get("vanity_name") or details.get("vanity_name"),
                observed_postal_code=details.get("postal_code"),
                modality=ctx.get("active_modality"),
                modality_source=ctx.get("modality_source"),
                is_trusted=None,
                laf_store_id=(ctx.get("laf_store_ids") or [None])[0],
                cms_scope=",".join(ctx.get("cms_scopes") or []),
                result="PASS" if v.passed else "FAIL",
                checks={"fetch_id": v.fetch_id, "url": v.url, "checks": checks},
                evidence_artifact_ids=[],
                observed_at=self.clock(),
            )
        )

    def assign(self, card: CardObservation, node: Node) -> Node | None:
        """The planned listing a card is recorded under: here the listing page it was read on."""
        return node

    def membership(self, card: CardObservation, node: Node, target: Node) -> dict[str, Any]:
        """How the card's listing membership was established (kept in its provenance)."""
        return {}

    def selection_text(self) -> str:
        return "selected with the site's store picker and verified"

    def sponsored_placement(self, card: CardObservation) -> bool:
        """Whether a card the page does not mark as sponsored is nevertheless a sponsored placement (here
        none: the grid marks its sponsored cards, :attr:`ListingView.sponsored`)."""
        return False

    def sponsored_member(self, card: CardObservation, node: Node) -> bool:
        """A sponsored card is a product of the listing when the site's own product data places it there
        (its taxonomy names the listing). Then it is recorded like any card, first placement wins, with its
        placement kept as sponsored; the "Sponsored" label neither excludes it nor makes it a promotion
        (release 1.5.0; until 1.4.0 every sponsored card was skipped, so a product shown only as sponsored
        was never recorded). Without product data saying so it stays a placement only."""
        facts = self.sources.product(card.upc)
        return facts is not None and node.taxonomy_id in facts.taxonomy_ids

    def _structured(self, upc: str | None) -> dict[str, Any]:
        """The site's own data read for a product: its product response and its coupons."""
        product = self.sources.product(upc)
        return {
            "product": product.as_dict() if product is not None else None,
            "coupons": [c.as_dict() for c in self.sources.coupons_for(upc)],
        }

    def placement(
        self,
        s: Session,
        card: CardObservation,
        target: Node,
        fetch: PageFetch,
        step: int,
        observed: datetime,
        *,
        sponsored: bool,
    ) -> None:
        """One placement of a product on a verified page step, kept apart from the record: the listing (and
        so the client's CSV row) it was shown under, the page, its position, the collection segment and the
        observation time. A sponsored placement is kept as ``paid`` (shown there, not a member by the
        listing's own results). Repeating a page step writes nothing new, and neither does a card still on
        the page at a later Load More step: the first step that showed it keeps the placement (release 1.5.0;
        until 1.4.0 every later step added a row)."""
        kind = "sponsored" if sponsored else "organic"
        placed = s.scalar(
            select(MembershipRow.id)
            .where(
                MembershipRow.run_id == self.run_id,
                MembershipRow.upc == card.upc,
                MembershipRow.category_source_id == target.category_source_id,
                MembershipRow.taxonomy_id == target.taxonomy_id,
                MembershipRow.coupon_id.is_(None),
                MembershipRow.placement == kind,
            )
            .limit(1)
        )
        if placed is not None:
            return
        s.execute(
            insert(MembershipRow)
            .values(
                id=new_id(),
                run_id=self.run_id,
                mode=DataMode.LIVE.value,
                upc=card.upc,
                category_source_id=target.category_source_id,
                taxonomy_id=target.taxonomy_id,
                page_offset=step,
                position=card.position,
                via="paid" if sponsored else "organic",
                page_fetch_id=fetch.fetch_id,
                segment_id=self.segment_id,
                observed_at=observed,
                placement=kind,
            )
            .on_conflict_do_nothing()
        )

    def record_step(
        self, s: Session, node: Node, fetch: PageFetch, view: ListingView, state: NodeState, step: int
    ) -> StepResult:
        """Records for the new cards of one verified page step (first placement wins), within the
        product limits. Duplicates are counted, not recorded; a sponsored card is recorded only when its own
        product data places it in the listing (:meth:`sponsored_member`); every placement of a
        product with a UPC is kept in ``memberships`` (release 1.4.0)."""
        res = StepResult()
        details, header, _ = page_store(self.html(fetch), self.store)
        if details is None:
            raise RunStop(
                StopCode.STORE_NOT_VERIFIED, f"{node.url}: no store details on the page", resumable=False
            )
        sf = store_fields(details, header)
        observed = datetime.fromisoformat(fetch.started_at.replace("Z", "+00:00"))
        observed_iso = iso(observed)
        crawl_date = store_local_date(observed, self.store.timezone)
        state_src = FieldSource(
            "state", "modalityPreferences.storeDetails", fetch.fetch_id, None, observed_iso
        )
        provenance = {"zipcode": state_src, "store_name": state_src, "store_location": state_src}
        steps = after_store_confirmed(self.session.fetches) if self.session is not None else []
        for f in [*steps, fetch]:
            if f.fetch_id not in self.indexed:
                index_captures(self.sources, f, self._read)
                self.indexed.add(f.fetch_id)
        seen = set(state.seen)
        room = product_room(self.cfg.limits, self.usage())
        for card in view.cards:
            if not card.upc:
                res.without_upc += 1
                continue
            sponsored = card.card_testid in view.sponsored or self.sponsored_placement(card)
            if card.card_testid in view.sponsored:
                res.sponsored += 1
                if not self.sponsored_member(card, node):
                    # An advertisement for a product of another listing: its placement is kept, not a record.
                    res.sponsored_elsewhere += 1
                    self.placement(s, card, node, fetch, step, observed, sponsored=True)
                    continue
            target = self.assign(card, node)
            if target is None:
                res.off_plan += 1
                continue
            own = target.taxonomy_id == node.taxonomy_id
            new_here = own and card.upc not in seen
            if card.upc in self.recorded:
                res.duplicates += 1
                self.placement(s, card, target, fetch, step, observed, sponsored=sponsored)
                if new_here:
                    seen.add(card.upc)
                    state.seen.append(card.upc)
                    res.new_cards += 1
                continue
            cb = build_card(
                card,
                fetch_id=fetch.fetch_id,
                observed_at=observed_iso,
                store=self.store,
                store_values=sf,
                store_provenance=provenance,
                category=CategoryAssignment(target.category, target.sub_category),
                crawl_date=crawl_date,
                settings=self.settings,
                detector=self.pipe.detector,
                sources=self.sources,
            )
            built = cb.built
            if target.kind == "row_listing" and "sub_category" in built.missing:
                built = replace(
                    built,
                    missing={
                        **built.missing,
                        "sub_category": "the client's CSV row is itself the listing page (no subcategory)",
                    },
                )
            verified = built.status is RecordStatus.VALID
            if verified and room is not None and room <= 0:
                # The product limit is reached: this card and the rest of the step wait for a resume.
                res.capped = product_limit_code(self.cfg.limits, self.usage()) or StopCode.RUN_PRODUCT_LIMIT
                break
            if new_here:
                seen.add(card.upc)
                state.seen.append(card.upc)
                res.new_cards += 1
            self.placement(s, card, target, fetch, step, observed, sponsored=sponsored)
            s.execute(
                insert(ProductObservation)
                .values(
                    id=new_id(),
                    run_id=self.run_id,
                    mode=DataMode.LIVE.value,
                    upc=card.upc,
                    page_fetch_id=fetch.fetch_id,
                    source="card",
                    displayed=card_to_dict(card),
                    structured=self._structured(card.upc),
                    provenance={
                        "verified": verified,
                        "node": target.taxonomy_id,
                        # A child listing read because its listing is larger than the site's result window:
                        # the client's listing it stands for.
                        **({"parent": target.parent} if target.parent else {}),
                        **({"read_on": node.taxonomy_id} if not own else {}),
                        **self.membership(card, node, target),
                        "category": target.category,
                        "sub_category": target.sub_category,
                        "step": step,
                        "position": card.position,
                        "store_check": "PASS",
                        # Which collection segment and browser session saw the card: a resumed run's
                        # earlier records are carried forward, not observed again.
                        "segment": self.segment_id,
                        "session": self.sessions_opened,
                        "fields": built.provenance,
                        "missing": built.missing,
                        "missing_kind": built.missing_kind,
                        "source_check": built.source_check,
                        "offers": offer_summaries(built, self.settings),
                    },
                    flags=list(card.flags),
                    parser_version=PARSER_VERSION,
                    observed_at=observed,
                )
                .on_conflict_do_nothing(constraint="uq_product_observations_key")
            )
            s.execute(
                insert(RecordRow)
                .values(
                    id=new_id(),
                    run_id=self.run_id,
                    mode=DataMode.LIVE.value,
                    upc=card.upc,
                    record=built.record,
                    record_sha256=record_sha256(built.record),
                    primary_category_source_id=target.category_source_id,
                    status=built.status.value,
                    reasons=[r.value for r in built.reasons],
                    flags=[f.value for f in built.flags],
                )
                .on_conflict_do_nothing(constraint="uq_records_run_upc")
            )
            for c in built.deals.classified:
                s.add(
                    OfferObservationRow(
                        run_id=self.run_id,
                        mode=DataMode.LIVE.value,
                        upc=card.upc,
                        page_fetch_id=fetch.fetch_id,
                        source=c.offer.source.value,
                        tag=c.offer.tag,
                        headline=c.offer.text,
                        description=format_description(
                            c.offer, self.settings.records.deal_description_format
                        ),
                        expiry_text=c.offer.expiry_text,
                        requires_clip=c.requires_clip,
                        kind=c.kind.value,
                        explicit_price=c.explicit_price,
                        modalities=sorted(c.restricted_to) if c.restricted_to else [],
                        flags=[f.value for f in c.flags],
                    )
                )
            self.recorded.add(card.upc)
            res.new_records += 1
            res.excluded += built.status is RecordStatus.EXCLUDED
            res.conflicts += built.status is RecordStatus.PRICE_CONFLICT
            if not own:
                res.other_listing += 1
            if verified:
                res.new_verified += 1
                if room is not None:
                    room -= 1
        return res

    def page_recorded(self, s: Session, node: Node, fetch: PageFetch, res: StepResult) -> None:
        """Called inside the transaction that records a page step's products (browser steps keep no page row:
        one document grows through its Load More clicks)."""

    def coverage(self, s: Session, node: Node, state: NodeState) -> None:
        organic = len(state.seen)
        total = state.total
        ratio = 1.0 if total == 0 else (min(1.0, organic / total) if total else None)
        values = {
            "total_count": total,
            "organic_upcs": organic,
            "coverage_ratio": ratio,
            "status": state.status,
            "partition": {
                "url": node.url,
                "steps": state.steps_done,
                "reason": state.reason,
                "available": state.available,
                "parent": node.parent or None,
                "partitions": state.partitions,
                **({"read": state.extra} if state.extra else {}),
            },
        }
        s.execute(
            insert(NodeCoverage)
            .values(
                id=new_id(),
                run_id=self.run_id,
                category_source_id=node.category_source_id,
                taxonomy_id=node.taxonomy_id,
                **values,
            )
            .on_conflict_do_update(constraint="uq_node_coverage_key", set_=values)
        )

    def _contract(self, s: Session, problem: str | None) -> None:
        run = s.get(Run, self.run_id)
        assert run is not None
        contract = dict((run.counts or {}).get("contract") or {"pages": 0, "problems": []})
        contract["pages"] = int(contract.get("pages", 0)) + 1
        if problem:
            contract["problems"] = [*contract.get("problems", []), problem][-20:]
        run.counts = {**(run.counts or {}), "contract": contract}

    # -- handlers ---------------------------------------------------------------------------------

    async def h_preflight(self, ctx: TaskContext) -> dict[str, Any]:
        """Robots.txt and the store selection, verified on the first listing page robots.txt allows."""
        if not self.plan:
            raise RunStop(
                StopCode.NOTHING_TO_COLLECT, "the run has no listing page to visit", resumable=False
            )
        self.check(ctx)

        async def select() -> str | None:
            for node in self.plan:
                if await self.ensure_session(ctx, node):
                    if self.ready is None:
                        # The store was selected earlier in this browser session (a task taken over after its
                        # lease ran out): open the page again and verify it before collection starts.
                        await self.select_store(ctx, node)
                    return node.url
            return None

        async with self.keepalive(ctx):
            url = await self._with_reconnects(ctx, select)
        if url is None:
            raise RunStop(
                StopCode.NOTHING_TO_COLLECT,
                "robots.txt allows none of the planned listing pages",
                resumable=False,
            )
        if self.ready is None:
            raise RunStop(
                StopCode.STORE_NOT_VERIFIED,
                "the store selection left no verified listing page",
                resumable=False,
            )
        _, fetch, _ = self.ready
        _, _, site_version = page_store(self.html(fetch), self.store)
        with self.factory() as s:
            run = s.get(Run, self.run_id)
            assert run is not None
            run.site_version = site_version
            event(
                s,
                self.run_id,
                "INFO",
                "STORE_VERIFIED",
                f"{self.store.expected.display_name} {self.selection_text()}",
                {"url": url},
            )
            if run.status == "preflight":
                transition(s, self.run_id, "running")
            s.commit()
        return {**ctx.cursor, "verified_on": url}

    async def h_listing(self, ctx: TaskContext) -> dict[str, Any]:
        node = Node.from_dict(ctx.cursor["node"])
        if NodeState.from_cursor(ctx.cursor).status in FINISHED_NODE:
            return dict(ctx.cursor)
        self.check(ctx)
        async with self.keepalive(ctx):
            return await self._with_reconnects(
                ctx, lambda: self.collect_node(ctx, node, NodeState.from_cursor(ctx.cursor))
            )

    @contextlib.asynccontextmanager
    async def keepalive(self, ctx: TaskContext) -> AsyncIterator[None]:
        """Renew the task's lease every :data:`KEEPALIVE_S` while the handler works, so a long page load or
        store selection never lets another worker take the task over (a lost lease would stop the run)."""

        async def renew() -> None:
            while True:
                await asyncio.sleep(KEEPALIVE_S)
                with contextlib.suppress(
                    Exception
                ):  # a lease already lost is reported by the next checkpoint
                    ctx.heartbeat()

        task = asyncio.create_task(renew())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                # The helper's own cancellation is expected; a cancellation of this task must go on.
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise

    async def collect_node(self, ctx: TaskContext, node: Node, state: NodeState) -> dict[str, Any]:
        if not await self.ensure_session(ctx, node):
            state.status, state.reason = "SKIPPED", "robots.txt does not allow this listing page"
            return self._finish_node(node, state)
        assert self.session is not None
        if self.ready is not None and self.ready[0] == node.url:
            _, fetch, v = self.ready
            self.ready = None
        else:
            self.check(ctx)
            fetch = await self.session.navigate(node.url, "listing", settle_ms=self.LISTING_SETTLE_MS)
            self.steps += 1
            v = self.verify(fetch)
        view = self._view(fetch)
        replay_until = state.steps_done
        state.last_offset = -1  # the page starts again from its first products
        step = 0
        self._step(ctx, node, fetch, v, view, state, step, replay=False, first=True)
        if (
            state.status == "IN_PROGRESS"
            and self.settings.coverage.partition_large_listings
            and state.total is not None
            and state.available is not None
            and state.total > state.available
            and view.children
        ):
            # The page cannot reach every result: the products of this first page are kept and the rest is
            # read through the child listings the site names (each a task of its own, checked as usual).
            self._partition(ctx, node, state, view.children)
            return self._finish_node(node, state)
        while state.status == "IN_PROGRESS":
            if step >= replay_until:
                state.steps_done = step
                ctx.checkpoint(state.cursor(node))
            if not await self._load_more_visible():
                # The last page, unless the site reports more results than its search lets the page reach.
                # The end of a listing is its count, never its last page (release 1.8.0).
                window = window_reason(state.total, state.available, len(state.seen))
                short = (
                    f"{pagination.GAP}: {len(state.seen)} distinct products of {state.total} reported"
                    if state.total is not None and len(state.seen) < state.total
                    else ""
                )
                state.status = "INCOMPLETE" if window or short else "DONE"
                state.reason = window or short
                break
            page_limit = self.cfg.limits.max_pages_per_listing
            if page_limit is not None and step + 1 >= page_limit:
                state.status = "INCOMPLETE"
                state.reason = f"stopped at the page limit ({page_limit} page steps per listing)"
                break
            if step >= max_steps(state.total):
                state.status = "INCOMPLETE"
                state.reason = f"stopped after {step} Load More steps (more than the page's total allows)"
                break
            self.check(ctx)
            fetch = await self._load_more(len(view.cards))
            self.steps += 1
            result = fetch.notes.get("result") or {}
            if result.get("clicked") is False:
                # The page copy of the failed step is kept as evidence; the listing stays incomplete.
                self._persist_now(ctx)
                if result.get("challenge"):
                    raise RunStop(
                        StopCode.SITE_REFUSAL,
                        "a challenge covered the Load More button (not clicked through): "
                        + ", ".join(result["challenge"]),
                        resumable=False,
                    )
                state.status = "INCOMPLETE"
                state.reason = (
                    "the Load More button could not be clicked: "
                    + "; ".join(result.get("click_problems") or [])[:600]
                )
                break
            step += 1
            v = self.verify(fetch)
            view = self._view(fetch)
            self._step(ctx, node, fetch, v, view, state, step, replay=step <= replay_until)
        state.steps_done = max(state.steps_done, step)
        return self._finish_node(node, state)

    def _partition(
        self, ctx: TaskContext, node: Node, state: NodeState, children: list[dict[str, Any]]
    ) -> None:
        """Plan the child listings of ``node`` as listing tasks of this run (idempotent per child)."""
        planned: list[dict[str, Any]] = []
        with self.factory() as s:
            task = s.get(Task, ctx.lease.task_id)
            priority = task.priority if task is not None else 50
            for ch in children:
                url = ch.get("url") or f"{base_of(node.url)}/pl/{ch['slug']}/{ch['id']}?pzn=relevance"
                entry = {"id": ch["id"], "name": ch["name"], "count": ch["count"], "url": url}
                if ch["count"] == 0:
                    planned.append({**entry, "task": None, "note": "the site reports 0 results: not read"})
                    continue
                child = replace(
                    node,
                    taxonomy_id=ch["id"],
                    url=url,
                    kind="partition",
                    parent=node.taxonomy_id,
                    partition_name=ch["name"],
                    partition_count=ch["count"],
                )
                key = f"{ctx.lease.idem_key}/{ch['id']}"
                queue.enqueue(
                    s,
                    self.run_id,
                    "listing_node",
                    key,
                    priority=priority,
                    category_source_id=node.category_source_id,
                    taxonomy_id=ch["id"][:10],
                    cursor={"node": child.as_dict(), "steps_done": 0, "seen": [], "status": "IN_PROGRESS"},
                )
                planned.append({**entry, "task": key})
            event(
                s,
                self.run_id,
                "INFO",
                "LISTING_PARTITIONED",
                f"{node.category} › {node.sub_category}: {state.total} results, {state.available} reachable; "
                f"read through {sum(1 for p in planned if p['task'])} child listings",
                {
                    "node": node.taxonomy_id,
                    "total": state.total,
                    "available": state.available,
                    "partitions": planned,
                },
            )
            s.commit()
        state.status, state.partitions = "PARTITIONED", planned
        state.reason = (
            f"the site's search lets the page reach {state.available} of the {state.total} results; the "
            f"listing is read through {len(planned)} subdivisions the page itself names "
            f"({', '.join(p['name'] for p in planned)[:400]}) and is complete only when they cover its "
            "results"
        )

    def _view(self, fetch: PageFetch) -> ListingView:
        grid, cards, sponsored, total = grid_cards(self.html(fetch))
        return ListingView(grid, cards, sponsored, total, search_requests(fetch.captured, self._read))

    def _step(
        self,
        ctx: TaskContext,
        node: Node,
        fetch: PageFetch,
        v: StoreVerification,
        view: ListingView,
        state: NodeState,
        step: int,
        *,
        replay: bool,
        first: bool = False,
    ) -> None:
        """Check one page step and record its products, or close the node (or the run) with the reason."""
        fatal: str | None = None
        problem: str | None = None
        if first:
            if not view.cards and (view.displayed_total == 0 or view.total == 0):
                state.total, state.status, state.reason = 0, "EMPTY", "the page shows 0 results"
            elif not view.cards:
                fatal = "the listing page shows no products (no product grid or no product cards)"
            elif view.total is None:
                problem = f"{node.url}: no result count on the page or in its product request"
        with self.factory() as s:
            self.persist(s, ctx)
            self.attest(s, v, "task_start" if first else "periodic")
            self._contract(s, fatal or problem)
            if not v.passed:
                s.commit()
                raise RunStop(
                    StopCode.STORE_NOT_VERIFIED,
                    f"{fetch.final_url or fetch.url}: "
                    + ("; ".join(v.failures()) or "store context incomplete"),
                    resumable=False,
                )
            if fatal is not None:
                s.commit()
                raise AbnormalPage(f"{node.url}: {fatal}")
            if state.status == "EMPTY":
                self.coverage(s, node, state)
                s.commit()
                return
            offsets = [x["offset"] for x in view.searches if isinstance(x.get("offset"), int)]
            if view.available is not None:
                state.available = view.available
            if first:
                state.total = view.total
            elif (
                not offsets
                or max(offsets) <= state.last_offset
                or {x.get("location_id") for x in view.searches} != {self.store.location_id}
            ):
                state.status = "INCOMPLETE"
                state.reason = (
                    "a Load More step showed no product request for a later page at the configured store; "
                    "its products were not counted"
                )
                self.coverage(s, node, state)
                s.commit()
                return
            if offsets:
                state.last_offset = max(state.last_offset, max(offsets))
            res = self.record_step(s, node, fetch, view, state, step)
            # In this transaction: the page's progress can never differ from its products.
            self.page_recorded(s, node, fetch, res)
            if not first and not replay and res.new_cards == 0 and res.capped is None:
                state.status, state.reason = "INCOMPLETE", "a Load More step showed no new products"
            self.coverage(s, node, state)
            self.heartbeat(s)
            click = fetch.notes.get("result") if fetch.purpose == "load_more" else None
            event(
                s,
                self.run_id,
                "INFO",
                "PAGE_COLLECTED",
                f"{node.category} › {node.sub_category}: page step {step}",
                {
                    "node": node.taxonomy_id,
                    "step": step,
                    "cards": len(view.cards),
                    "new_cards": res.new_cards,
                    "new_records": res.new_records,
                    "new_verified": res.new_verified,
                    "duplicates": res.duplicates,
                    "sponsored": res.sponsored,
                    "sponsored_elsewhere": res.sponsored_elsewhere,
                    "other_listing": res.other_listing,
                    "off_plan": res.off_plan,
                    "total": state.total,
                    "seen": len(state.seen),
                    "replay": replay,
                    # How the Load More button was clicked when the plain click did not work.
                    **(
                        {"click_via": click.get("via"), "click_problems": click.get("click_problems")}
                        if isinstance(click, dict) and click.get("click_problems")
                        else {}
                    ),
                },
            )
            s.commit()
        if not replay and res.new_records > 0:
            self.canary(fetch)
        if res.capped is not None:
            usage, limits = self.usage(), self.cfg.limits
            detail = (
                f"{usage.run_products} verified products in this run (limit {limits.max_products_per_run})"
                if res.capped is StopCode.RUN_PRODUCT_LIMIT
                else f"{usage.day_products} verified products today (limit {limits.max_products_per_day})"
            )
            raise RunStop(res.capped, detail, resumable=True)

    # -- automated canary -------------------------------------------------------------------------

    def canary_checks(self, fetch: PageFetch) -> tuple[bool, dict[str, Any]]:
        """The first recorded page step's records checked automatically: enough valid records, required
        fields filled, prices in two-decimal form, and the valid records compared with the site's own
        product data for the store, read independently of the collector's parser
        (:mod:`marianos_headless.checks.source_check`): none may differ, and at least
        ``min_source_verified_ratio`` of them must be found in that data."""
        cfg = self.canary_cfg
        with self.factory() as s:
            rows = list(
                s.scalars(
                    select(RecordRow)
                    .join(
                        ProductObservation,
                        (ProductObservation.run_id == RecordRow.run_id)
                        & (ProductObservation.upc == RecordRow.upc),
                    )
                    .where(
                        RecordRow.run_id == self.run_id, ProductObservation.page_fetch_id == fetch.fetch_id
                    )
                )
            )
        valid = [r for r in rows if r.status == RecordStatus.VALID.value]
        problems: list[str] = []
        if len(valid) < cfg.min_valid_records:
            problems.append(
                f"{len(valid)} valid records on the first page step (at least {cfg.min_valid_records})"
            )
        ratio = len(valid) / len(rows) if rows else 0.0
        if rows and ratio < cfg.min_valid_ratio:
            problems.append(
                f"{ratio:.0%} of the step's records are valid (at least {cfg.min_valid_ratio:.0%})"
            )
        missing: dict[str, int] = {}
        bad_prices = 0
        # A CSV row that is itself a listing page has no subcategory: it is not required there.
        row_listings = {n.category for n in self.plan if n.kind == "row_listing"}
        for r in valid:
            for name in cfg.required_fields:
                if name == "sub_category" and r.record.get("category") in row_listings:
                    continue
                if not str(r.record.get(name) or "").strip():
                    missing[name] = missing.get(name, 0) + 1
            for name in ("regular_price", "sale_price"):
                value = str(r.record.get(name) or "")
                if value and not re.fullmatch(r"\d+\.\d{2}", value):
                    bad_prices += 1
        if missing:
            problems.append(f"required fields empty in valid records: {missing}")
        if bad_prices:
            problems.append(f"{bad_prices} prices not in two-decimal form")
        source: dict[str, Any] = {"records": 0, "verified": 0, "mismatch": 0, "unverified": 0}
        if cfg.source_check and valid:
            bodies = []
            for key in self.storage.list(f"{self.prefix}/raw/"):
                if key.endswith(".products_v2.json.gz"):
                    with contextlib.suppress(OSError, KeyError, EOFError):
                        bodies.append(gzip.decompress(self._read(key)))
            products = source_check.index(bodies)
            source = source_check.check_records([r.record for r in valid], products, self.store.location_id)[
                "summary"
            ]
            share = source["verified"] / len(valid)
            if source["mismatch"]:
                problems.append(f"{source['mismatch']} valid records differ from the site's product data")
            if share < cfg.min_source_verified_ratio:
                problems.append(
                    f"only {source['verified']} of {len(valid)} valid records found in the site's product "
                    f"data (at least {cfg.min_source_verified_ratio:.0%})"
                )
        summary = {
            "page": fetch.fetch_id,
            "url": fetch.final_url or fetch.url,
            "records": len(rows),
            "valid": len(valid),
            "valid_ratio": round(ratio, 3),
            "source_check": source,
            "problems": problems,
        }
        return not problems, summary

    def canary(self, fetch: PageFetch) -> None:
        """After the first page step that recorded products: continue only when its automated checks pass;
        otherwise stop the run (not resumable) with the reasons."""
        if not self.canary_cfg.enabled or self.canary_done:
            return
        passed, summary = self.canary_checks(fetch)
        self.canary_done = passed
        with self.factory() as s:
            run = s.get(Run, self.run_id)
            assert run is not None
            run.counts = {
                **(run.counts or {}),
                "canary": {"status": "passed" if passed else "failed", "at": iso(self.clock()), **summary},
            }
            event(
                s,
                self.run_id,
                "INFO" if passed else "WARN",
                "CANARY_PASSED" if passed else "CANARY_FAILED",
                "first recorded page step passed the automated checks: collection continues"
                if passed
                else "first recorded page step failed the automated checks: "
                + "; ".join(summary["problems"]),
                summary,
            )
            s.commit()
        if not passed:
            raise RunStop(
                StopCode.CANARY_CHECK_FAILED, "; ".join(summary["problems"])[:2000], resumable=False
            )

    def _finish_node(self, node: Node, state: NodeState) -> dict[str, Any]:
        with self.factory() as s:
            self.coverage(s, node, state)
            total = state.total if state.total is not None else "?"
            event(
                s,
                self.run_id,
                "INFO" if state.status in ("DONE", "EMPTY") else "WARN",
                f"NODE_{state.status}",
                f"{node.category} › {node.sub_category}: {len(state.seen)} of {total} products"
                + (f" ({state.reason})" if state.reason else ""),
                {"node": node.taxonomy_id, "steps": state.steps_done},
            )
            s.commit()
        return state.cursor(node)

    async def _load_more_visible(self) -> bool:
        assert self.session is not None and self.session.page is not None
        loc = self.session.page.locator(LOAD_MORE_CSS)
        try:
            if not await asyncio.wait_for(loc.count(), 15):
                return False
            first = loc.first
            return bool(
                await asyncio.wait_for(first.is_visible(), 15)
                and await asyncio.wait_for(first.is_enabled(), 15)
            )
        except TimeoutError:
            raise _SessionLost("the cloud browser did not answer within 15 s") from None

    async def _load_more(self, before: int) -> PageFetch:
        assert self.session is not None

        async def click(page: Page) -> dict[str, Any]:
            btn = page.locator(LOAD_MORE_CSS).first
            problems: list[str] = []
            via = "pointer"
            try:
                await btn.scroll_into_view_if_needed(timeout=10_000)
                await btn.click(timeout=10_000)
            except PlaywrightError as exc:
                # Something covers the button (live 2026-10-23: a click that timed out on a visible,
                # enabled button), or it moved. A challenge is never clicked through: the page is checked
                # first, and a challenge leaves the step unclicked (the step's own check then stops the run).
                # Otherwise Escape closes what it closes; then the button is clicked once more, and last
                # through the page itself (the site's own handler runs either way).
                problems.append(click_problem(exc))
                via = ""
                blocker = await obstruction_challenge(page)
                if blocker:
                    return {
                        "clicked": False,
                        "click_problems": problems,
                        "challenge": blocker,
                        "cards_before": before,
                        "grew": False,
                    }
                with contextlib.suppress(PlaywrightError):
                    await page.keyboard.press("Escape")
                try:
                    await btn.click(timeout=5_000)
                    via = "pointer_after_escape"
                except PlaywrightError as again:
                    problems.append(click_problem(again))
                    try:
                        await btn.dispatch_event("click", timeout=5_000)
                        via = "dom_click"
                    except PlaywrightError as last:
                        problems.append(click_problem(last))
            if not via:
                return {"clicked": False, "click_problems": problems, "cards_before": before, "grew": False}
            try:
                await page.wait_for_function(CARDS_GREW_JS, arg=before, timeout=25_000)
                grew = True
            except Exception:
                grew = False
            return {
                "clicked": "Load More Results",
                "via": via,
                **({"click_problems": problems} if problems else {}),
                "cards_before": before,
                "grew": grew,
            }

        # The page copy of every step is kept (the records come from it); a picture only of the first page.
        return await self.session.act("load_more", click, settle_ms=self.STEP_SETTLE_MS, screenshot=False)

    # -- assemble / validate ----------------------------------------------------------------------

    def prior_good(self, s: Session) -> dict[str, int]:
        """Valid records per category of the store's last successful complete run (abnormal yield, G4)."""
        last = s.scalar(
            select(Run.id)
            .where(
                Run.store_id == self.store_id,
                Run.id != self.run_id,
                Run.status.in_(("validated", "published")),
                Run.mode == DataMode.LIVE.value,
            )
            .order_by(Run.created_at.desc())
            .limit(1)
        )
        if last is None:
            return {}
        out: dict[str, int] = {}
        for r in s.scalars(
            select(RecordRow).where(RecordRow.run_id == last, RecordRow.status == RecordStatus.VALID.value)
        ):
            cat = str(r.record.get("category", ""))
            out[cat] = out.get(cat, 0) + 1
        return out

    def node_outcomes(self, s: Session) -> list[dict[str, Any]]:
        return reconciliation.node_outcomes(s, self.run_id)

    async def h_assemble(self, ctx: TaskContext) -> dict[str, Any]:
        with ctx.session() as s:
            run = s.get(Run, self.run_id)
            assert run is not None
            nodes = self.node_outcomes(s)
            complete = bool(nodes) and all(n["status"] in ("DONE", "EMPTY") for n in nodes)
            # The store's products verified by earlier runs and not observed by this one (retention.py).
            cfg = self.historical_cfg
            kept = (
                retention.carry_forward(
                    s,
                    self.run_id,
                    self.store_id,
                    self.clock(),
                    max_age_days=cfg.max_age_days,
                    run_complete=complete,
                )
                if cfg.enabled
                else {"carried_forward": 0, "too_old": 0}
            )
            run.counts = {**(run.counts or {}), "historical": kept}
            if any(kept.values()):
                event(
                    s,
                    self.run_id,
                    "INFO",
                    "HISTORICAL_OBSERVATIONS",
                    f"{kept['carried_forward']} products verified by earlier runs and not observed by this "
                    "run carried forward unchanged (each with its own crawl date)",
                    kept,
                )
            statuses = {
                str(k): int(v)
                for k, v in s.execute(
                    select(RecordRow.status, func.count())
                    .where(RecordRow.run_id == self.run_id)
                    .group_by(RecordRow.status)
                ).all()
            }
            by_status: dict[str, int] = {}
            for n in nodes:
                by_status[n["status"]] = by_status.get(n["status"], 0) + 1
            run.counts = {
                **(run.counts or {}),
                "records_by_status": statuses,
                "verified": verified_in_run(s, self.run_id),
                "nodes": by_status,
                "collection_complete": complete,
            }
            event(
                s,
                self.run_id,
                "INFO",
                "RECORDS_ASSEMBLED",
                f"{sum(statuses.values())} products ({statuses.get('valid', 0)} verified)"
                + ("" if complete else "; collection incomplete"),
                {"records_by_status": statuses, "collection_complete": complete},
            )
            s.commit()
        return {**ctx.cursor, "collection_complete": complete}

    async def h_validate(self, ctx: TaskContext) -> dict[str, Any]:
        with ctx.session() as s:
            run = s.get(Run, self.run_id)
            assert run is not None
            last = s.scalars(
                select(StoreAttestation)
                .where(StoreAttestation.run_id == self.run_id)
                .order_by(StoreAttestation.created_at.desc(), StoreAttestation.id.desc())
                .limit(1)
            ).first()
            if last is not None:  # the final attestation repeats the last page the collector checked
                s.add(
                    StoreAttestation(
                        run_id=self.run_id,
                        mode=last.mode,
                        phase="final",
                        observed_location_id=last.observed_location_id,
                        observed_name=last.observed_name,
                        observed_postal_code=last.observed_postal_code,
                        modality=last.modality,
                        modality_source=last.modality_source,
                        is_trusted=last.is_trusted,
                        laf_store_id=last.laf_store_id,
                        cms_scope=last.cms_scope,
                        result=last.result,
                        checks=last.checks,
                        evidence_artifact_ids=last.evidence_artifact_ids,
                        observed_at=last.observed_at,
                    )
                )
                s.flush()
            tasks_terminal, artifacts_ok, records_ok = self.pipe.integrity(s, self.run_id)
            atts = [
                AttestationSummary(
                    a.phase,
                    a.result == "PASS",
                    tuple(
                        c["check"] for c in (a.checks or {}).get("checks", []) if c.get("status") == "FAIL"
                    ),
                )
                for a in s.scalars(select(StoreAttestation).where(StoreAttestation.run_id == self.run_id))
            ]
            recs = list(s.scalars(select(RecordRow).where(RecordRow.run_id == self.run_id)))
            exported_rows = [r for r in recs if r.status in EXPORTED_RECORD_STATUSES]
            exported = [ordered_record(r.record) for r in exported_rows]
            names = {c.id: c.category_name for c in s.scalars(select(CategorySource))}
            valid_by_cat: dict[str, int] = {}
            for r in recs:
                if r.status == RecordStatus.VALID.value:
                    cat = str(r.record.get("category", ""))
                    valid_by_cat[cat] = valid_by_cat.get(cat, 0) + 1
            per_cat: dict[str, dict[str, Any]] = {}
            for n in self.node_outcomes(s):
                node = n["node"]
                cat = names.get(node.get("category_source_id", ""), node.get("category", ""))
                entry = per_cat.setdefault(
                    cat, {"statuses": [], "coverage": {}, "row": node.get("row_index", -1)}
                )
                entry["statuses"].append(n["status"])
                total = n["total"]
                entry["coverage"][str(node.get("taxonomy_id"))] = (
                    1.0 if total == 0 else (min(1.0, n["seen"] / total) if total else 0.0)
                )
            # Abnormal yield (G4): each category's fresh verified products against the store's last
            # successful complete run (carried-forward products do not count); a bounded (pilot) run is not
            # compared.
            prior = {} if (run.config_snapshot or {}).get("pilot") else self.prior_good(s)
            cats = [
                CategoryOutcome(
                    int(e["row"]),
                    cat,
                    "DONE" if all(st in ("DONE", "EMPTY") for st in e["statuses"]) else "INCOMPLETE",
                    valid_by_cat.get(cat, 0),
                    prior.get(cat),
                    zero_rule_holds=all(st == "EMPTY" for st in e["statuses"]),
                    node_coverage=e["coverage"],
                )
                for cat, e in per_cat.items()
            ]
            contract = (run.counts or {}).get("contract") or {}
            challenges = s.scalar(
                select(func.count())
                .select_from(PageFetchRow)
                .where(PageFetchRow.run_id == self.run_id, PageFetchRow.challenge.is_(True))
            )
            evidence = RunEvidence(
                mode=DataMode.LIVE,
                attestations=atts,
                challenges_detected=int(challenges or 0),
                categories=cats,
                exported_records=exported,
                exported_keys=[r.upc for r in exported_rows],
                valid_upcs=frozenset(r.upc for r in recs if r.status == RecordStatus.VALID.value),
                required_fields=self.REQUIRED_FIELDS,
                contract_canary_ok=bool(contract.get("pages")) and not contract.get("problems"),
                tasks_all_terminal=tasks_terminal,
                artifact_hashes_verified=artifacts_ok,
                manifest_complete=records_ok,
            )
            outcome = run_gates(evidence, self.settings)
            transition(s, self.run_id, "validating")
            status = record_validation(s, self.run_id, outcome, apply_status=False)
            run.counts = {
                **(run.counts or {}),
                "gates": {r.gate: r.status.value for r in outcome.results},
                "completeness": field_completeness(exported),
                "outcome": status,
            }
            event(s, self.run_id, "INFO", "CHECKS_COMPLETE", status, run.counts["gates"])
            s.commit()
        return {**ctx.cursor, "status": status}
