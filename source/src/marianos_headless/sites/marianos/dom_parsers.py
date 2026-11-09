"""Offline parsers for rendered Mariano's DOM (brief §4.7).

Parsers read displayed text only and never compute values. Selectors live in :class:`Selectors` so
the site contract can update them without code changes elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

from marianos_headless.core.text import collapse_ws, normalize_single_price

if TYPE_CHECKING:
    from collections.abc import Iterable

BASE_URL = "https://www.marianos.com/"
_UPC_IN_PATH = re.compile(r"/p/[^/]+/(\d{13})(?:[/?#]|$)")
_COUPON_ID = re.compile(r"-(\d+)$")
_SLOT_SEPARATOR = re.compile(r"\s*\|$")  # a trailing separator before a sibling link, not size text
# The label a grid card's savings zone shows before a coupon's text ("Coupon: $4.99 Kroger Seedless Grapes").
ZONE_LABEL = re.compile(r"^(Coupon|Digital Coupon|Weekly Digital Deal|Cash Back)\s*:\s*(?=\S)", re.I)
# A displayed price per measure: "$0.23/oz", "$0.05 / fl oz", "($1.99/lb)". Never parsed into numbers.
PPM_DISPLAY = re.compile(
    r"^\(?\$\d{1,4}(?:\.\d{1,3})?\s*/\s*"
    r"(?:fl\.? ?oz|oz|lb|lbs|ct|count|each|ea|sq\.? ?ft|qt|gal|pt|l|ml|g|kg"
    r"|load|use|sheet|roll|bag|pack|pk|100 ?ct)\.?\)?$",
    re.I,
)


@dataclass(frozen=True)
class Selectors:
    card_root: str = '[data-testid^="carousel-product-card-"]'
    title: str = '[data-testid="cart-page-item-description"]'
    size: str = '[data-testid="product-item-sizing"]'
    price_block: str = '[data-testid="product-item-unit-price"]'
    price_tag: str = '[data-testid="price-heading-tag"]'
    savings_zone: str = '[data-testid="savings-zone"]'
    zone_card: str = '[data-testid="savings-zone-card"]'
    zone_text: str = '[data-testid="savings-zone-text"]'  # grid cards: the offer without "View Offer"
    # Grid cards with a coupon: "Coupon: $4.99 Kroger Seedless Grapes" beside a "View Offer" button.
    zone_coupon_text: str = '[data-testid="savings-zone-coupon-text"]'
    coupon_checkbox: str = 'input[data-testid="coupon-checkbox"]'
    product_link: str = 'a[href*="/p/"]'
    product_image: str = '[data-testid="product-image"] img'
    offer_drawer: str = 'dialog[data-testid="savings-side-drawer"]'
    drawer_offer: str = '[data-testid="savings-side-offer"], [data-testid="savings-side-coupon"]'
    savings_tag: str = '[data-testid="savings-tag"]'
    coupon_card_root_prefix: str = "CouponCard-"
    header_logo: str = ".KrogerHeader-Logo img.hardcoded-logo"
    current_modality: str = '[data-testid="CurrentModality-button"]'
    current_modality_type: str = '[data-testid="CurrentModality-modalityType"]'
    current_vanity_name: str = '[data-testid="CurrentModality-vanityName"]'
    # Release 1.9.0rc2. The tile served since 2026-11-06 shows its price per measure in an element of its own
    # (empty: the older cards' sizing slots hold it) and has no size slot at all.
    ppm: str = ""
    has_size_slot: bool = True
    layout: str = "card"  # "card": the cards up to 2026-11-04; "tile": the tile served since 2026-11-06


DEFAULT_SELECTORS = Selectors()

# Release 1.9.0rc2. The product tile the site serves since 2026-11-06 (stages S1 and O2, store 53100502
# PICKUP): "horizontal-product-card-N" on listing pages and "default-product-card-N" on search pages
# (CardTemplate-Horizontal / CardTemplate-Default), with the same inner test ids. Its price is the same citrus
# Price component as before; its price per measure has an element of its own; it shows no size (a product's
# size is stated only in its own data in the same page, ``item.customerFacingSize``: see
# ``assembly.record_builder``); its savings zone keeps the earlier test ids ("Buy 1 Save $2", "View 1 Offer").
# The cards up to 2026-11-04 keep their own selectors (``Selectors()``): earlier saved pages read as before.
TILE_PREFIXES = ("horizontal-product-card-", "default-product-card-")
TILE_SELECTORS = Selectors(
    card_root=", ".join(f'[data-testid^="{p}"]' for p in TILE_PREFIXES),
    title='[data-testid="product-description"]',
    price_block='[data-testid="product-price"]',
    price_tag='[data-testid="eyebrow-text"]',
    product_image='img[data-testid="product-image"]',
    ppm='[data-testid="product-price-equivalized-unit-price"]',
    has_size_slot=False,
    layout="tile",
)


def selectors_for(card: LexborNode, sel: Selectors = DEFAULT_SELECTORS) -> Selectors:
    """The selectors of the card's own template: the tile's (release 1.9.0rc2) or the given ones."""
    testid = card.attributes.get("data-testid") or ""
    return TILE_SELECTORS if testid.startswith(TILE_PREFIXES) else sel


def _all(node: LexborNode, selector: str) -> list[LexborNode]:
    """Descendants matching ``selector``. Lexbor's ``Node.css`` also matches the node itself."""
    me = node.mem_id
    return [n for n in node.css(selector) if n.mem_id != me]


