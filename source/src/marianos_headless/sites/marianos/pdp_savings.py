"""A product page's "Savings" section, as the site renders it (release 1.9.0, M4: complete coupon terms).

Observed 2026-11-06 (gated live observation stage O1, Vernon Hills 53100502, PICKUP, the Web API's Mariano's
scraper with ``run_js``): the rendered product page holds ``[data-testid="savings-center-pdp"]``, one
``[data-testid="savings-center-row-<kind>"]`` per offer of the product (``other-coupon``, ``cash-back``,
``must-buy``, ...). A coupon row carries its details dialog, already rendered: the savings tag ("Coupon",
"Cash Back"), the headline (``CouponDetails-shortDescription``), the description paragraph and its full legal
copy (``show-more-expanded-copy``), the displayed expiry (``CouponExpiryDate-<id>``, e.g. "Exp. Nov. 10")
and days left (``CouponExpiryDays-<id>``), the action (``CouponActionButton-<id>``: "Sign In To Clip", "Sign
In for Cash Back"), and the "Qualifying Products" the coupon lists (product links with their UPCs). The
coupon's ID is the number in those test ids. The listing card shows only the headline ("Coupon: Save
$10.00 on 2 Purina ONE"; its "View 2 Offers" opens this dialog), and the site's coupon API is not reachable
through the provider (stage O1, two faulted attempts, not charged).

Nothing here is computed: wording is kept as displayed (whitespace collapsed); an expiry without a year stays
as displayed; a coupon applies to a product only when its own "Qualifying Products" list names the product."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from selectolax.lexbor import LexborHTMLParser, LexborNode

from marianos_headless.core.text import collapse_ws

SECTION = '[data-testid="savings-center-pdp"]'
ROW = '[data-testid^="savings-center-row-"]'
DETAILS = '[data-testid="CouponDetails-new-content"]'
HEADLINE = '[data-testid="CouponDetails-shortDescription"]'
EXPANDED = '[data-testid="show-more-expanded-copy"]'
TAG = '[data-testid="savings-tag"]'
ACTION = '[data-testid^="CouponActionButton-"]'
PROMOTION = '[data-testid="promotion-description"]'
PROMOTION_SECTION = '[data-testid="promotion-details-section"]'
_UPC_HREF = re.compile(r"/p/[^?#]*/(\d{13})(?:[?#]|$)")
COUPON_KINDS = frozenset({"other-coupon", "cash-back", "digital-coupon", "coupon"})


@dataclass(frozen=True)
class SavingsRow:
    """One offer of the product's Savings section, as displayed."""

    row_kind: str  # the row's own kind, from its test id: "other-coupon", "cash-back", "must-buy", ...
    tag: str  # the savings tag shown: "Coupon", "Cash Back", "Sale", ...
    coupon_id: str  # "" for an offer that names no coupon (a sale)
    headline: str
    description: str  # the description paragraph's own sentence(s), as displayed
    legal: str  # the full copy behind "Show More", as displayed
    expiry_text: str  # e.g. "Exp. Nov. 10" (as displayed: no year is invented)
    days_left_text: str  # e.g. "4 days left!" (relative to the observation)
    action: str  # e.g. "Sign In To Clip"
    action_label: str
    qualifying_upcs: tuple[str, ...]
    has_details: bool
    locators: dict[str, str] = field(default_factory=dict)

    @property
    def is_coupon(self) -> bool:
        return bool(self.coupon_id) and (
            self.row_kind in COUPON_KINDS or self.tag.casefold() in {"coupon", "cash back"}
        )

    @property
    def coupon_type(self) -> str:
        if self.row_kind == "cash-back" or self.tag.casefold() == "cash back":
            return "CASH_BACK"
        return "STANDARD"

    @property
    def terms(self) -> str:
        """The coupon's applicable terms as displayed: its description, then its full legal copy."""
        return collapse_ws(" ".join(x for x in (self.description, self.legal) if x))

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_kind": self.row_kind,
            "tag": self.tag,
            "coupon_id": self.coupon_id,
            "headline": self.headline,
            "description": self.description,
            "legal": self.legal,
            "expiry_text": self.expiry_text,
            "days_left_text": self.days_left_text,
            "action": self.action,
            "action_label": self.action_label,
            "qualifying_upcs": list(self.qualifying_upcs),
            "has_details": self.has_details,
            "locators": dict(self.locators),
        }


@dataclass(frozen=True)
class PdpSavings:
    """What a rendered product page shows about its offers."""

    section: bool  # the page shows a Savings section at all
    rows: tuple[SavingsRow, ...]

    def coupons(self) -> list[SavingsRow]:
        return [r for r in self.rows if r.is_coupon]


