"""What a Classic response shows, and whether the campaign may go on.

Three statuses are kept apart (docs/DOCUMENTED_CONTRACT.md, Response codes): the provider's HTTP status of the
response, the retailer's status of each result (``results[].status_code``), and the parser's status
(``content.parse_status_code``). An HTTP 200 proves only that the provider answered. The retailer context and
the product identity are read from Walmart's own page data in the raw result with the Walmart collector's
validated readers (``vendor/``), and the parsed result has to agree with them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from classic_probe.stops import Stop
from classic_probe.transport import ProviderResponse
from classic_probe.vendor import walmart_challenge as wch
from classic_probe.vendor import walmart_page_data as wpd

# The documented billing rules (usage-and-billing/billing-information): results with 2xx or 4xx statuses are
# billed; 429 is not; failed attempts from the provider's errors (5xx, 6xx) are not; a fault on the caller's
# side is billed.
NOT_BILLED_HTTP = frozenset({429, 500, 524, 612, 613})
# Documented as temporary: "try again a bit later" (500), "Service unavailable" (524), "You can try again at
# no extra cost" (612, 613), the rate limit (429).
TRANSIENT_HTTP = frozenset({429, 500, 524, 612, 613})
CALLER_FAULT_HTTP = frozenset({400, 422})  # a wrong request: billed by the documented rule, never retried
PARSED_OK = frozenset({12000, 12004, 12005})  # success and the two documented partial successes


@dataclass
class Inspection:
    """One response, read. ``stop`` empty: the step succeeded and the campaign may go on."""

    provider_status: int
    billing: str
    results: int = 0  # entries of ``results`` (each type requested is one entry)
    billable_results: int = 0  # entries with a 2xx or 4xx retailer status
    render_forced: bool = False
    retailer_statuses: tuple[int, ...] = ()
    parser_status: int | None = None
    job_id: str | None = None
    transient: bool = False
    stop: Stop | None = None
    detail: str = ""
    facts: dict[str, Any] = field(default_factory=dict)

    def fail(self, stop: Stop, detail: str) -> Inspection:
        self.stop, self.detail = stop, detail
        return self


def provider(response: ProviderResponse) -> Inspection:
    """The provider's own answer: its HTTP status and the envelope."""
    status = response.http_status
    if status in NOT_BILLED_HTTP:
        billing = "documented_not_billed"
    elif status in CALLER_FAULT_HTTP or 200 <= status < 300:
        billing = "documented_billable"
    else:
        billing = "unknown"
    ins = Inspection(provider_status=status, billing=billing)
    if status in TRANSIENT_HTTP:
        ins.transient = True
        return ins.fail(Stop.RETRIES_EXHAUSTED, f"HTTP {status}: documented as temporary")
    if status == 401:
        return ins.fail(
            Stop.AUTHORIZATION, "HTTP 401: the authorization header is missing or the credentials are wrong"
        )
    if status == 403:
        return ins.fail(Stop.ENTITLEMENT, "HTTP 403: the account does not have access to this resource")
    if status in CALLER_FAULT_HTTP:
        return ins.fail(Stop.BAD_REQUEST, f"HTTP {status}: the request was refused (documented as billed)")
    if status != 200:
        return ins.fail(Stop.UNSUPPORTED_RESPONSE, f"HTTP {status} is not a documented Realtime answer here")
    try:
        body = json.loads(response.body)
    except ValueError:
        return ins.fail(Stop.UNSUPPORTED_RESPONSE, "the body is not JSON")
    results = body.get("results") if isinstance(body, Mapping) else None
    if not isinstance(results, list) or not results or not all(isinstance(r, Mapping) for r in results):
        return ins.fail(Stop.UNSUPPORTED_RESPONSE, "the body has no results list")
    ins.results = len(results)
    statuses = []
    for r in results:
        code = r.get("status_code")
        if not isinstance(code, int) or isinstance(code, bool):
            return ins.fail(Stop.UNSUPPORTED_RESPONSE, "a result has no status_code")
        statuses.append(code)
    ins.retailer_statuses = tuple(statuses)
    ins.billable_results = sum(1 for c in statuses if 200 <= c < 500)
    ins.render_forced = any(r.get("is_render_forced") is True for r in results)
    ins.job_id = next((str(r["job_id"]) for r in results if r.get("job_id")), None)
    ins.facts["results"] = results
    return ins


