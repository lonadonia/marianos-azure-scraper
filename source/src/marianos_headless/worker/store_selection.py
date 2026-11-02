"""Selecting and checking the configured Mariano's store in a Scrapfly cloud browser session.

:class:`StoreSelector` selects the store with the site's own store and fulfillment picker (as recorded
live on 2026-10-20); :func:`verify_store` checks every page against the configured store before any
price is trusted: location ID, name, address, ZIP, fulfillment, an explicit selection in this session,
and the store of every data request the page made. A refusal from the site (HTTP 403/429, a challenge or
CAPTCHA page) or an abnormal empty page stops the run with its evidence; nothing is retried with another
identity. (Kept from the application's provider pilot module; its pilot stages are not part of this
collector.)
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Locator, Page
from selectolax.lexbor import LexborHTMLParser

from marianos_headless.acquisition.browser import (
    BrowserSession,
)
from marianos_headless.core.settings import Settings, StoreConfig
from marianos_headless.core.text import collapse_ws
from marianos_headless.sites.marianos.dom_parsers import (
    DEFAULT_SELECTORS,
    HeaderStore,
    parse_header_store,
    text_of,
)
from marianos_headless.sites.marianos.initial_state import InitialStateNotFound, parse_initial_state
from marianos_headless.sites.marianos.store_context import (
    AttestationObservation,
    StoreContext,
    attest,
    request_location_id,
    store_context_from_state,
)

BASE = "https://www.marianos.com"
DEFAULT_LISTINGS: tuple[tuple[str, str], ...] = (
    ("Grocery", "Canned Foods"),
    ("Dairy", "Milk & Plant-based Milk"),
    ("Frozen", "Frozen Pizza"),
    ("Beverages", "Soda & Pop"),
    ("Breakfast", "Cereal & Granola"),
    ("Candy", "Chocolate"),
)
# Card roots: carousel cards (confirmed on the saved homepage) and grid cards (not yet confirmed).
LISTING_SELECTORS = replace(
    DEFAULT_SELECTORS,
    card_root='[data-testid^="carousel-product-card-"], [data-testid^="product-card-"], '
    '[data-testid^="mini-product-card-"]',
)
PICKER_CSS = 'dialog[data-testid="ModalitySelectorModal"]'  # the store/fulfillment picker (live, 2026-10-20)
CTA_PATTERNS = (
    r"\b(make|set)\b.{0,24}\bmy store\b",
    r"\bshop (this|at this) store\b",
    r"\bstart shopping\b",
    r"\b(select|choose) (this )?store\b",
)
_PRODUCT_HREF = re.compile(r'href="([^"]*/p/[^"]+)"')
# Dotted quads, except product version tokens such as Chrome/155.0.0.0 (not addresses).
_IPV4 = re.compile(r"(?<![A-Za-z]/)\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")

CLICKABLES_JS = """
(rootSelector) => {
  const root = rootSelector ? document.querySelector(rootSelector) : document;
  if (!root) return [];
  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const out = [];
  for (const el of root.querySelectorAll('button, a, [role="button"], [role="tab"], [role="radio"], input')) {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0)) continue;
    out.push({
      tag: el.tagName.toLowerCase(),
      text: clean(el.innerText || el.value).slice(0, 100),
      aria: clean(el.getAttribute('aria-label')).slice(0, 140),
      testid: el.getAttribute('data-testid') || '',
      role: el.getAttribute('role') || '',
      href: (el.getAttribute('href') || '').slice(0, 160),
    });
    if (out.length >= 250) break;
  }
  return out;
}
"""


class AbnormalEmpty(RuntimeError):
    """A page loaded without the content it must have (no products, no store details)."""


class StoreNotVerified(RuntimeError):
    pass


# -- plans ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ListingPlan:
    category: str
    sub_category: str
    url: str


def listing_plans(
    seed: Mapping[str, Any], wanted: Sequence[tuple[str, str]], base: str = BASE
) -> list[ListingPlan]:
    """Resolve (client category, subcategory title) pairs to listing URLs of the saved site menu."""
    out: list[ListingPlan] = []
    for category, title in wanted:
        row = next((r for r in seed["rows"] if r["category"].lower() == category.lower()), None)
        if row is None:
            raise ValueError(f"unknown client category {category!r}")
        node = next((n for n in row.get("menu_nodes", []) if n["title"].lower() == title.lower()), None)
        if node is None:
            raise ValueError(f"{category!r} has no menu node {title!r}")
        out.append(ListingPlan(row["category"], node["title"], urljoin(base + "/", node["url"])))
    return out


# -- store verification -----------------------------------------------------------------------------


@dataclass
class StoreCheck:
    name: str
    ok: bool | None  # None: not applicable on this page
    observed: Any
    expected: Any
    required: bool = True
    note: str = ""


@dataclass
class StoreVerification:
    fetch_id: str
    purpose: str
    url: str
    checks: list[StoreCheck]
    context: dict[str, Any]
    attestation: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        required_ok = all(c.ok is True for c in self.checks if c.required)
        return required_ok and not any(c.ok is False for c in self.checks)

    def failures(self) -> list[str]:
        return [
            f"{c.name}: observed {c.observed!r}, expected {c.expected!r}"
            for c in self.checks
            if c.ok is False
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fetch_id": self.fetch_id,
            "purpose": self.purpose,
            "url": self.url,
            "passed": self.passed,
            "checks": [asdict(c) for c in self.checks],
            "context": self.context,
            "attestation_A1_A8": self.attestation,
        }


_HEADER_MODALITY = {
    "pickup": "PICKUP",
    "in-store": "IN_STORE",
    "in store": "IN_STORE",
    "delivery": "DELIVERY",
}


def _page_context(html: str) -> tuple[StoreContext | None, HeaderStore, str, str]:
    tree = LexborHTMLParser(html)
    header = parse_header_store(tree)
    address = text_of(tree.css_first('[data-testid="PickupAddressText"]'))
    try:
        return store_context_from_state(parse_initial_state(html)), header, address, ""
    except (InitialStateNotFound, ValueError) as exc:
        return None, header, address, f"no page state: {str(exc)[:120]}"


def request_scope(url: str, headers: Mapping[str, str]) -> dict[str, list[str]]:
    """The store and fulfillment a data request is for: ``filter.locationId`` in its URL, else the
    ``x-laf-object`` header the site sends (e.g. ``products/v2`` carries the store only there)."""
    store_ids: list[str] = []
    modalities: list[str] = []
    laf = headers.get("x-laf-object") or ""
    try:
        items = json.loads(laf) if laf else []
    except ValueError:
        items = []
    for item in items if isinstance(items, list) else []:
        m = item.get("modality") if isinstance(item, dict) else None
        if isinstance(m, dict):
            if m.get("type"):
                modalities.append(str(m["type"]))
            sid = (m.get("handoffLocation") or {}).get("storeId")
            if sid:
                store_ids.append(str(sid))
    in_url = request_location_id(url)
    return {"store_ids": [in_url] if in_url else store_ids, "modalities": modalities}


def verify_store(
    store: StoreConfig,
    settings: Settings,
    html: str,
    *,
    fetch_id: str,
    purpose: str,
    url: str,
    data_request_urls: Sequence[str] = (),
    data_request_headers: Sequence[Mapping[str, str]] = (),
    selected_before: bool | None = None,
) -> StoreVerification:
    """Is this page priced for the configured store, in its configured fulfillment, after an explicit
    selection? Read from the page state and the visible header; missing evidence is a failure."""
    exp = store.expected
    ctx, header, header_address, state_note = _page_context(html)
    details = ctx.store(store.location_id) if ctx else None
    ids = sorted({s.location_id for s in ctx.stores}) if ctx else []
    entry = ctx.active_modality_entry() if ctx else None
    modality = store.modality.value
    scopes = [
        request_scope(u, data_request_headers[i] if i < len(data_request_headers) else {})
        for i, u in enumerate(data_request_urls)
    ]
    req_ids = sorted({i for sc in scopes for i in sc["store_ids"]})
    req_modalities = sorted({m for sc in scopes for m in sc["modalities"]})
    unscoped = sum(1 for sc in scopes if not sc["store_ids"])
    requests_ok = (req_ids == [store.location_id] and req_modalities in ([], [modality])) if req_ids else None
    checks = [
        StoreCheck(
            "location_id",
            ctx is not None and ids == [store.location_id],
            ids,
            store.location_id,
            note=state_note,
        ),
        StoreCheck(
            "store_name",
            (header.vanity_name or (details.vanity_name if details else "")) == exp.display_name,
            {"header": header.vanity_name, "state": details.vanity_name if details else None},
            exp.display_name,
        ),
        StoreCheck(
            "address",
            details is not None
            and bool(details.address_lines)
            and details.address_lines[0].lower() == (exp.address_line1 or "").lower(),
            list(details.address_lines) if details else None,
            exp.address_line1,
        ),
        StoreCheck(
            "header_address",
            header_address.lower() == (exp.address_line1 or "").lower() if header_address else None,
            header_address,
            exp.address_line1,
            required=False,
        ),
        StoreCheck(
            "postal_code",
            details is not None and details.postal_code == exp.postal_code,
            details.postal_code if details else None,
            exp.postal_code,
        ),
        StoreCheck(
            "fulfillment",
            ctx is not None
            and details is not None
            and ctx.active_modality == modality
            and modality in details.allowed_modalities,
            {
                "active": ctx.active_modality if ctx else None,
                "allowed": list(details.allowed_modalities) if details else None,
                "header": _HEADER_MODALITY.get(header.modality_text.strip().lower(), header.modality_text),
            },
            modality,
        ),
        StoreCheck(
            "explicit_selection",
            entry is not None
            and not entry.source.upper().startswith("DEFAULT_")
            and (selected_before is None or selected_before),
            {
                "source": entry.source if entry else None,
                "isTrustedSource": entry.is_trusted_source if entry else None,
                "hasManuallySetActiveModality": ctx.has_manually_set_active_modality if ctx else None,
                "store_picker_confirmed_before_this_page": selected_before,
            },
            "the store chosen in the site's picker before this page, and no DEFAULT_* source",
            note="FALLBACK_ACTIVE_MODALITY_COOKIE was also seen on a site-default page (2026-10-20), so "
            "the source alone does not prove a selection",
        ),
        StoreCheck(
            "data_requests",
            requests_ok,
            {
                "requests": len(scopes),
                "store_ids": req_ids,
                "modalities": req_modalities,
                "without_store": unscoped,
            },
            {"store": store.location_id, "modality": modality},
            required=False,
            note="store from filter.locationId, else from the x-laf-object request header",
        ),
        StoreCheck(
            "laf",
            set(ctx.laf_store_ids) == {store.location_id} if ctx and ctx.laf_store_ids else None,
            list(ctx.laf_store_ids) if ctx else [],
            store.location_id,
            required=False,
        ),
        StoreCheck(
            "cms_scope",
            all(s.endswith(f"{store.division_number}/{store.store_number}") for s in ctx.cms_scopes)
            if ctx and ctx.cms_scopes
            else None,
            list(ctx.cms_scopes) if ctx else [],
            f"{store.division_number}/{store.store_number}",
            required=False,
        ),
    ]
    attestation: list[dict[str, Any]] = []
    if ctx is not None:
        res = attest(
            store,
            AttestationObservation(
                ctx,
                header_vanity_name=header.vanity_name or None,
                data_request_urls=tuple(u for u in data_request_urls if "products-search" in u),
            ),
            settings.attestation,
        )
        attestation = [
            {"check": c.check, "status": c.status.value, "observed": c.observed, "message": c.message}
            for c in res.checks
        ]
    context = {
        "active_modality": ctx.active_modality if ctx else None,
        "modality_source": entry.source if entry else None,
        "stores": [asdict(s) for s in ctx.stores] if ctx else [],
        "header": asdict(header),
        "header_address": header_address,
        "laf_store_ids": list(ctx.laf_store_ids) if ctx else [],
        "cms_scopes": list(ctx.cms_scopes) if ctx else [],
        "site_version": ctx.site_version if ctx else None,
        "data_request_location_ids": req_ids,
    }
    return StoreVerification(fetch_id, purpose, url, checks, context, attestation)


# -- store selection on the site --------------------------------------------------------------------


class StoreSelector:
    """Selects the configured store and fulfillment with the site's own controls, at most
    ``max_actions`` clicks. Every step is a paced UI action with its page copy and screenshot."""

    def __init__(self, session: BrowserSession, store: StoreConfig, *, max_actions: int = 8):
        self.s = session
        self.store = store
        self.max_actions = max_actions
        self.actions = 0
        self.log: list[dict[str, Any]] = []

    @property
    def page(self) -> Page:
        assert self.s.page is not None
        return self.s.page

    async def clickables(self, root_css: str | None = None) -> list[dict[str, Any]]:
        try:
            out = await self.page.evaluate(CLICKABLES_JS, root_css)
            return list(out) if isinstance(out, list) else []
        except Exception as exc:
            return [{"error": f"{type(exc).__name__}: {str(exc)[:120]}"}]

    @staticmethod
    async def _name(el: Locator) -> str:
        try:
            return collapse_ws((await el.get_attribute("aria-label")) or (await el.inner_text()))[:100]
        except Exception:
            return "?"

    async def _find(
        self,
        patterns: Sequence[str],
        *,
        css: str | None = None,
        scope: Locator | None = None,
        roles: Sequence[str] = ("button", "link"),
    ) -> tuple[Locator, str] | None:
        root: Page | Locator = scope if scope is not None else self.page
        if css:
            loc = root.locator(css)
            for i in range(min(await loc.count(), 4)):
                if await loc.nth(i).is_visible():
                    return loc.nth(i), f"css {css}"
        for pat in patterns:
            rx = re.compile(pat, re.I)
            for role in roles:
                loc = root.get_by_role(role, name=rx)  # type: ignore[arg-type]
                for i in range(min(await loc.count(), 6)):
                    el = loc.nth(i)
                    if await el.is_visible():
                        return el, f"{role} {await self._name(el)!r} ~ /{pat}/"
        return None

    async def click(
        self,
        purpose: str,
        patterns: Sequence[str] = (),
        *,
        css: str | None = None,
        scope: Locator | None = None,
        roles: Sequence[str] = ("button", "link"),
    ) -> str | None:
        if self.actions >= self.max_actions:
            self.log.append({"step": purpose, "skipped": "action limit reached"})
            return None
        target = await self._find(patterns, css=css, scope=scope, roles=roles)
        if target is None:
            self.log.append({"step": purpose, "found": False})
            return None
        el, desc = target
        self.actions += 1

        async def do(_: Page) -> dict[str, Any]:
            await el.click(timeout=10_000)
            return {"clicked": desc}

        fetch = await self.s.act(purpose, do, settle_ms=2500)
        self.log.append({"step": purpose, "found": True, "clicked": desc, "fetch_id": fetch.fetch_id})
        return desc

    async def from_store_page(self) -> None:
        url = self.store.store_page_url
        if not url:
            self.log.append({"step": "store_page", "skipped": "no store_page_url configured"})
            return
        if self.s.robots is None or not self.s.robots.allowed(url):
            self.log.append({"step": "store_page", "skipped": "robots.txt does not allow the store page"})
            return
        fetch = await self.s.navigate(url, "store_page", expect_initial_state=False)
        html = await self.s.current_html()
        name_tail = self.store.expected.display_name.split(" ", 1)[-1]
        if name_tail.lower() not in html.lower():
            raise AbnormalEmpty(f"the store page does not show {name_tail!r}")
        self.log.append(
            {"step": "store_page", "fetch_id": fetch.fetch_id, "clickables": await self.clickables()}
        )
        await self.click("store_page_cta", CTA_PATTERNS)

    async def via_store_picker(self) -> bool:
        """The site's store picker as recorded live on 2026-10-20 (``ModalitySelectorModal``): the
        header button, the In Store tab, a ZIP search, the configured store's card, then the panel's
        confirm button ("Plan Your Visit" / "Start Shopping"). Returns False at the first missing step."""
        st = self.store
        if not await self.click("open_store_picker", css=DEFAULT_SELECTORS.current_modality):
            return False
        dlg = self.page.locator(PICKER_CSS)
        if not await dlg.count():
            self.log.append({"step": "store_picker", "open": False})
            return False
        self.log.append(
            {"step": "store_picker", "open": True, "clickables": await self.clickables(PICKER_CSS)}
        )
        if not await self.click("choose_in_store", (r"^\s*in[- ]?store\s*$",), scope=dlg, roles=("tab",)):
            return False
        box = dlg.locator('[data-testid="PostalCodeSearchBox-input"]:visible')
        if not await box.count():
            self.log.append({"step": "search_postal_code", "found": False})
            return False
        target = box.first
        code = st.expected.postal_code

        async def search(_: Page) -> dict[str, Any]:
            await target.fill(code)
            await target.press("Enter")
            return {"typed": code}

        self.actions += 1
        fetch = await self.s.act("search_postal_code", search, settle_ms=3500)
        self.log.append({"step": "search_postal_code", "found": True, "fetch_id": fetch.fetch_id})
        card = dlg.locator(f'[data-testid="ModalityOption-Store-Card-{st.store_number}"]:visible')
        if not await card.count():
            shown = await dlg.locator('[data-testid^="ModalityOption-Store-Card-"]').evaluate_all(
                "els => els.map(e => e.getAttribute('data-testid'))"
            )
            self.log.append({"step": "pick_store", "found": False, "cards_shown": shown[:20]})
            return False
        text = collapse_ws(await card.first.inner_text())
        name_tail = st.expected.display_name.split(" ", 1)[-1]
        if (
            name_tail.lower() not in text.lower()
            or (st.expected.address_line1 or "").lower() not in text.lower()
        ):
            self.log.append({"step": "pick_store", "found": False, "card_text": text[:200]})
            return False
        choice = f'label[data-testid$="-{st.location_id}"], input[type="radio"][value="{st.location_id}"]'
        if not await self.click("pick_store", css=choice, scope=card.first):
            return False
        return bool(
            await self.click("confirm_store", css='button[data-testid^="Start-Shopping-"]', scope=dlg)
        )


def base_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def picker_confirmed_before(
    selection: Sequence[Mapping[str, Any]], order: Sequence[str], fetch_id: str
) -> bool:
    """Was the store picker's confirm button clicked in this session before the page ``fetch_id``?"""
    confirmed = [
        str(e.get("fetch_id")) for e in selection if e.get("step") == "confirm_store" and e.get("found")
    ]
    if not confirmed or fetch_id not in order:
        return False
    first = min((order.index(c) for c in confirmed if c in order), default=None)
    return first is not None and order.index(fetch_id) > first