def _own_text(p: LexborNode) -> str:
    """A paragraph's own text: its text nodes only (the "..." marker, the hidden copy and the "Show More"
    button are elements of their own)."""
    parts: list[str] = []
    for ch in p.iter(include_text=True):
        if ch.tag == "-text":
            parts.append(ch.text_content or "")
    return collapse_ws("".join(parts))


def _text(n: LexborNode | None) -> str:
    return collapse_ws(n.text(deep=True)) if n is not None else ""


def parse_row(row: LexborNode) -> SavingsRow:
    kind = (row.attributes.get("data-testid") or "").removeprefix("savings-center-row-")
    details = row.css_first(DETAILS)
    headlines = [t for t in (_text(n) for n in row.css(HEADLINE)) if t]
    para = details.css_first("p") if details is not None else None
    btn = row.css_first(ACTION)
    cid = (
        (btn.attributes.get("data-testid") or "").removeprefix("CouponActionButton-")
        if btn is not None
        else ""
    )
    if not cid:
        exp_any = row.css_first('[data-testid^="CouponExpiryDate-"]')
        if exp_any is not None:
            cid = (exp_any.attributes.get("data-testid") or "").removeprefix("CouponExpiryDate-")
    exp = row.css_first(f'[data-testid="CouponExpiryDate-{cid}"]') if cid else None
    days = row.css_first(f'[data-testid="CouponExpiryDays-{cid}"]') if cid else None
    qualifying: list[str] = []
    for a in row.css('a[href*="/p/"]'):
        m = _UPC_HREF.search(a.attributes.get("href") or "")
        if m and m.group(1) not in qualifying:
            qualifying.append(m.group(1))
    promo = row.css_first(PROMOTION)
    headline = headlines[0] if headlines else _text(promo)
    expiry = _text(exp)
    if not expiry and promo is not None:
        # A sale's "Offer Details" (live 2026-11-06, UPC 0001820020352): "Exp. Jan. 05", then "-" and an
        # empty days-left part.
        section = row.css_first(PROMOTION_SECTION)
        expiry = next(
            (t for t in (_text(n) for n in (section or row).css("span")) if t.startswith("Exp.")),
            "",
        )
    if not headline:
        # Neither a coupon headline nor a promotion description: the row's first text after its tag.
        headline = next(
            (t for t in (_text(n) for n in row.css('span[data-citrus-component="Text"]')) if t), ""
        )
    locators = {
        "row": f'[data-testid="{row.attributes.get("data-testid")}"]',
        "headline": HEADLINE if headlines else PROMOTION,
        "legal": EXPANDED,
    }
    if cid:
        locators.update(
            expiry=f'[data-testid="CouponExpiryDate-{cid}"]',
            days_left=f'[data-testid="CouponExpiryDays-{cid}"]',
            action=f'[data-testid="CouponActionButton-{cid}"]',
        )
    return SavingsRow(
        row_kind=kind,
        tag=_text(row.css_first(TAG)),
        coupon_id=cid,
        headline=headline,
        description=_own_text(para) if para is not None else "",
        legal=_text(row.css_first(EXPANDED)),
        expiry_text=expiry,
        days_left_text=_text(days),
        action=_text(btn),
        action_label=collapse_ws(btn.attributes.get("aria-label") or "") if btn is not None else "",
        qualifying_upcs=tuple(qualifying),
        has_details=details is not None,
        locators=locators,
    )


def parse_pdp_savings(html: str) -> PdpSavings:
    tree = LexborHTMLParser(html)
    section = tree.css_first(SECTION)
    if section is None:
        return PdpSavings(section=False, rows=())
    return PdpSavings(section=True, rows=tuple(parse_row(r) for r in section.css(ROW)))


def savings_document(html: str, *, upc: str, rendered: bool | None, requested_run_js: bool) -> dict[str, Any]:
    """The capture artifact of one product page's Savings section (kind ``pdp_savings``), indexed like the
    site's other responses. ``rendered`` is the provider's own statement that it ran the page's scripts
    (``results[0].metadata.run_js``): the coupon rows load only then, so a page brought without them proves
    nothing about the product's coupons (stage O1, 2026-11-06: of 14 product pages requested with ``run_js``
    the answers of 3 state it; one of the 3, 0001780014939, shows coupon rows and the other 2 show no Savings
    section; the 11 brought without it show no coupon row. Notes before 1.10.0 said 1 of 14 came back
    rendered)."""
    s = parse_pdp_savings(html)
    return {
        "data": {
            "upc": upc,
            "requested_run_js": requested_run_js,
            "rendered": rendered,
            "section": s.section,
            "rows": [r.as_dict() for r in s.rows],
        }
    }