def _entries(
    results: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    raw = parsed = None
    for r in results:
        kind = r.get("type")
        content = r.get("content")
        if kind == "raw" or (kind is None and isinstance(content, str)):
            raw = raw or r
        elif kind == "parsed" or (kind is None and isinstance(content, Mapping)):
            parsed = parsed or r
    return raw, parsed


def _retailer(ins: Inspection, entry: Mapping[str, Any], *, product: bool) -> bool:
    code = int(entry["status_code"])
    if 200 <= code < 300:
        return True
    if code == 404 and product:
        ins.fail(Stop.WRONG_IDENTITY, "the retailer answered 404 for the product")
    else:
        ins.fail(Stop.BLOCKED, f"the retailer answered {code}")
    return False


def _raw_page(ins: Inspection, raw: Mapping[str, Any]) -> dict[str, Any] | None:
    html = raw.get("content")
    if not isinstance(html, str) or not html:
        ins.fail(Stop.UNSUPPORTED_RESPONSE, "the raw result has no page")
        return None
    verdict = wch.detect_document_challenge(
        int(raw["status_code"]), html, expect_initial_state=True, state_marker=wch.WALMART_STATE_MARKER
    )
    ins.facts["challenge_signals"] = list(wch.signals(verdict))
    ins.facts["challenge_notes"] = list(wch.notes(verdict))
    if verdict.is_challenge:
        ins.fail(Stop.BLOCKED, "a challenge or refusal page: " + ", ".join(wch.signals(verdict)))
        return None
    try:
        return wpd.next_data(html)
    except wpd.PageDataMissing:
        ins.fail(Stop.UNSUPPORTED_RESPONSE, "the raw page carries no Walmart page data")
        return None


def _parsed(ins: Inspection, parsed: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if parsed is None:
        ins.fail(Stop.UNSUPPORTED_RESPONSE, "no parsed result")
        return None
    content = parsed.get("content")
    if not isinstance(content, Mapping):
        ins.fail(Stop.UNSUPPORTED_RESPONSE, "the parsed result has no content object")
        return None
    code = content.get("parse_status_code")
    ins.parser_status = code if isinstance(code, int) else None
    if code not in PARSED_OK:
        ins.fail(Stop.PARSER_FAILED, f"parse_status_code {code}")
        return None
    return content


def _context(ins: Inspection, store_id: str, *, page_store: str, page_intent: str, parsed_store: str) -> bool:
    ins.facts["page_store"] = page_store
    ins.facts["page_intent"] = page_intent
    ins.facts["parsed_store"] = parsed_store
    if not page_store or not page_intent:
        ins.fail(Stop.UNVERIFIED_CONTEXT, "Walmart's page data names no store or no fulfillment")
        return False
    if page_store != store_id or page_intent != "PICKUP":
        ins.fail(
            Stop.WRONG_CONTEXT, f"the page is for store {page_store} {page_intent}, not {store_id} PICKUP"
        )
        return False
    if parsed_store and parsed_store != store_id:
        ins.fail(Stop.WRONG_CONTEXT, f"the parsed location names store {parsed_store}, the page {page_store}")
        return False
    return True


def search_page(ins: Inspection, store_id: str, page: int, previous_ids: frozenset[str] | None) -> Inspection:
    """A ``walmart_search`` page of the target store's Pickup results, and whether it advanced."""
    if ins.stop:
        return ins
    raw, parsed = _entries(ins.facts["results"])
    if raw is None:
        return ins.fail(
            Stop.UNVERIFIED_CONTEXT, "no raw result: the store cannot be read from Walmart's own data"
        )
    if not _retailer(ins, raw, product=False):
        return ins
    nd = _raw_page(ins, raw)
    content = _parsed(ins, parsed)
    if nd is None or content is None:
        return ins
    loc = wpd.page_location(nd)
    parsed_loc = content.get("location") if isinstance(content.get("location"), Mapping) else {}
    assert isinstance(parsed_loc, Mapping)
    if not _context(
        ins,
        store_id,
        page_store=loc.store_id if loc else "",
        page_intent=loc.intent if loc else "",
        parsed_store=wpd.text(parsed_loc.get("store_id")),
    ):
        return ins
    try:
        items = wpd.page_items(nd)
    except wpd.PageShapeUnclear as exc:
        return ins.fail(Stop.UNSUPPORTED_RESPONSE, f"the results of the page cannot be told apart: {exc}")
    ids = [it.item_id for it in items]
    parsed_results = [r for r in content.get("results") or [] if isinstance(r, Mapping)]
    parsed_ids = [wpd.text((r.get("general") or {}).get("product_id")) for r in parsed_results]
    details = content.get("page_details") if isinstance(content.get("page_details"), Mapping) else {}
    assert isinstance(details, Mapping)
    pg = wpd.pagination(nd)
    ins.facts.update(
        items=len(ids),
        item_ids=ids,
        parsed_items=len(parsed_ids),
        walmart_seller=sum(1 for it in items if it.seller_name.casefold() == "walmart.com"),
        with_pickup_line=sum(1 for it in items if any(f.kind == "PICKUP" for f in it.fulfillment)),
        sponsored=sum(1 for it in items if it.sponsored),
        page_reported=details.get("page"),
        last_visible_page=details.get("last_visible_page"),
        total_results=details.get("total_results"),
        page_data_page=pg.current_page,
        page_data_max_page=pg.max_page,
    )
    if not ids:
        return ins.fail(Stop.EMPTY_RESPONSE, "the page has no product")
    if set(parsed_ids) - set(ids):
        return ins.fail(
            Stop.UNSUPPORTED_RESPONSE, "the parsed results name products the page's own data does not hold"
        )
    if previous_ids is not None:
        if details.get("page") != page or pg.current_page != page:
            return ins.fail(
                Stop.REPEATED_PAGE,
                f"page {page} was asked for; the response says {details.get('page')} (parsed) and "
                f"{pg.current_page} (page data)",
            )
        if set(ids) <= previous_ids:
            return ins.fail(Stop.REPEATED_PAGE, f"page {page} holds only products of the previous page")
    return ins


def product_page(ins: Inspection, store_id: str, product_id: str) -> Inspection:
    """A ``walmart_product`` page: the requested product, for the target store's Pickup."""
    if ins.stop:
        return ins
    raw, parsed = _entries(ins.facts["results"])
    if raw is None:
        return ins.fail(
            Stop.UNVERIFIED_CONTEXT, "no raw result: the product cannot be read from Walmart's own data"
        )
    if not _retailer(ins, raw, product=True):
        return ins
    nd = _raw_page(ins, raw)
    content = _parsed(ins, parsed)
    if nd is None or content is None:
        return ins
    page = wpd.product_page(nd)
    ident = wpd.product_identifier(str(raw["content"]), product_id)
    general = content.get("general") if isinstance(content.get("general"), Mapping) else {}
    assert isinstance(general, Mapping)
    parsed_url = wpd.text(general.get("url"))
    ins.facts.update(
        page_item=page.page_item if page else ident.page_item,
        upc=ident.value,
        upc_path=ident.path,
        parsed_gtin=wpd.text((general.get("meta") or {}).get("gtin")),
        parsed_url_item=wpd.item_id_from_url(parsed_url) if parsed_url else "",
        seller=wpd.text((content.get("seller") or {}).get("name")),
    )
    if page is None or page.page_item != product_id:
        return ins.fail(
            Stop.WRONG_IDENTITY, f"the page is for item {ins.facts['page_item'] or 'none'}, not {product_id}"
        )
    if ins.facts["parsed_url_item"] and ins.facts["parsed_url_item"] != product_id:
        return ins.fail(Stop.WRONG_IDENTITY, f"the parsed product is item {ins.facts['parsed_url_item']}")
    parsed_loc = content.get("location") if isinstance(content.get("location"), Mapping) else {}
    assert isinstance(parsed_loc, Mapping)
    page_store = (
        store_id
        if store_id in page.store_ids or page.pickup_store == store_id
        else (page.pickup_store or (page.store_ids[0] if page.store_ids else ""))
    )
    _context(
        ins,
        store_id,
        page_store=page_store,
        page_intent=page.intent,
        parsed_store=wpd.text(parsed_loc.get("store_id")),
    )
    return ins


def category_page(ins: Inspection, store_id: str) -> Inspection:
    """A Walmart page requested by its URL alone. The documentation states no store or fulfillment parameter
    for this form, so its context is whatever the page itself states."""
    if ins.stop:
        return ins
    raw, _ = _entries(ins.facts["results"])
    if raw is None:
        return ins.fail(Stop.UNSUPPORTED_RESPONSE, "no page in the result")
    if not _retailer(ins, raw, product=False):
        return ins
    nd = _raw_page(ins, raw)
    if nd is None:
        return ins
    loc = wpd.page_location(nd)
    if not _context(
        ins,
        store_id,
        page_store=loc.store_id if loc else "",
        page_intent=loc.intent if loc else "",
        parsed_store="",
    ):
        return ins
    try:
        ins.facts["items"] = len(wpd.page_items(nd))
    except wpd.PageShapeUnclear as exc:
        return ins.fail(Stop.UNSUPPORTED_RESPONSE, f"the results of the page cannot be told apart: {exc}")
    return ins