def _first(node: LexborNode, selector: str) -> LexborNode | None:
    return next(iter(_all(node, selector)), None)


def text_of(node: LexborNode | None) -> str:
    return collapse_ws(node.text(deep=True)) if node is not None else ""


def absolute_url(href: str) -> str:
    return urljoin(BASE_URL, href)


def canonical_product_url(url: str) -> str:
    """A product page URL without the query a listing appends (``?fulfillment=PICKUP`` selects a tab
    of the same page); other URLs are returned unchanged."""
    parts = urlsplit(url)
    if "/p/" not in parts.path:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def upc_from_product_url(url: str) -> str | None:
    m = _UPC_IN_PATH.search(urlsplit(url).path + "/")
    return m.group(1) if m else None


def observable_image_url(src: str | None) -> str:
    """Only http(s) URLs are real image URLs; inlined ``data:`` URIs (saved pages) are not."""
    if not src:
        return ""
    src = src.strip()
    if src.startswith(("http://", "https://")):
        return src
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return absolute_url(src)
    return ""


class PriceDisplayKind(StrEnum):
    REGULAR = "regular"
    SALE = "sale"
    RELATIVE = "relative"  # "about $X each" (orderBy Unit, sellBy Weight)
    RELATIVE_SALE = "relative_sale"
    NOT_DISPLAYED = "not_displayed"  # e.g. "Prices May Vary"
    MISSING = "missing"  # no price block at all and no known placeholder
    # Release 1.9.0rc2: a tile's price in a form not seen on the tile before (nothing is guessed from it).
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True)
class PriceDisplay:
    kind: PriceDisplayKind
    current_text: str  # displayed current price, e.g. "$34.99"
    original_text: str  # struck-through price, e.g. "$39.99"; "" when absent
    sr_text: str  # screen-reader sentence, e.g. "Sale: $34.99 discounted from $39.99"
    placeholder_text: str  # e.g. "Prices May Vary"
    regular_price: str  # normalised two-decimal string or ""
    sale_price: str

    @property
    def is_relative(self) -> bool:
        return self.kind in (PriceDisplayKind.RELATIVE, PriceDisplayKind.RELATIVE_SALE)


@dataclass(frozen=True)
class ZoneOffer:
    """The single offer the card's savings zone shows."""

    text: str  # the offer's own text, without the zone's label and without button labels
    requires_clip: bool  # a coupon checkbox is present
    checkbox_label: str
    label: str = ""  # the label the zone shows before the text, e.g. "Coupon" in "Coupon: $4.99 …"
    details: bool = False  # a "View Offer" button opens the offer's details


