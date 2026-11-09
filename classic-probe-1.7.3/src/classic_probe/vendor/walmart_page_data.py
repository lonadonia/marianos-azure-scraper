"""Read Walmart's server-rendered page data (``<script id="__NEXT_DATA__">``) offline.

Walmart's pages are Next.js pages: the server embeds the page's data as JSON, so a listing page's
products, prices, unit prices, fulfillment, sellers and pagination are in the document itself, without
running the page's scripts. Field names follow Walmart's ``searchResult.itemStacks[].items[]`` shape;
every lookup tolerates a missing key, and what a page does not hold stays unknown (empty), never
guessed. Display text (price strings, unit prices, badge texts) is kept exactly as shown.

Three price layouts are read: nested objects (``priceInfo.currentPrice.priceString``,
``priceInfo.wasPrice.priceString``, ``priceInfo.unitPrice.priceString``; product pages), flat display
strings (``priceInfo.linePrice``, ``priceInfo.wasPrice``, ``priceInfo.unitPrice``,
``priceInfo.priceRangeString``), and price lines (``priceInfo.priceDetails.priceLines``, the layout of
live listing pages on 2026-10-21, where the older fields are empty: see :func:`price_lines`). Each price
text keeps the path it was read from and the change made to it (:class:`ValueSource`), so a record's
provenance names the field actually read (release 1.3.1; 1.3.0 named ``priceInfo.currentPrice|linePrice``
and ``priceInfo.unitPrice`` whichever layout supplied the value).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser

BASE_URL = "https://www.walmart.com"
_NEXT_DATA = re.compile(r"<script[^>]*\bid=[\"']__NEXT_DATA__[\"'][^>]*>(?P<json>.*?)</script>", re.S | re.I)
_PRODUCT_PATH = re.compile(r"^/ip/(?:[^/?#]+/)?(?P<id>\d+)")
_DIGITS = re.compile(r"^\d{8,14}$")
SEARCH_RESULT_PATH = "props.pageProps.initialData.searchResult"


class PageDataMissing(ValueError):
    """The document has no readable ``__NEXT_DATA__`` (a challenge page, an error page, a new layout)."""


def next_data(html: str) -> dict[str, Any]:
    m = _NEXT_DATA.search(html)
    if m is None:
        raise PageDataMissing("no __NEXT_DATA__ script in the page")
    try:
        data = json.loads(m.group("json"))
    except ValueError as exc:
        raise PageDataMissing(f"__NEXT_DATA__ is not JSON: {exc}") from None
    if not isinstance(data, dict):
        raise PageDataMissing("__NEXT_DATA__ is not an object")
    return data


def get(obj: Any, *path: str | int) -> Any:
    for key in path:
        if isinstance(key, int):
            if not isinstance(obj, list) or not -len(obj) <= key < len(obj):
                return None
            obj = obj[key]
        else:
            if not isinstance(obj, Mapping):
                return None
            obj = obj.get(key)
    return obj


def text(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    return " ".join(str(value).split())


def walk(obj: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every (JSON path, value) pair, depth first."""
    yield path, obj
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def initial_data(nd: Mapping[str, Any]) -> Mapping[str, Any]:
    d = get(nd, "props", "pageProps", "initialData")
    return d if isinstance(d, Mapping) else {}


def search_result(nd: Mapping[str, Any]) -> Mapping[str, Any] | None:
    sr = get(initial_data(nd), "searchResult")
    return sr if isinstance(sr, Mapping) else None


def listing_identity(nd: Mapping[str, Any]) -> tuple[str, list[str]]:
    """A listing page's own name (``searchResult.catInfo.name``) and the category ids of its breadcrumb
    (``searchResult.breadCrumb[].id``, e.g. ``1115193`` then ``1115193_1071967``), as the page states them."""
    sr = search_result(nd) or {}
    info = sr.get("catInfo")
    name = text(info.get("name")) if isinstance(info, Mapping) else ""
    crumbs = sr.get("breadCrumb")
    ids = (
        [text(c.get("id")) for c in crumbs if isinstance(c, Mapping) and text(c.get("id"))]
        if isinstance(crumbs, list)
        else []
    )
    return name, ids


def absolute(href: str, base: str = BASE_URL) -> str:
    """``href`` as an absolute URL on the page's own site (``base``: scheme and host)."""
    return urljoin(base.rstrip("/") + "/", href) if href else ""


def item_id_from_url(url: str) -> str:
    m = _PRODUCT_PATH.match(urlsplit(url).path)
    return m.group("id") if m else ""