@dataclass(frozen=True)
class CardObservation:
    position: int  # document order of the card on the page
    card_testid: str
    upc: str | None
    url: str  # absolute product URL as linked, without the view parameters a listing appends
    title: str
    size_text: str
    price: PriceDisplay
    price_tag: str  # "Everyday Low Price", "Price Cut", … (a label, not a price)
    zone: ZoneOffer | None
    image_src: str  # raw src attribute
    image_url: str  # observable http(s) URL or ""
    snap_ebt: bool
    flags: tuple[str, ...] = ()
    ppm_text: str = ""  # price per measure as displayed (grid cards show it next to the size), or ""
    layout: str = "card"  # "tile": the tile served since 2026-11-06 (release 1.9.0rc2)
    size_displayed: bool = True  # False: the card has no size slot (the tile): no size is displayed


def _class_tokens(node: LexborNode) -> set[str]:
    return set((node.attributes.get("class") or "").split())


def _price_placeholder(card: LexborNode, sel: Selectors) -> str:
    """The text a card shows instead of a price ("Prices May Vary"), or "".

    Carousel cards show it first in their description container. Grid cards show it in the price area,
    above the title: the first plain text span (one without a ``data-testid``) before the title."""
    desc = _first(card, '[class*="DescriptionContainer"]')
    if desc is not None:
        candidate = text_of(_first(desc, "span.citrus-Text"))
        return candidate if candidate and not re.search(r"\$\d", candidate) else ""
    title = _first(card, sel.title)
    stop = title.mem_id if title is not None else None
    for node in _all(card, "*"):
        if node.mem_id == stop:
            break
        if (
            node.tag == "span"
            and node.attributes.get("data-citrus-component") == "Text"
            and not node.attributes.get("data-testid")
        ):
            candidate = text_of(node)
            if candidate and not re.search(r"\$\d", candidate):
                return candidate
    return ""


def parse_price_block(card: LexborNode, sel: Selectors = DEFAULT_SELECTORS) -> PriceDisplay:
    block = _first(card, sel.price_block)
    if block is None:
        placeholder = _price_placeholder(card, sel)
        kind = PriceDisplayKind.NOT_DISPLAYED if placeholder else PriceDisplayKind.MISSING
        return PriceDisplay(kind, "", "", "", placeholder, "", "")

    classes = _class_tokens(block)
    relative = "citrus-RelativePrice" in classes
    promo = any(c.endswith("--promotional") for c in classes)
    if relative:
        current = text_of(_first(block, ".citrus-RelativePrice--current-price-value"))
        original = text_of(_first(block, ".citrus-RelativePrice--original-price"))
        sr = text_of(_first(block, ".citrus-RelativePrice--sr-description"))
        kind = PriceDisplayKind.RELATIVE_SALE if promo else PriceDisplayKind.RELATIVE
    else:
        current = text_of(_first(block, ".citrus-Price--current-price"))
        original = text_of(_first(block, ".citrus-Price--original-price-value"))
        sr = text_of(_first(block, ".citrus-Price--sr-description"))
        kind = PriceDisplayKind.SALE if promo else PriceDisplayKind.REGULAR

    current_n = normalize_single_price(current)
    original_n = normalize_single_price(original)
    if promo:
        regular, sale = original_n, current_n
    else:
        regular, sale = current_n, ""
    return PriceDisplay(kind, current, original, sr, "", regular, sale)


# A single displayed price: "$2.99", "$1,299.00". Anything else in a tile's price element is not read.
_PLAIN_PRICE = re.compile(r"^\$\d{1,3}(?:,\d{3})*\.\d{2}$")


def tile_price(display: PriceDisplay) -> PriceDisplay:
    """A tile's price, only in the forms the tile was seen to show (stages S1 and O2, 2026-11-06): a plain
    price whose screen-reader text is the same price; "Sale: $X discounted from $Y" with the promotional
    style; "about $X each" (a product sold by weight). Any other form, for example a multi-unit price written
    in the price element, is UNRECOGNIZED: no price is read from it (a single price taken out of "2 For $5.00"
    would be a guess)."""
    cur, orig, sr = display.current_text, display.original_text, display.sr_text
    k = display.kind
    if k in (PriceDisplayKind.NOT_DISPLAYED, PriceDisplayKind.MISSING):
        return display
    plain = bool(_PLAIN_PRICE.match(cur))
    if k is PriceDisplayKind.REGULAR:
        ok = plain and not orig and sr == cur
    elif k is PriceDisplayKind.SALE:
        ok = plain and bool(_PLAIN_PRICE.match(orig)) and sr == f"Sale: {cur} discounted from {orig}"
    elif k is PriceDisplayKind.RELATIVE:
        ok = plain and not orig and sr == f"about {cur} each"
    else:  # RELATIVE_SALE: not seen on a tile; an estimate is never exported as a price either way
        ok = plain and sr.startswith(f"about {cur}")
    if ok:
        return display
    return PriceDisplay(PriceDisplayKind.UNRECOGNIZED, cur, orig, sr, "", "", "")


def _text_without_buttons(node: LexborNode) -> str:
    """The node's text without its buttons: "View Offer" and other controls are not offer text."""
    sub = LexborHTMLParser(node.html or "")
    for button in sub.css("button"):
        button.decompose()
    return text_of(sub.body)


def parse_zone(card: LexborNode, sel: Selectors = DEFAULT_SELECTORS) -> ZoneOffer | None:
    zone = _first(card, sel.savings_zone)
    if zone is None:
        return None
    checkbox = _first(zone, sel.coupon_checkbox)
    checkbox_label = collapse_ws(checkbox.attributes.get("aria-label")) if checkbox is not None else ""
    own = _first(zone, sel.zone_coupon_text) or _first(zone, sel.zone_text)
    text = text_of(own) if own is not None else _text_without_buttons(zone)
    label = ""
    m = ZONE_LABEL.match(text)
    if m:
        label, text = m.group(1), text[m.end() :]
    return ZoneOffer(
        text=text,
        requires_clip=checkbox is not None,
        checkbox_label=checkbox_label,
        label=label,
        details=_first(zone, "button") is not None,
    )


def parse_card(card: LexborNode, position: int, sel: Selectors = DEFAULT_SELECTORS) -> CardObservation:
    link = _first(card, sel.product_link)
    href = (link.attributes.get("href") or "") if link is not None else ""
    url = canonical_product_url(absolute_url(href)) if href else ""
    img = _first(card, sel.product_image)
    src = (img.attributes.get("src") or "") if img is not None else ""
    flags: list[str] = []
    image_url = observable_image_url(src)
    if src and not image_url:
        flags.append("IMAGE_NOT_OBSERVABLE")
    # Grid cards show two sizing slots: the price per measure, then the size. Carousel cards show one
    # (the size, or for "about $X each" items the $/lb, which the record builder handles).
    # In-store listings end the size slot with the separator of a "3 more sizes" link ("5 oz | ").
    sizes = [_SLOT_SEPARATOR.sub("", text_of(n)) for n in _all(card, sel.size)]
    ppm = next((t for t in sizes if PPM_DISPLAY.match(t)), "") if len(sizes) > 1 else ""
    size_text = next((t for t in sizes if t and t != ppm), "") if ppm else (sizes[0] if sizes else "")
    price = parse_price_block(card, sel)
    if sel.ppm:  # the tile (1.9.0rc2): its own price-per-measure element, no size slot
        shown = text_of(_first(card, sel.ppm))
        ppm = shown if PPM_DISPLAY.match(shown) else ""
        if shown and not ppm:
            flags.append("PPM_TEXT_UNRECOGNIZED")
    if not sel.has_size_slot:
        size_text = ""
    if sel.layout == "tile":
        price = tile_price(price)
        if price.kind is PriceDisplayKind.UNRECOGNIZED:
            flags.append("PRICE_DISPLAY_UNRECOGNIZED")
    return CardObservation(
        position=position,
        card_testid=card.attributes.get("data-testid") or "",
        upc=upc_from_product_url(url) if url else None,
        url=url,
        title=text_of(_first(card, sel.title)),
        size_text=size_text,
        price=price,
        price_tag=text_of(_first(card, sel.price_tag)),
        zone=parse_zone(card, sel),
        image_src=src if not src.startswith("data:") else "data:",
        image_url=image_url,
        snap_ebt=_first(card, '[data-testid="snap-ebt-eligible-tag"]') is not None,
        flags=tuple(flags),
        ppm_text=ppm,
        layout=sel.layout,
        size_displayed=sel.has_size_slot,
    )