def page_url(url: str, page: int) -> str:
    """The listing's result page ``page`` as Walmart links it (``page=N``; page 1 is the URL itself)."""
    if page <= 1:
        return url
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
    query.append(("page", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def listing_id(url: str) -> str:
    """A listing's own ID: the last segment of its path (``/browse/food/milk/976759_9176907``)."""
    segs = [s for s in urlsplit(url).path.split("/") if s]
    return segs[-1] if segs else ""


# -- products -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Fulfillment:
    kind: str  # PICKUP | DELIVERY | SHIPPING | …, as the page states it
    store_id: str  # the store the line is for ("" when the page states none)


@dataclass(frozen=True)
class VariantRef:
    """Another item a tile offers as one of its options (``variantCriteria[].variantList[]``): its own
    Walmart item id and product link as the tile gives them. Only these source-provided references are
    followed; a "more sizes" label alone names no item."""

    item_id: str
    url: str
    criterion: str  # the option's dimension as given ("size", "multipack_quantity", "material")
    value: str  # the option's name as displayed ("5 lbs", "3", "Pumpkin Light")
    availability: str  # the option's availabilityStatus as given


def variant_refs(item: Mapping[str, Any], base: str = BASE_URL) -> tuple[VariantRef, ...]:
    own = text(item.get("usItemId"))
    out: dict[str, VariantRef] = {}
    for crit in item.get("variantCriteria") or []:
        if not isinstance(crit, Mapping):
            continue
        dim = text(crit.get("name")) or text(crit.get("id"))
        for v in crit.get("variantList") or []:
            if not isinstance(v, Mapping):
                continue
            sel = v.get("selectedProduct")
            sel = sel if isinstance(sel, Mapping) else {}
            href = text(sel.get("canonicalUrl")) or text(v.get("canonicalUrl"))
            vid = (
                text(sel.get("usItemId"))
                or text(v.get("usItemId"))
                or (item_id_from_url(href) if href else "")
            )
            if not vid or vid == own or not vid.isdigit() or not href:
                continue
            out.setdefault(
                vid,
                VariantRef(
                    vid,
                    absolute(href, base),
                    dim,
                    text(v.get("displayName")) or text(v.get("name")),
                    text(v.get("availabilityStatus")).upper(),
                ),
            )
    return tuple(out.values())


AS_GIVEN = "as given"
DOLLAR_PREFIXED = "'$' prefixed to the line's bare amount"
RANGE_JOINED = "the LOW_PRICE and HIGH_PRICE amounts, each '$' prefixed when bare, joined with ' - '"
RANGE_AS_JSON = "the object written as JSON with sorted keys (it has no display string)"


@dataclass(frozen=True)
class ValueSource:
    """Where in an item's data a displayed text was read: its exact JSON path below the item, the price
    line it belongs to (``lineType=CURRENT_PRICE, key=PRICE``; "" outside the price lines) and the change
    made to the value before it was kept."""

    path: str  # below the item ("priceInfo.priceDetails.priceLines[0].values[0].value")
    selector: str = ""
    transform: str = AS_GIVEN


@dataclass(frozen=True)
class WalmartItem:
    """One product placement of a listing page, as the page's data states it."""

    path: str  # JSON path of the item in __NEXT_DATA__ (source evidence)
    position: int  # order among the page's products
    item_id: str  # usItemId: Walmart's id of this exact item (size, pack and variant)
    product_id: str  # Walmart's catalogue product id, when given
    name: str
    brand: str
    url: str  # absolute product URL, as linked (canonicalUrl)
    image_url: str  # as given (imageInfo.thumbnailUrl)
    upc: str  # only when the page states a UPC; never derived from an item id
    price_string: str  # current price as displayed ("$3.12"), "" when none
    price_value: str  # the same price as data, for a cross-check
    was_price_string: str  # struck-through price ("$4.98") when shown
    price_range: str  # displayed range for several options ("$3.97 - $5.97"), "" when none
    unit_price_string: str  # price per measure as displayed ("16.0 ¢/oz"), "" when not shown
    savings_text: str  # displayed savings line, if any
    price_codes: tuple[str, ...]  # price display codes that are set (rollback, strikethrough, …)
    sales_unit: str  # salesUnitType (a product page: salesUnit): EACH | WEIGHT | EACH_WEIGHT | …
    weight_priced: bool  # the final cost depends on the weight (``weight_priced_by`` says what states it)
    badges: tuple[tuple[str, str], ...]  # displayed badges as (key, text)
    promo_texts: tuple[str, ...]  # displayed promotion texts outside the badges
    fulfillment: tuple[Fulfillment, ...]
    fulfillment_texts: tuple[str, ...]  # displayed fulfillment lines ("Pickup today")
    seller_name: str
    seller_id: str
    availability: str  # IN_STOCK | OUT_OF_STOCK | …
    availability_display: str
    sponsored: bool
    variant_count: int
    raw_keys: tuple[str, ...] = field(default_factory=tuple)  # the item's own keys (layout drift check)
    average_weight: str = ""  # averageWeight as given (a source size field; empty on the listings read)
    # Structured promotion data without displayed wording (promoDiscount): kept for the log only.
    promo_structured: tuple[dict[str, Any], ...] = ()
    # Other items the tile offers as options (sizes, packs): followed by the run's follow-up task.
    variants: tuple[VariantRef, ...] = ()
    # Where each price text was read and how it was changed (None when the text is empty).
    price_source: ValueSource | None = None
    was_price_source: ValueSource | None = None
    unit_price_source: ValueSource | None = None
    price_range_source: ValueSource | None = None
    # sellerType as given (INTERNAL | EXTERNAL): product pages state it, listing tiles do not.
    seller_type: str = ""
    # Walmart's wording next to the price that qualifies it ("each (est.)": the price of one piece is an
    # estimate, its final cost depends on its weight; "/ 0.14lb"), as given, and where it was read; "" when
    # the page shows none (release 1.3.1).
    price_condition: str = ""
    price_condition_source: ValueSource | None = None
    # What in the item's data states that its final cost depends on the weight (release 1.3.1): its sales
    # unit (WEIGHT, or EACH_WEIGHT: sold by the piece, charged by weight), a SOLD_BY_WEIGHT price line (it
    # carries no value) or a finalCostByWeight code. Release 1.3.0 read the code and the WEIGHT unit only:
    # a result tile states neither for an EACH_WEIGHT item, so "each (est.)" prices were taken as fixed.
    weight_priced_by: tuple[str, ...] = ()

    @property
    def badge_texts(self) -> tuple[str, ...]:
        return tuple(t for _, t in self.badges)


def _price_text(info: Mapping[str, Any], nested: str, *flat: str) -> tuple[str, str]:
    """A displayed price text and its path below ``priceInfo`` (("", "") when there is none): the nested
    object's ``priceString`` or ``priceDisplay``, else the first non-empty flat string."""
    v = info.get(nested)
    if isinstance(v, Mapping):
        for key in ("priceString", "priceDisplay"):
            t = text(v.get(key))
            if t:
                return t, f"{nested}.{key}"
        return "", ""
    for key in (nested, *flat):
        t = text(info.get(key)) if isinstance(info.get(key), str) else ""
        if t:
            return t, key
    return "", ""


def price_lines(info: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """``priceInfo.priceDetails.priceLines`` as {line type: {value key: value}} (the layout Walmart's
    listings served on 2026-10-21, with the older display fields empty): ``CURRENT_PRICE``/``PRICE``,
    ``DISCOUNTED_PRICE``/``PRICE`` with ``COMPARISON``/``WAS_PRICE`` (a sale), ``UNIT_PRICE``,
    ``OPTIONS``/``LOW_PRICE`` ("options from"), ``OPTIONS_RANGE`` (low and high), ``SHIPPING`` and
    subscription lines. Values are kept as given ("22.97", "37.8 ¢/count")."""
    return {kind: {key: v for key, (v, _) in vals.items()} for kind, vals in price_line_values(info).items()}


def price_line_types(info: Mapping[str, Any]) -> tuple[str, ...]:
    """Every price line's type, in order, with or without values (``SOLD_BY_WEIGHT`` carries none)."""
    details = info.get("priceDetails")
    lines = details.get("priceLines") if isinstance(details, Mapping) else None
    return tuple(
        kind
        for line in lines or []
        if isinstance(line, Mapping) and (kind := text(line.get("lineType")).upper())
    )


def price_line_values(info: Mapping[str, Any]) -> dict[str, dict[str, tuple[str, str]]]:
    """:func:`price_lines` with each value's path below ``priceInfo``
    (``priceDetails.priceLines[1].values[0].value``); a later line of the same type and key wins."""
    details = info.get("priceDetails")
    lines = details.get("priceLines") if isinstance(details, Mapping) else None
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for i, line in enumerate(lines or []):
        if not isinstance(line, Mapping):
            continue
        kind = text(line.get("lineType")).upper()
        values = {
            text(v.get("key")).upper(): (
                text(v.get("value")),
                f"priceDetails.priceLines[{i}].values[{j}].value",
            )
            for j, v in enumerate(line.get("values") or [])
            if isinstance(v, Mapping) and text(v.get("value"))
        }
        if kind and values:
            out.setdefault(kind, {}).update(values)
    return out


def _line_source(kind: str, key: str, value: tuple[str, str]) -> tuple[str, ValueSource]:
    """A price line's value as displayed ("22.97" -> "$22.97"), and where it was read."""
    shown = _amount(value[0])
    change = DOLLAR_PREFIXED if shown != value[0] else AS_GIVEN
    return shown, ValueSource(f"priceInfo.{value[1]}", f"lineType={kind}, key={key}", change)


def _info_source(path: str) -> ValueSource | None:
    return ValueSource(f"priceInfo.{path}") if path else None


def _amount(value: str) -> str:
    """A price line's amount as Walmart displays it ("22.97" -> "$22.97"); other text unchanged."""
    return f"${value}" if re.fullmatch(r"\d+(?:\.\d{1,2})?", value) else value


def _member_text(m: Mapping[str, Any]) -> str:
    """A badge member's displayed text: ``text`` (+ ``slaText``), or its ``content`` TEXT parts."""
    t = " ".join(p for p in (text(m.get("text")), text(m.get("slaText"))) if p)
    if t:
        return t
    parts = [
        text(c.get("value"))
        for c in m.get("content") or []
        if isinstance(c, Mapping) and text(c.get("type")).upper() == "TEXT" and text(c.get("value"))
    ]
    return " ".join(parts)


def _badges(item: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    out: list[tuple[str, str]] = []
    b = item.get("badges")
    if isinstance(b, Mapping):
        for group in ("flags", "tags", "groups", "groupsV2"):
            for x in b.get(group) or []:
                if not isinstance(x, Mapping):
                    continue
                t = text(x.get("text"))
                if t:
                    out.append((text(x.get("key")) or text(x.get("id")), t))
                for m in x.get("members") or []:
                    if isinstance(m, Mapping) and _member_text(m):
                        key = text(m.get("key")) or text(m.get("id")) or text(m.get("memId"))
                        out.append((key, _member_text(m)))
    for x in item.get("flags") or []:  # older layouts
        if isinstance(x, Mapping) and text(x.get("text")):
            out.append((text(x.get("key")), text(x.get("text"))))
    return tuple(dict.fromkeys(out))


_PROMO_KEYS = ("promoData", "promoDiscount", "promotion", "promotions", "offerPromotion", "rewards")
# Keys of a promotion object whose strings are its displayed wording or terms.
_PROMO_TEXT_KEYS = (
    "text",
    "message",
    "label",
    "title",
    "description",
    "display",
    "terms",
    "condition",
    "eligib",
    "disclaimer",
    "limit",
    "expir",
    "valid",
)


def _promo_texts(item: Mapping[str, Any]) -> tuple[str, ...]:
    """Displayed promotion wording and terms outside the badges (multi-buy, coupons, rewards, rebates), read
    only inside the item's promotion objects. Long terms are kept whole: their quantity, membership, limit,
    date and fulfillment conditions are part of the offer (only links are left out)."""
    out: list[str] = []
    for key in _PROMO_KEYS:
        for path, v in walk(item.get(key)):
            last = path.rsplit(".", 1)[-1].lower()
            if not isinstance(v, str) or not v.strip() or v.startswith(("http", "/", "walmart://")):
                continue
            if any(w in last for w in _PROMO_TEXT_KEYS):
                out.append(text(v))
    return tuple(dict.fromkeys(out))


def _promo_structured(item: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Promotion objects the item carries (``promoDiscount``: an amount, a minimum, limits), as given."""
    v = item.get("promoDiscount")
    if isinstance(v, Mapping) and any(x not in (None, False, "", 0, []) for x in v.values()):
        return ({"key": "promoDiscount", **{str(k): x for k, x in v.items()}},)
    return ()


def parse_item(item: Mapping[str, Any], path: str, position: int, base: str = BASE_URL) -> WalmartItem | None:
    """``None`` for placements that are not products (ads without an item, banners)."""
    url = absolute(text(item.get("canonicalUrl")), base)
    item_id = text(item.get("usItemId")) or item_id_from_url(url)
    name = text(item.get("name"))
    if not item_id or not name:
        return None
    raw_info = item.get("priceInfo")
    info: Mapping[str, Any] = raw_info if isinstance(raw_info, Mapping) else {}
    current = info.get("currentPrice")
    rng = info.get("priceRange")
    raw_codes = info.get("priceDisplayCodes")
    codes: Mapping[str, Any] = raw_codes if isinstance(raw_codes, Mapping) else {}
    upc = text(item.get("upc"))
    fulfil = tuple(
        Fulfillment(text(get(f, "fulfillment")).upper(), text(get(f, "storeId")))
        for f in item.get("fulfillmentSummary") or []
        if isinstance(f, Mapping) and text(get(f, "fulfillment"))
    )
    lines: list[str] = []
    for g in item.get("fulfillmentBadgeGroups") or []:
        if isinstance(g, Mapping):
            line = " ".join(t for t in (text(g.get("text")), text(g.get("slaText"))) if t)
            if line:
                lines.append(line)
    for x in item.get("fulfillmentBadges") or []:
        if isinstance(x, Mapping) and (text(x.get("text")) or text(x.get("label"))):
            lines.append(text(x.get("text")) or text(x.get("label")))
    raw_avail = item.get("availabilityStatusV2")
    avail: Mapping[str, Any] = raw_avail if isinstance(raw_avail, Mapping) else {}
    variants = item.get("variantCount")
    # A result tile states salesUnitType, a product page salesUnit (the same values).
    sales_unit = (text(item.get("salesUnitType")) or text(item.get("salesUnit"))).upper()
    range_text = text(info.get("priceRangeString"))
    range_src = _info_source("priceRangeString" if range_text else "")
    if not range_text and isinstance(rng, Mapping) and rng:
        range_text = text(rng.get("priceString"))
        range_src = _info_source("priceRange.priceString")
        if not range_text:
            range_text, range_src = (
                json.dumps(rng, sort_keys=True),
                ValueSource("priceInfo.priceRange", "", RANGE_AS_JSON),
            )
    price_string, at = _price_text(info, "currentPrice", "linePriceDisplay", "linePrice", "itemPrice")
    price_src = _info_source(at)
    was_string, at = _price_text(info, "wasPrice")
    was_src = _info_source(at)
    unit_string, at = _price_text(info, "unitPrice")
    unit_src = _info_source(at)
    code_list = sorted(str(k) for k, v in codes.items() if v not in (None, False, "", 0))
    plines = price_line_values(info)
    if plines:
        # The price-lines layout: the item's own price (a discounted price is the current one), the
        # struck-through comparison price, the displayed unit price, a range only when no single price.
        own_kind = "DISCOUNTED_PRICE" if plines.get("DISCOUNTED_PRICE", {}).get("PRICE") else "CURRENT_PRICE"
        own = plines.get(own_kind, {}).get("PRICE")
        if not price_string and own:
            price_string, price_src = _line_source(own_kind, "PRICE", own)
        was = plines.get("COMPARISON", {}).get("WAS_PRICE")
        if not was_string and was:
            was_string, was_src = _line_source("COMPARISON", "WAS_PRICE", was)
        unit = plines.get("UNIT_PRICE", {}).get("UNIT_PRICE")
        if not unit_string and unit:
            unit_string = unit[0]
            unit_src = ValueSource(f"priceInfo.{unit[1]}", "lineType=UNIT_PRICE, key=UNIT_PRICE")
        span = plines.get("OPTIONS_RANGE", {})
        low, high = span.get("LOW_PRICE"), span.get("HIGH_PRICE")
        if not range_text and not own and low and high:
            range_text = f"{_amount(low[0])} - {_amount(high[0])}"
            range_src = ValueSource(
                f"priceInfo.{low[1]} and priceInfo.{high[1]}",
                "lineType=OPTIONS_RANGE, key=LOW_PRICE|HIGH_PRICE",
                RANGE_JOINED,
            )
        code_list = sorted({*code_list, *(f"line:{k}" for k in plines)})
    line_types = price_line_types(info)
    code_list = sorted({*code_list, *(f"line:{k}" for k in line_types)})
    condition, condition_src = "", None
    shown = plines.get("DISPLAY_CONDITION", {}).get("PRICE_DISPLAY_CONDITION") if plines else None
    if shown:
        condition = shown[0]
        condition_src = ValueSource(
            f"priceInfo.{shown[1]}", "lineType=DISPLAY_CONDITION, key=PRICE_DISPLAY_CONDITION"
        )
    else:
        for at, value in (
            ("priceDisplayCodes.priceDisplayCondition", codes.get("priceDisplayCondition")),
            ("priceDisplayCondition", info.get("priceDisplayCondition")),
        ):
            if text(value):
                condition, condition_src = text(value), ValueSource(f"priceInfo.{at}")
                break
    weight_priced_by = tuple(
        what
        for what, stated in (
            (f"sales unit {sales_unit}", sales_unit in ("WEIGHT", "EACH_WEIGHT")),
            ("price line SOLD_BY_WEIGHT", "SOLD_BY_WEIGHT" in line_types),
            ("priceDisplayCodes.finalCostByWeight", bool(codes.get("finalCostByWeight"))),
            ("priceInfo.finalCostByWeight", info.get("finalCostByWeight") is True),
        )
        if stated
    )
    return WalmartItem(
        path=path,
        position=position,
        item_id=item_id,
        product_id=text(item.get("id")),
        name=name,
        brand=text(item.get("brand")),
        url=url,
        image_url=text(get(item, "imageInfo", "thumbnailUrl")) or text(item.get("image")),
        upc=upc if _DIGITS.match(upc) else "",
        price_string=price_string,
        price_value=(text(get(current, "price")) if isinstance(current, Mapping) else "")
        or (text(item.get("price")) if isinstance(item.get("price"), (int, float, str)) else ""),
        was_price_string=was_string,
        price_range=range_text,
        unit_price_string=unit_string,
        savings_text=_price_text(info, "savings")[0],
        price_codes=tuple(code_list),
        sales_unit=sales_unit,
        weight_priced=bool(weight_priced_by),
        badges=_badges(item),
        promo_texts=_promo_texts(item),
        fulfillment=fulfil,
        fulfillment_texts=tuple(dict.fromkeys(lines)),
        # A listing tile names its seller in sellerName; a product page in sellerDisplayName (release 1.3.0
        # read sellerName only, so it never saw a product page's seller).
        seller_name=text(item.get("sellerName")) or text(item.get("sellerDisplayName")),
        seller_id=text(item.get("sellerId")),
        availability=text(avail.get("value")).upper() or text(item.get("availabilityStatus")).upper(),
        availability_display=text(avail.get("display")) or text(item.get("availabilityStatusDisplayValue")),
        sponsored=bool(item.get("isSponsoredFlag")) or bool(item.get("isSponsored")),
        variant_count=variants if isinstance(variants, int) and not isinstance(variants, bool) else 0,
        raw_keys=tuple(sorted(str(k) for k in item)),
        average_weight=text(item.get("averageWeight")),
        promo_structured=_promo_structured(item),
        variants=variant_refs(item, base),
        price_source=price_src if price_string else None,
        was_price_source=was_src if was_string else None,
        unit_price_source=unit_src if unit_string else None,
        price_range_source=range_src if range_text else None,
        seller_type=text(item.get("sellerType")).upper(),
        price_condition=condition,
        price_condition_source=condition_src,
        weight_priced_by=weight_priced_by,
    )


class PageShapeUnclear(ValueError):
    """A listing page whose result stack cannot be told from its other item stacks."""


@dataclass(frozen=True)
class ItemStack:
    """One item stack of a listing page (``searchResult.itemStacks[index]``), as the page states it."""

    index: int
    layout: str  # layoutEnum: GRID (the results), CAROUSEL (a module such as "Available for shipping")
    title: str
    count: int | None  # the stack's own count (the listing's total for the result grid)
    entries: int  # items of any kind (products, ad and tile placeholders)
    products: int  # items that are products
    primary: bool  # the listing's results
    # The fulfillment the stack's results are filtered for, as the stack's ``meta.fulfillmentIntent`` states
    # it ("Pickup" for Walmart's Pickup grid; "" when the stack names no filter).
    fulfillment_filter: str = ""


def _stacks(nd: Mapping[str, Any]) -> list[Any]:
    sr = search_result(nd) or {}
    stacks = sr.get("itemStacks")
    return stacks if isinstance(stacks, list) else []


def primary_stacks(nd: Mapping[str, Any]) -> tuple[list[int], str]:
    """The indices of the stacks that hold the listing's results, and the page data that says so.

    A listing page may add other modules as item stacks (live 2026-10-26: an "Available for shipping"
    carousel after the results, with products of other categories and fulfillment). The results are the
    stacks the page names in ``paginationV2.pageProperties.primaryStacksToMatch`` (``isPrimaryStack``,
    ``matchIndex``); a named stack must be a result grid when the page states layouts. Without that list:
    the page's only GRID stack, else its only stack. Anything else raises :class:`PageShapeUnclear`."""
    stacks = _stacks(nd)
    if not stacks:
        return [], "no item stack"
    layouts = [text(s.get("layoutEnum")) if isinstance(s, Mapping) else "" for s in stacks]
    named = get(search_result(nd) or {}, "paginationV2", "pageProperties", "primaryStacksToMatch")
    if isinstance(named, list) and named:
        idx = sorted(
            {
                m["matchIndex"]
                for m in named
                if isinstance(m, Mapping)
                and m.get("isPrimaryStack") is True
                and isinstance(m.get("matchIndex"), int)
                and not isinstance(m.get("matchIndex"), bool)
            }
        )
        if not idx or any(not 0 <= i < len(stacks) for i in idx):
            raise PageShapeUnclear(f"primaryStacksToMatch names no item stack of the page: {named}")
        if any(layouts[i] and layouts[i] != "GRID" for i in idx):
            raise PageShapeUnclear(f"primaryStacksToMatch names a stack that is not a result grid: {named}")
        return idx, "paginationV2.pageProperties.primaryStacksToMatch"
    grids = [i for i, layout in enumerate(layouts) if layout == "GRID"]
    if len(grids) == 1:
        return grids, "the page's only GRID item stack"
    if len(stacks) == 1:
        return [0], "the page's only item stack"
    raise PageShapeUnclear(f"{len(stacks)} item stacks ({layouts}) and none named as the results")


def item_stacks(nd: Mapping[str, Any]) -> list[ItemStack]:
    """Every item stack of the page, the result stacks marked (:func:`primary_stacks`)."""
    primary, _ = primary_stacks(nd)
    out = []
    for i, stack in enumerate(_stacks(nd)):
        stack = stack if isinstance(stack, Mapping) else {}
        items = [x for x in stack.get("items") or [] if isinstance(x, Mapping)]
        out.append(
            ItemStack(
                index=i,
                layout=text(stack.get("layoutEnum")),
                title=text(stack.get("title")),
                count=_num(stack.get("count")),
                entries=len(items),
                products=sum(1 for x in items if text(x.get("__typename")) in ("", "Product")),
                primary=i in primary,
                fulfillment_filter=text(get(stack, "meta", "fulfillmentIntent")),
            )
        )
    return out


def page_items(nd: Mapping[str, Any], base: str = BASE_URL) -> list[WalmartItem]:
    """The listing's results on the page, in page order: the products of its result stacks only
    (:func:`primary_stacks`); the products of other modules on the page are not results of the listing."""
    out: list[WalmartItem] = []
    if search_result(nd) is None:
        return out
    primary, _ = primary_stacks(nd)
    stacks = _stacks(nd)
    for si in primary:
        stack = stacks[si]
        if not isinstance(stack, Mapping):
            continue
        for ii, item in enumerate(stack.get("items") or []):
            if not isinstance(item, Mapping):
                continue
            parsed = parse_item(item, f"{SEARCH_RESULT_PATH}.itemStacks[{si}].items[{ii}]", len(out), base)
            if parsed is not None:
                out.append(parsed)
    return out


def placements(nd: Mapping[str, Any]) -> int:
    """Entries in the page's result stacks, products or not (to tell an empty page from a new layout)."""
    return sum(s.entries for s in item_stacks(nd) if s.primary)


@dataclass(frozen=True)
class Pagination:
    current_page: int | None
    max_page: int | None
    total_count: int | None  # results the page reports for the listing (all pages)
    page_size: int | None
    page_count: int | None = None  # results the page reports for itself (searchResult.count)


def _num(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    return int(v) if isinstance(v, str) and v.isdigit() else None


def pagination(nd: Mapping[str, Any]) -> Pagination:
    sr = search_result(nd) or {}
    raw_p2 = sr.get("paginationV2")
    p2: Mapping[str, Any] = raw_p2 if isinstance(raw_p2, Mapping) else {}
    raw_props = p2.get("pageProperties")
    props: Mapping[str, Any] = raw_props if isinstance(raw_props, Mapping) else {}
    count = _num(sr.get("aggregatedCount")) or _num(sr.get("count"))
    if count is None:
        try:
            results = [s for s in item_stacks(nd) if s.primary]
        except PageShapeUnclear:
            results = []
        if len(results) == 1:
            count = results[0].count
    return Pagination(
        current_page=_num(props.get("page")) or _num(get(nd, "query", "page")) or 1,
        max_page=_num(p2.get("maxPage")),
        total_count=count,
        page_size=_num(sr.get("pageSize")) or _num(props.get("ps")),
        page_count=_num(sr.get("count")),
    )


@dataclass(frozen=True)
class FacetValue:
    """One value of a listing page's own filter facet, as the page states it."""

    facet: str  # the facet's type ("cat_id", "retailer_type", ...)
    facet_name: str  # its displayed name ("Departments", "Retailer")
    id: str
    name: str
    url: str  # absolute listing URL of the value (baseSeoURL), "" when the page gives none
    query: str  # the value's own query string as the page gives it ("...&facet=retailer_type:Walmart")
    path: str  # JSON path of the value


def listing_facets(nd: Mapping[str, Any], base: str = BASE_URL) -> list[FacetValue]:
    """The listing page's own sort-and-filter facets (``contentLayout`` ``allSortAndFilterFacets``, the
    layout of 2026-10-23), every value with its id, name, listing URL and query, in page order."""
    out: list[FacetValue] = []
    for path, node in walk(content_layout(nd)):
        if not (path.endswith("allSortAndFilterFacets") and isinstance(node, list)):
            continue
        for fi, f in enumerate(node):
            if not isinstance(f, Mapping):
                continue
            ftype, fname = text(f.get("type")), text(f.get("name"))
            for vi, v in enumerate(f.get("values") or []):
                if not isinstance(v, Mapping) or not text(v.get("id")):
                    continue
                seo = text(v.get("baseSeoURL"))
                out.append(
                    FacetValue(
                        ftype,
                        fname,
                        text(v.get("id")),
                        text(v.get("name")) or text(v.get("title")),
                        absolute(seo, base) if seo else "",
                        text(v.get("url")),
                        f"{path}[{fi}].values[{vi}]",
                    )
                )
        break  # the first facet module is the listing's own
    return out


def child_categories(nd: Mapping[str, Any], listing: str, base: str = BASE_URL) -> list[FacetValue]:
    """The listing's child categories as its own "Departments" facet names them: ``cat_id`` values whose
    id extends the listing's id (``5427_486190`` → ``5427_486190_1101406``) and that link to a /browse/
    listing. They may overlap one another (a brand category inside a type): their counts are never added
    up; a child's own first page gives its total."""
    return [
        f
        for f in listing_facets(nd, base)
        if f.facet == "cat_id"
        and f.id.startswith(f"{listing}_")
        and urlsplit(f.url).path.startswith("/browse/")
        and listing_id(f.url) == f.id
    ]


# -- subcategories of a category landing page ----------------------------------------------------------


@dataclass(frozen=True)
class SubcategoryLink:
    name: str
    url: str  # absolute /browse/ listing URL, as linked
    path: str  # JSON path where the page lists it


def _link_name(node: Mapping[str, Any]) -> str:
    for key in ("title", "name", "text", "label", "linkText", "displayName", "heading", "alt"):
        t = text(node.get(key))
        if t:
            return t
    return text(get(node, "image", "alt"))


_HREF_KEYS = ("url", "link", "href", "linkUrl", "destinationUrl", "clickThroughUrl", "redirectUrl")


def _link_href(node: Mapping[str, Any]) -> str:
    for v in (get(node, "clickThrough", "value"), *(node.get(k) for k in _HREF_KEYS)):
        t = text(v)
        if t:
            return t
    return ""


def content_layout(nd: Mapping[str, Any]) -> Any:
    """A page's content modules: ``initialData.contentLayout``, or ``initialTempoData.contentLayout``
    (where live category pages keep them, 2026-10-21)."""
    data = initial_data(nd)
    raw_layout = data.get("contentLayout")
    if isinstance(raw_layout, Mapping):
        return raw_layout
    tempo = get(nd, "props", "pageProps", "initialTempoData", "contentLayout")
    return tempo if isinstance(tempo, Mapping) else data


@dataclass(frozen=True)
class NavGroup:
    """A group of a category page's navigation ("Dairy & Eggs") and its links, in page order."""

    name: str
    links: tuple[SubcategoryLink, ...]
    path: str


def category_nav(nd: Mapping[str, Any], base: str = BASE_URL) -> list[NavGroup]:
    """The category page's navigation (``configs.categoriesData``): groups with a name and their links
    (``subCategoryLink.title`` and ``clickThrough.value``), /browse/ and /cp/ alike, in page order."""
    out: list[NavGroup] = []
    for path, node in walk(content_layout(nd)):
        if not (path.endswith("categoriesData") and isinstance(node, list)):
            continue
        for gi, g in enumerate(node):
            if not isinstance(g, Mapping) or not text(g.get("name")):
                continue
            links = []
            for si, s in enumerate(g.get("subcategories") or []):
                link = s.get("subCategoryLink") if isinstance(s, Mapping) else None
                if not isinstance(link, Mapping):
                    continue
                href = _link_href(link)
                title = text(link.get("title")) or _link_name(link)
                if href and title:
                    links.append(
                        SubcategoryLink(title, absolute(href, base), f"{path}[{gi}].subcategories[{si}]")
                    )
            out.append(NavGroup(text(g.get("name")), tuple(links), f"{path}[{gi}]"))
        if out:
            break  # the first navigation module is the page's own
    return out


def subcategory_links(nd: Mapping[str, Any], base: str = BASE_URL) -> list[SubcategoryLink]:
    """The /browse/ listings a category landing page links to, in page order (first sighting wins).

    Landing pages list their subcategories in content modules (``contentLayout``): an entry with a
    display name and a link (``clickThrough.value`` or ``url``) to a /browse/ page."""
    out: dict[str, SubcategoryLink] = {}
    layout: Any = content_layout(nd)
    for path, node in walk(layout):
        if not isinstance(node, Mapping):
            continue
        href = _link_href(node)
        if "/browse/" not in href:
            continue
        name = _link_name(node)
        if not name:
            continue
        url = absolute(href, base)
        key = urlsplit(url).path.rstrip("/")
        if key not in out:
            out[key] = SubcategoryLink(name, url, path)
    return list(out.values())


# -- the page header -----------------------------------------------------------------------------------

_HOME_LINK = 'a[aria-label="Walmart Homepage"]'


def header_logo(html: str, base: str = BASE_URL) -> tuple[str, str]:
    """The retailer logo the page header shows: the image inside a header link named "Walmart Homepage"
    (``link-identifier="walmartLogoDesktop"`` on the pages of 2026-10-21 to 2026-10-24; the mobile link shows
    an icon-font glyph without an address). Returns (absolute image URL, where it was read), or ("", "")
    when the page shows no such image. A protocol-relative address (``//i5.walmartimages.com/...``) is
    resolved against the page's own scheme."""
    tree = LexborHTMLParser(html)
    for a in tree.css(_HOME_LINK):
        img = a.css_first("img")
        src = (img.attributes.get("src") or "").strip() if img is not None else ""
        if src:
            ident = a.attributes.get("link-identifier") or ""
            where = f'{_HOME_LINK}[link-identifier="{ident}"] img@src' if ident else f"{_HOME_LINK} img@src"
            return absolute(src, base), where
    return "", ""


# -- store and fulfillment context ---------------------------------------------------------------------


@dataclass(frozen=True)
class StoreDetails:
    """A store page's own description of the store (its page at /store/<id>)."""

    store_id: str
    name: str
    address_line1: str
    city: str
    state: str
    postal_code: str
    path: str

    @property
    def location_text(self) -> str:
        tail = f"{self.state} {self.postal_code}".strip()
        return ", ".join(p for p in (self.address_line1, self.city, tail) if p)


_ID_KEYS = ("id", "storeId", "storeNumber", "nodeId", "store_id")
_LINE1_KEYS = ("addressLineOne", "address1", "streetAddress", "street", "addressLine1", "line1")
_POSTAL_KEYS = ("postalCode", "zipCode", "zip", "postal_code")


def _first(node: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    return next((t for k in keys if (t := text(node.get(k)))), "")


def store_details(nd: Mapping[str, Any], store_id: str) -> StoreDetails | None:
    """The store ``store_id`` as its store page describes it: an object with that id and an address."""
    for path, node in walk(nd):
        if not isinstance(node, Mapping):
            continue
        sid = _first(node, _ID_KEYS)
        if sid != store_id:
            continue
        addr = node.get("address") if isinstance(node.get("address"), Mapping) else None
        if addr is None:
            continue
        line1 = _first(addr, _LINE1_KEYS)
        postal = _first(addr, _POSTAL_KEYS)
        if not (line1 and postal):
            continue
        return StoreDetails(
            store_id=sid,
            name=text(node.get("displayName")) or text(node.get("name")),
            address_line1=line1,
            city=text(addr.get("city")),
            state=text(addr.get("state")) or text(addr.get("stateOrProvinceCode")),
            postal_code=postal,
            path=path,
        )
    return None


_ADDRESS_TEXT = (
    r"(?P<line1>{house}\s[^\n,]{{2,60}}?),?\s+(?P<city>[A-Za-z .'-]{{2,40}}),\s*"
    r"(?P<state>[A-Z]{{2}})\s+(?P<zip>\d{{5}})"
)


def store_details_from_text(
    page_text: str, store_id: str, house_number: str, name: str
) -> StoreDetails | None:
    """The store as its page *shows* it, when its data names no store object: the address that starts
    with the configured house number, with its city, state and ZIP, as displayed (``name``: the page's own
    heading)."""
    if not house_number.isdigit():
        return None
    m = re.search(_ADDRESS_TEXT.format(house=re.escape(house_number)), page_text)
    if m is None:
        return None
    return StoreDetails(
        store_id=store_id,
        name=name,
        address_line1=" ".join(m.group("line1").split()),
        city=" ".join(m.group("city").split()),
        state=m.group("state"),
        postal_code=m.group("zip"),
        path="(page text)",
    )


@dataclass(frozen=True)
class PageLocation:
    """The page's own location context (``pageMetadata.location``): the store its prices are for and
    the fulfillment intent the page is shown in (PICKUP after a Pickup store selection)."""

    path: str
    store_id: str
    postal_code: str
    intent: str


_LOCATION_PATHS = (
    ("props", "pageProps", "initialData", "pageMetadata", "location"),
    ("props", "pageProps", "initialData", "data", "contentLayout", "pageMetadata", "location"),
    ("props", "pageProps", "initialData", "contentLayout", "pageMetadata", "location"),
    ("props", "pageProps", "initialTempoData", "contentLayout", "pageMetadata", "location"),
)


def page_location(nd: Mapping[str, Any]) -> PageLocation | None:
    for path in _LOCATION_PATHS:
        node = get(nd, *path)
        if isinstance(node, Mapping) and text(node.get("storeId")):
            return PageLocation(
                ".".join(path),
                text(node.get("storeId")),
                text(node.get("postalCode")),
                (text(node.get("intent")) or text(node.get("fulfillmentIntent"))).upper(),
            )
    return None


@dataclass(frozen=True)
class StoreContext:
    """An object in the page data that names a store together with location or fulfillment fields."""

    path: str
    store_id: str
    postal_code: str
    fulfillment: str


_STORE_KEYS = ("storeId", "nodeId", "accessPointStoreId", "preferredStoreId", "assortmentStoreId")
_ZIP_KEYS = ("postalCode", "zipCode", "zip")
_INTENT_KEYS = ("intent", "fulfillmentIntent", "accessPointType", "fulfillmentType")


def store_contexts(nd: Mapping[str, Any]) -> list[StoreContext]:
    """Page-level objects that name a store with a ZIP or a fulfillment (items' own fulfillment lines are
    read by :func:`page_items`). Recorded as evidence of the page's store context."""
    out: list[StoreContext] = []
    for path, node in walk(nd):
        if not isinstance(node, Mapping) or "itemStacks" in path:
            continue
        store_id = next((text(node.get(k)) for k in _STORE_KEYS if text(node.get(k))), "")
        if not store_id.isdigit():
            continue
        postal = next((text(node.get(k)) for k in _ZIP_KEYS if text(node.get(k))), "")
        intent = next((text(node.get(k)).upper() for k in _INTENT_KEYS if text(node.get(k))), "")
        if postal or intent:
            out.append(StoreContext(path, store_id, postal, intent))
    return out


# -- product pages ------------------------------------------------------------------------------------

_GTIN = re.compile(r"^\d{12,14}$")
_LD_JSON = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(?P<json>.*?)</script>', re.S | re.I
)
IDENTIFIER_KEYS = ("upc", "gtin13", "gtin12", "gtin14", "gtin")


@dataclass(frozen=True)
class ProductIdentifier:
    """A UPC/GTIN a product page states for one item, with where it was read (empty when none), and what
    the page is: whether it carries Walmart's page data, whether that data names the requested item, and
    which item the page itself is for (a page for another item or variant must not lend it its UPC)."""

    value: str
    source: str  # "page_data" | "json_ld" | ""
    path: str
    candidates: tuple[tuple[str, str], ...] = ()  # every (path, value) seen, for the supporting log
    page_data: bool = True  # the page carries Walmart's __NEXT_DATA__
    matched: bool = False  # an object of the page data names the requested item (usItemId)
    page_item: str = ""  # the item the page is for (initialData.data.product.usItemId)


def product_identifier(html: str, item_id: str) -> ProductIdentifier:
    """The UPC or GTIN the product page of ``item_id`` states: first in the page data (an object whose
    ``usItemId`` is the item, keys ``upc``, ``gtin13``, ``gtin12``, ``gtin14``, ``gtin``), else in the page's
    JSON-LD ``Product``. Only 12 to 14 digits, exactly as written (leading zeros kept); never the item id."""
    candidates: list[tuple[str, str]] = []
    try:
        nd: Mapping[str, Any] = next_data(html)
        has_data = True
    except PageDataMissing:
        nd, has_data = {}, False
    product = nd.get("props", {}).get("pageProps", {}).get("initialData", {}).get("data", {}).get("product")
    page_item = text(product.get("usItemId")) if isinstance(product, Mapping) else ""
    matched = False
    for path, value in walk(nd):
        if isinstance(value, Mapping) and text(value.get("usItemId")) == item_id:
            matched = True
            for key in IDENTIFIER_KEYS:
                v = text(value.get(key))
                if v:
                    candidates.append((f"{path}.{key}", v))
    if page_item and page_item != item_id:
        # The page is another item's (a redirect to another variant, or a replacement listing): its
        # identifiers are not this item's, even where its data mentions this item among the variants.
        return ProductIdentifier("", "", "", tuple(candidates), has_data, matched, page_item)
    for i, m in enumerate(_LD_JSON.finditer(html)):
        try:
            data = json.loads(m.group("json"))
        except ValueError:
            continue
        for path, value in walk(data, f"ld[{i}]"):
            if isinstance(value, Mapping) and str(value.get("@type", "")).lower() == "product":
                for key in IDENTIFIER_KEYS:
                    v = text(value.get(key))
                    if v:
                        candidates.append((f"{path}.{key}", v))
    for path, v in candidates:
        if _GTIN.match(v) and v != item_id:
            return ProductIdentifier(
                v,
                "json_ld" if path.startswith("ld[") else "page_data",
                path,
                tuple(candidates),
                has_data,
                matched,
                page_item,
            )
    return ProductIdentifier("", "", "", tuple(candidates), has_data, matched, page_item)


# -- product pages read for a product (follow-ups) -----------------------------------------------------

PRODUCT_PATH = "props.pageProps.initialData.data.product"


@dataclass(frozen=True)
class ProductPage:
    """What a product page's own data (``initialData.data.product``) says about its item: the item as a
    record source (the listing-tile reader applies: name, brand, prices, unit price, fulfillment lines,
    seller), the store and fulfillment intent the page is shown for (``product.location``), the category
    path Walmart files it under, and the fulfillment options it displays."""

    item: WalmartItem | None
    page_item: str  # the item the page is for (usItemId)
    store_ids: tuple[str, ...]  # product.location.storeIds
    pickup_store: str  # product.location.pickupLocation.storeId
    postal_code: str
    intent: str  # product.location.intent (PICKUP after a Pickup store selection)
    category_ids: tuple[str, ...]  # product.category.categoryPathId split on ":" (as given)
    category_names: tuple[str, ...]  # product.category.path[].name
    category_urls: tuple[str, ...]  # product.category.path[].url
    options: tuple[tuple[str, str, str], ...]  # fulfillmentOptions: (type, availabilityStatus, locationText)
    offer_type: str
    seller_type: str

    def under(self, listing_id: str, listing_name: str = "") -> tuple[bool, str]:
        """Whether the page files the item under a listing (its id ``976759_976793_9756351``: every id in
        order in the category path, or in a breadcrumb link; else its name as a breadcrumb). Returns the
        decision and the evidence used."""
        want = [x for x in listing_id.split("_") if x]
        ids = [x for x in self.category_ids if x]
        if want and ids:
            n = len(want)
            hit = any(ids[i : i + n] == want for i in range(len(ids) - n + 1))
            return hit, "categoryPathId " + ":".join(ids)
        for url in self.category_urls:
            if listing_id and listing_id in url:
                return True, f"breadcrumb link {url}"
        names = [n.casefold() for n in self.category_names]
        if listing_name and names:
            return listing_name.casefold() in names, "breadcrumb " + " > ".join(self.category_names)
        return False, "the page states no category path"


def product_page(nd: Mapping[str, Any], base: str = BASE_URL) -> ProductPage | None:
    product = get(nd, "props", "pageProps", "initialData", "data", "product")
    if not isinstance(product, Mapping) or not text(product.get("usItemId")):
        return None
    loc = product.get("location")
    loc = loc if isinstance(loc, Mapping) else {}
    raw_ids = loc.get("storeIds")
    store_ids = tuple(text(x) for x in raw_ids if text(x)) if isinstance(raw_ids, list) else ()
    cat = product.get("category")
    cat = cat if isinstance(cat, Mapping) else {}
    path = [x for x in cat.get("path") or [] if isinstance(x, Mapping)]
    options = tuple(
        (
            (text(o.get("type")) or text(o.get("__typename"))).upper(),
            text(o.get("availabilityStatus")).upper(),
            text(o.get("locationText")),
        )
        for o in product.get("fulfillmentOptions") or []
        if isinstance(o, Mapping)
    )
    return ProductPage(
        item=parse_item(product, PRODUCT_PATH, 0, base),
        page_item=text(product.get("usItemId")),
        store_ids=store_ids,
        pickup_store=text(get(loc, "pickupLocation", "storeId")),
        postal_code=text(loc.get("postalCode")),
        intent=text(loc.get("intent")).upper(),
        category_ids=tuple(x for x in text(cat.get("categoryPathId")).split(":") if x),
        category_names=tuple(text(x.get("name")) for x in path if text(x.get("name"))),
        category_urls=tuple(text(x.get("url")) for x in path if text(x.get("url"))),
        options=options,
        offer_type=text(product.get("offerType")).upper(),
        seller_type=text(product.get("sellerType")).upper(),
    )