def parse_cards(tree: LexborHTMLParser, sel: Selectors = DEFAULT_SELECTORS) -> list[CardObservation]:
    """Each card with its own template's selectors (release 1.9.0rc2: the tile, or ``sel``)."""
    return [parse_card(node, i, selectors_for(node, sel)) for i, node in enumerate(tree.css(sel.card_root))]


# --- Offer drawer -------------------------------------------------------------------------------


@dataclass(frozen=True)
class DrawerOffer:
    source: str  # "drawer_offer" (savings-side-offer) | "drawer_coupon" (savings-side-coupon)
    display_order: int
    tag: str  # "Sale", "Coupon", "Weekly Digital Deal", "Cash Back", …
    text: str  # full offer sentence (last headline)
    headlines: tuple[str, ...]  # all headline texts as displayed (the first may be a split price)
    expiry_text: str  # "Exp. Oct. 20" without the relative countdown
    ctas: tuple[str, ...]
    coupon_id: str | None


@dataclass(frozen=True)
class OfferDrawer:
    position: int
    dialog_id: str
    offers: tuple[DrawerOffer, ...]


def _expiry_text(node: LexborNode) -> str:
    dated = _first(node, '[data-testid^="CouponExpiryDate-"]')
    if dated is not None:
        return text_of(dated)
    for span in _all(node, "span"):
        t = text_of(span)
        if t.startswith("Exp.") and _first(span, "span") is None:
            return t
    return ""


def parse_drawer(dialog: LexborNode, position: int, sel: Selectors = DEFAULT_SELECTORS) -> OfferDrawer:
    offers: list[DrawerOffer] = []
    for i, node in enumerate(_all(dialog, sel.drawer_offer)):
        testid = node.attributes.get("data-testid") or ""
        headlines = tuple(text_of(h) for h in _all(node, "h3"))
        coupon_id = None
        for el in _all(node, '[data-testid^="CouponExpiryDate-"], [data-testid^="CouponActionButton-"]'):
            m = _COUPON_ID.search(el.attributes.get("data-testid") or "")
            if m:
                coupon_id = m.group(1)
                break
        offers.append(
            DrawerOffer(
                source="drawer_coupon" if testid == "savings-side-coupon" else "drawer_offer",
                display_order=i,
                tag=text_of(_first(node, sel.savings_tag)),
                text=headlines[-1] if headlines else "",
                headlines=headlines,
                expiry_text=_expiry_text(node),
                ctas=tuple(text_of(b) for b in _all(node, "button")),
                coupon_id=coupon_id,
            )
        )
    return OfferDrawer(position, dialog.attributes.get("id") or "", tuple(offers))


def parse_drawers(tree: LexborHTMLParser, sel: Selectors = DEFAULT_SELECTORS) -> list[OfferDrawer]:
    return [parse_drawer(d, i, sel) for i, d in enumerate(tree.css(sel.offer_drawer))]


# --- Coupon cards -------------------------------------------------------------------------------


@dataclass(frozen=True)
class CouponCardObservation:
    position: int
    coupon_id: str
    brand: str  # data-brand
    categories: tuple[str, ...]  # data-category, split on ","
    title: str  # headline aria-label, never the split-price join
    description: str  # CouponDesc-<id>
    expiry_text: str
    savings_tag: str  # "Weekly Digital Deal", "Points Event", … ("" when none)
    other_tags: tuple[str, ...]  # e.g. "Pickup & Delivery Only"
    ctas: tuple[str, ...]


def parse_coupon_cards(
    tree: LexborHTMLParser, sel: Selectors = DEFAULT_SELECTORS
) -> list[CouponCardObservation]:
    out: list[CouponCardObservation] = []
    root_re = re.compile(rf"^{re.escape(sel.coupon_card_root_prefix)}(\d+)$")
    for node in tree.css(f'[data-testid^="{sel.coupon_card_root_prefix}"]'):
        m = root_re.match(node.attributes.get("data-testid") or "")
        if not m:
            continue
        cid = m.group(1)
        title_node = _first(node, f'[data-testid="CouponTitle-{cid}"]')
        title = collapse_ws(title_node.attributes.get("aria-label")) if title_node is not None else ""
        savings_tag = text_of(_first(node, sel.savings_tag))
        other = tuple(
            t
            for tag in _all(node, '[data-citrus-component="Tag"]')
            if (t := text_of(tag)) and tag.attributes.get("data-testid") != "savings-tag"
        )
        out.append(
            CouponCardObservation(
                position=len(out),
                coupon_id=cid,
                brand=collapse_ws(node.attributes.get("data-brand")),
                categories=tuple(
                    c.strip() for c in (node.attributes.get("data-category") or "").split(",") if c.strip()
                ),
                title=title,
                description=text_of(_first(node, f'[data-testid="CouponDesc-{cid}"]')),
                expiry_text=text_of(_first(node, f'[data-testid="CouponExpiryDate-{cid}"]')),
                savings_tag=savings_tag,
                other_tags=other,
                ctas=tuple(text_of(b) for b in _all(node, "button") if text_of(b)),
            )
        )
    return out


# --- Header (store context as displayed) ---------------------------------------------------------


@dataclass(frozen=True)
class HeaderStore:
    modality_text: str  # e.g. "Pickup"
    vanity_name: str  # e.g. "Marianos Lakeshore East"
    button_label: str
    logo_src: str
    logo_url: str
    logo_alt: str


def parse_header_store(tree: LexborHTMLParser, sel: Selectors = DEFAULT_SELECTORS) -> HeaderStore:
    btn = tree.css_first(sel.current_modality)
    modality_node = tree.css_first(sel.current_modality_type)
    modality_text = ""
    if modality_node is not None:
        # The first child span holds the modality word ("Pickup"); css_first() would match the node itself.
        first = next((c for c in modality_node.iter() if c.tag == "span"), None)
        modality_text = text_of(first)
    logo = tree.css_first(sel.header_logo)
    src = (logo.attributes.get("src") or "") if logo is not None else ""
    return HeaderStore(
        modality_text=modality_text,
        vanity_name=text_of(tree.css_first(sel.current_vanity_name)),
        button_label=collapse_ws(btn.attributes.get("aria-label")) if btn is not None else "",
        logo_src=src if not src.startswith("data:") else "data:",
        logo_url=observable_image_url(src),
        logo_alt=collapse_ws(logo.attributes.get("alt")) if logo is not None else "",
    )


@dataclass
class PageParse:
    cards: list[CardObservation] = field(default_factory=list)
    drawers: list[OfferDrawer] = field(default_factory=list)
    coupons: list[CouponCardObservation] = field(default_factory=list)
    header: HeaderStore | None = None


def parse_page(html: str, sel: Selectors = DEFAULT_SELECTORS) -> PageParse:
    tree = LexborHTMLParser(html)
    return PageParse(
        cards=parse_cards(tree, sel),
        drawers=parse_drawers(tree, sel),
        coupons=parse_coupon_cards(tree, sel),
        header=parse_header_store(tree, sel),
    )


def unique_by_upc(cards: Iterable[CardObservation]) -> dict[str, list[CardObservation]]:
    """Group placements by UPC (never by title: the same title can have several UPCs)."""
    groups: dict[str, list[CardObservation]] = {}
    for card in cards:
        if card.upc:
            groups.setdefault(card.upc, []).append(card)
    return groups
