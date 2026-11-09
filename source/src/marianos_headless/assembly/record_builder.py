"""Assemble the 22-field record from displayed observations (brief §5.9, §6.2, §6.4)."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from marianos_headless.assembly.exclusions import (
    approx_weight_wording,
    exclusion_reasons,
    is_plu_code,
    size_slot_is_unit_price,
    weight_range_in,
)
from marianos_headless.assembly.offers import (
    ClassifiedOffer,
    DealFields,
    OfferKind,
    OfferObservation,
    derive_deal_fields,
    restriction_reason,
    states_bundle_price,
)
from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.size_evidence import (
    SizeAssessment,
    SizeResolution,
    assess_size,
    package_weight_measure,
    price_basis_measure,
)
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.schema import ALWAYS_EMPTY, build_record, format_violations, shape_violations
from marianos_headless.core.settings import RecordSettings
from marianos_headless.core.text import collapse_ws
from marianos_headless.sites.marianos.dom_parsers import PriceDisplay, PriceDisplayKind

# Text the size slot sometimes shows that is not a size: the name of a product picture's view (the
# retailer's own size field holds "Front" for some products, live 2026-10-20) or a control's label.
_PICTURE_VIEWS = frozenset(
    {"front", "back", "left", "right", "top", "bottom", "side", "angle", "detail", "nutrition",
     "ingredients", "label", "image", "photo", "picture", "default", "main", "hero", "thumbnail"}
)  # fmt: skip
_CONTROL_LABEL = re.compile(
    r"^(?:sign in(?: to (?:add|clip))?|add(?: to (?:cart|list))?|view (?:offer|details)"
    r"|see (?:details|options|more)|shop (?:all )?items?|select|\d+ more (?:sizes?|options?|flavors?))$",
    re.I,
)
# Release 1.9.0rc2: a text that states no quantity is not a pack size: "N/A" (the product data's own "not
# applicable", run Q2 and stage O2: 0002310032784) and a unit named alone ("Count", Q2: 0019283330664).
_NO_QUANTITY = re.compile(r"^(?:n/?a|not applicable|count|ct)$", re.I)
NO_QUANTITY = "states no quantity"
# Release 1.9.0rc3: the digital fields' reason on a tile when no coupon is known (``no_coupon_reason``).
COUPON_UNKNOWN = "whether a digital coupon applies is unknown"


def size_text_problem(size_text: str, title: str = "") -> str:
    """Why the text in the size slot is not a size ("" when it can be one)."""
    text = collapse_ws(size_text)
    if not text:
        return ""
    if text.casefold() in _PICTURE_VIEWS:
        return f"the size slot shows {text!r}, the name of a product picture's view, not a size"
    if _CONTROL_LABEL.match(text):
        return f"the size slot shows {text!r}, a control's label, not a size"
    if title and text.casefold() == collapse_ws(title).casefold():
        return "the size slot repeats the product name"
    if _NO_QUANTITY.match(text):
        return f"the size is given as {text!r}, which {NO_QUANTITY}: not a pack size"
    return ""


class RecordStatus(StrEnum):
    """A record's disposition (release 1.4.0 separates identity, price and availability).

    ``VALID``: a verified product with a fixed displayed price that agrees with its own data for the store.
    ``ELIGIBLE_UNPRICED``: a verified product of the store's assortment that shows no fixed current price
    (unavailable, "Prices May Vary", or only an estimated item price): a valid identity, exported with
    empty prices. ``PRICE_CONFLICT``: the displayed price differs from the product's own data for the store:
    both are kept, the displayed one is exported, and it is not counted as verified. ``EXPORTED_NOT_VALID``:
    an incomplete identity (no title, link or category), or (release 1.8.0rc2) a displayed price that the
    product's own data states for no store (``PRICE_STORE_NOT_STATED``): exported as displayed, not counted as
    valid."""

    VALID = "valid"
    ELIGIBLE_UNPRICED = "eligible_unpriced"
    PRICE_CONFLICT = "price_conflict"
    EXPORTED_NOT_VALID = "exported_not_valid"
    EXCLUDED = "excluded"
    QUARANTINED = "quarantined"


EXPORTED_RECORD_STATUSES = (
    RecordStatus.VALID,
    RecordStatus.ELIGIBLE_UNPRICED,
    RecordStatus.PRICE_CONFLICT,
    RecordStatus.EXPORTED_NOT_VALID,
)


def availability_of(check: SourceCheck | None) -> dict[str, str]:
    """The product's availability at the store as its own data states it. A missing price, "Prices May
    Vary" or a missing search result is not evidence of stock: without a stated stock level it is
    ``unknown``."""
    level = (check.stock_level if check is not None else "") or ""
    if check is None or check.response is None:
        return {"availability": "unknown", "source": "no product data was read for it"}
    if not level:
        return {"availability": "unknown", "source": "the product data states no stock level for the store"}
    cls = {
        "HIGH": "in_stock",
        "LOW": "low_stock",
        "TEMPORARILY_OUT_OF_STOCK": "out_of_stock",
    }.get(level.upper(), "unknown")
    return {"availability": cls, "source": f"product data inventory stockLevel {level}"}


@dataclass(frozen=True)
class StoreFields:
    zipcode: str
    store_name: str
    store_location: str
    store_logo: str


@dataclass(frozen=True)
class FieldSource:
    source: str  # dom_card | dom_pdp | dom_header | json_products | json_coupons | state | config
    ref: str  # selector or JSON path
    fetch_id: str | None = None
    response_sha256: str | None = None
    observed_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "selector_or_path": self.ref,
            "fetch_id": self.fetch_id,
            "response_sha256": self.response_sha256,
            "observed_at": self.observed_at,
        }


def truncation_explains(displayed: str, stated: str) -> bool:
    """Whether a displayed price equals the stated one truncated to cents in binary floating point (1.7.0).

    On the stored pages a promoted card's "discounted from" price equals ``floor(price * 100) / 100`` in
    double arithmetic, so a stated 8.79 shows as 8.78 (8.79 * 100 = 878.9999999999999): 3,692 of 3,692
    promoted card observations of 1.7.0's report, the one-cent conflicts included. A pattern, not a cause: the
    page reached the collector with both values already in it, and a page returned through a provider does not
    show which upstream component produced the difference (release 1.8.0 dropped the word "retailer" from the
    label). The
    displayed value is still exported and the conflict still kept."""
    shown, data = Decimal(displayed), Decimal(stated)
    return shown != data and Decimal(math.floor(float(data) * 100)) / 100 == shown


def price_conflict_cause(conflicts: Mapping[str, Mapping[str, str]]) -> dict[str, str]:
    return {
        name: "ONE_CENT_TRUNCATION_PATTERN"
        if truncation_explains(c["displayed"], c["product_data"])
        else "UNEXPLAINED"
        for name, c in conflicts.items()
    }


@dataclass(frozen=True)
class SourceCheck:
    """What the site's own product response says about one product at the configured store.

    Used to verify the store and fulfillment of the displayed values and to explain missing ones; it
    never fills a displayed field. ``response`` is ``None`` when no product response was captured."""

    response: dict[str, Any] | None = None  # kind, fetch_id, sha256, observed_at of the response
    store: str = ""  # the configured store's location ID
    modality: str = ""  # the configured fulfillment
    price_location: str | None = None  # the store the response's price is for (None: no price stated)
    fulfillment: tuple[str, ...] = ()  # fulfillment types the response offers the product for
    stock_level: str = ""  # stock level at the configured store, as stated
    unit_price_text: tuple[str, ...] = ()  # the site's own unit-price text ("$0.29/fl oz"), if any
    size: str = ""  # the response's customer-facing size
    sold_by: str = ""  # "<sellBy>/<orderBy>", e.g. "Unit/Unit", "Weight/Unit"
    # The store's regular and promotional unit prices the response states ("8.79"; "" when not stated).
    regular_price: str = ""
    promo_price: str = ""
    brand: str = ""  # the product's own brand as the response states it ("" when not stated)
    # The size facts of the product's own data (release 1.8.0): compared with the displayed size, exported
    # only
    # when the rules of ``assembly.size_evidence`` settle a conflict with them.
    size_quantity: str = ""  # item.pidSizeQuantity
    size_unit: str = ""  # item.pidSizeUnitOfMeasureName
    package_weight: str = ""  # item.weight, "0.5 [lb_av]"
    unit_price_amount: str = ""  # price.storePrices.regular.equivalizedUnitPrice.amount
    unit_price_unit: str = ""  # its unit, "PER OUNCE"
    price_postal_codes: tuple[str, ...] = ()  # postalCodes[] stating a price (never a store's price)

    def price_conflicts(self, record: Mapping[str, str]) -> dict[str, dict[str, str]]:
        """Displayed prices that differ from the store's prices in the same product's response (1.3.0).
        Only comparable values count: a displayed sale with no promotion in the response is not checked."""
        out: dict[str, dict[str, str]] = {}
        if self.response is None or self.location_ok is False:
            return out
        for name, stated in (("regular_price", self.regular_price), ("sale_price", self.promo_price)):
            shown = record.get(name) or ""
            if shown and stated and Decimal(shown) != Decimal(stated):
                out[name] = {"displayed": shown, "product_data": stated}
        return out

    @property
    def location_ok(self) -> bool | None:
        return None if not self.price_location else self.price_location == self.store

    @property
    def price_store_not_stated(self) -> bool:
        """The response states a price but no store for it: ``price.storePrices`` without
        ``sourceLocationId`` (release 1.8.0rc2). Live 2026-11-02 at 53100502 Pickup: a jar candle temporarily
        out of stock at the store, its price stated under ``postalCodes`` for ZIP 60061 only. Such a price is
        not the store's by the site's own data."""
        return (
            self.response is not None
            and not self.price_location
            and bool(self.regular_price or self.promo_price)
        )

    @property
    def modality_ok(self) -> bool | None:
        return None if not self.fulfillment else self.modality.upper() in self.fulfillment

    def as_dict(self) -> dict[str, Any]:
        if self.response is None:
            return {
                "result": "N/A",
                "note": "no product response for it was captured before its card was recorded",
            }
        failed = self.location_ok is False or self.modality_ok is False
        return {
            "result": "FAIL" if failed else "PASS",
            "response": self.response,
            "price_location": self.price_location,
            "location_ok": self.location_ok,
            "fulfillment": list(self.fulfillment),
            "modality_ok": self.modality_ok,
            "stock_level": self.stock_level,
            "unit_price_text": list(self.unit_price_text),
            "regular_price": self.regular_price,
            "promo_price": self.promo_price,
            "brand": self.brand,
            "size": self.size,
            "sold_by": self.sold_by,
            "size_quantity": self.size_quantity,
            "size_unit": self.size_unit,
            "package_weight": self.package_weight,
            "unit_price_amount": self.unit_price_amount,
            "unit_price_unit": self.unit_price_unit,
        }


@dataclass(frozen=True)
class ProductEvidence:
    """Displayed values for one product, already chosen by precedence PDP > card > drawer."""

    upc: str | None
    url: str
    title: str
    size_text: str
    price: PriceDisplay
    offers: tuple[OfferObservation, ...]
    image_url: str
    ppm_text: str = ""  # PPM exactly as displayed, "" if not displayed
    pdp_size_text: str = ""  # size from the PDP when the card's size slot shows a unit price
    # False: the card has no size slot (the tile served since 2026-11-06, release 1.9.0rc2).
    size_displayed: bool = True
    # False: a tile (served since 2026-11-06), which shows no coupon even for a product whose own page shows
    # one (release 1.9.0rc3): its empty coupon zone is not an observed absence.
    listing_shows_coupons: bool = True
    # The product's own page read for its coupons: "rendered", "not_rendered" (not brought rendered), or ""
    # (not read).
    product_page_read: str = ""
    brand: str | None = None
    is_ship_only: bool = False
    # The offer is a marketplace seller's, not the retailer's own local offer (Walmart): no local price.
    is_marketplace: bool = False
    # The product's identity when the retailer shows no UPC (Walmart item id, "wm:123"): used to keep
    # products apart and never exported as ``upc``.
    source_key: str | None = None
    location_attested: bool = True
    provenance: dict[str, FieldSource] = field(default_factory=dict)
    flags: tuple[RecordFlag, ...] = ()
    source_check: SourceCheck | None = None  # the site's product response for this product, if read
    offer_notes: tuple[str, ...] = ()  # offers the details listed but the record leaves out, and why


@dataclass(frozen=True)
class CategoryAssignment:
    category: str
    sub_category: str


@dataclass(frozen=True)
class BuiltRecord:
    upc: str | None
    record: dict[str, str]
    status: RecordStatus
    reasons: tuple[RecordFlag, ...]
    flags: tuple[RecordFlag, ...]
    deals: DealFields
    provenance: dict[str, dict[str, Any]]
    missing: dict[str, str] = field(default_factory=dict)  # empty field -> why it is empty
    missing_kind: dict[str, str] = field(default_factory=dict)  # empty field -> class of the reason
    source_check: dict[str, Any] = field(default_factory=dict)

    @property
    def exported(self) -> bool:
        return self.status in EXPORTED_RECORD_STATUSES


def assess_weight(
    weight: str, evidence: ProductEvidence, sold_by_weight: bool, detail: str = ""
) -> SizeAssessment:
    """The record's size from the observations of this one product (``assembly.size_evidence``)."""
    check = evidence.source_check
    if check is None or check.response is None:
        return assess_size(weight, title=evidence.title, detail=detail, sold_by_weight=sold_by_weight)
    return assess_size(
        weight,
        title=evidence.title,
        pid_quantity=check.size_quantity or None,
        pid_unit=check.size_unit or None,
        detail=detail,
        sold_by_weight=sold_by_weight,
        ppm_unit=check.unit_price_unit,
        basis=price_basis_measure(check.regular_price, check.unit_price_amount, check.unit_price_unit),
        package=package_weight_measure(check.package_weight),
    )


_PPM_TEXT = re.compile(r"^\$(?P<amount>\d[\d,]*(?:\.\d+)?)\s*/\s*(?P<unit>[A-Za-z][A-Za-z .]*)$")
_COUNT_WORDS = frozenset({"each", "ea", "ct", "count"})
_COUNT_UNITS = frozenset({"EACH", "COUNT", "CT", "EA"})


def ppm_source_anomalies(ppm: str, prices: tuple[str, str], check: SourceCheck | None) -> list[RecordFlag]:
    """Source-value anomalies of a displayed price per measure (release 1.9.0, M3), from comparisons only:
    nothing is computed and the exported text is never changed. Found in run Q2 (2026-11-02): "$19.99/oz" on
    a $19.99 pack of 12 x 2.6 oz (UPC 0084024314377; the product data's own unit price states 19.99 PER
    OUNCE too) and "$7.99/oz" on a product whose data states 1 EACH (UPC 0001280052496)."""
    m = _PPM_TEXT.match(collapse_ws(ppm))
    if m is None or check is None or check.response is None:
        return []
    try:
        amount = Decimal(m.group("amount").replace(",", ""))
        quantity = Decimal(check.size_quantity) if check.size_quantity else None
    except InvalidOperation:
        return []
    out: list[RecordFlag] = []
    shown: set[Decimal] = set()
    for p in prices:
        try:
            if p:
                shown.add(Decimal(p))
        except InvalidOperation:
            continue
    if amount in shown and quantity is not None and quantity != 1:
        out.append(RecordFlag.PPM_EQUALS_ITEM_PRICE)
    pack_unit = check.size_unit.strip().upper()
    if pack_unit and (m.group("unit").strip().casefold() not in _COUNT_WORDS) == (pack_unit in _COUNT_UNITS):
        out.append(RecordFlag.PPM_UNIT_FAMILY_MISMATCH)
    return out


def _terms_unread(c: ClassifiedOffer) -> bool:
    return c.kind is OfferKind.DIGITAL and restriction_reason(c) is None and not collapse_ws(c.offer.terms)


def _require_coupon_terms(deals: DealFields) -> DealFields:
    """A digital coupon whose complete terms were not read (release 1.9.0, M4): the record keeps the headline
    the card displays and is flagged ``DIGITAL_TERMS_UNREAD``; a price its headline states ("$6.99 Temptations
    Cat Treats") is not exported, since the quantity, products and conditions it applies under are not
    established. The supporting files say why the terms were not read."""
    unread = [c for c in deals.classified if _terms_unread(c)]
    if not unread:
        return deals
    price = deals.digital_deals_price
    if price and any(c.explicit_price == price for c in unread):
        price = ""
    return replace(
        deals,
        digital_deals_price=price,
        flags=tuple(dict.fromkeys((*deals.flags, RecordFlag.DIGITAL_TERMS_UNREAD))),
    )


def _check_coupon_price(deals: DealFields, price: PriceDisplay) -> DealFields:
    """A coupon's headline price ("$4.99 Kroger Seedless Grapes") is a final price only below the price the
    card shows; otherwise it cannot be what the product costs with the coupon, and no price is set."""
    shelf = price.sale_price or price.regular_price
    if not deals.digital_deals_price or not shelf or RecordFlag.PER_WEIGHT_DEAL_PRICE in deals.flags:
        return deals
    chosen = next(
        (
            c
            for c in deals.classified
            if c.kind is OfferKind.DIGITAL and c.explicit_price == deals.digital_deals_price
        ),
        None,
    )
    if chosen is None or states_bundle_price(chosen.offer.text):
        return deals
    if Decimal(deals.digital_deals_price) < Decimal(shelf):
        return deals
    return replace(deals, digital_deals_price="", flags=(*deals.flags, RecordFlag.DEAL_PRICE_NOT_BELOW_PRICE))


def _offer_texts(deals: DealFields, kinds: tuple[OfferKind, ...]) -> str:
    return "; ".join(repr(c.offer.text) for c in deals.classified if c.kind in kinds)


def no_coupon_reason(evidence: ProductEvidence) -> str:
    """Why a record holds no digital coupon. A card's empty coupon zone is an observed absence; a tile's is
    not (release 1.9.0rc3): tiles showed no coupon for products whose own page shows one, so only that page,
    rendered, tells."""
    if evidence.listing_shows_coupons:
        return "no digital coupon is displayed"
    if evidence.product_page_read == "rendered":
        return "neither the tile nor the product's own page, rendered, shows an applicable digital coupon"
    page = "was not brought rendered" if evidence.product_page_read == "not_rendered" else "was not read"
    return (
        "the tile shows no coupon (tiles omit coupons that the product's own page shows) and that page "
        f"{page}: {COUPON_UNKNOWN}"
    )


def missing_reasons(
    record: dict[str, str],
    *,
    evidence: ProductEvidence,
    size_problem: str,
    size_is_unit_price: bool,
    deals: DealFields,
    settings: RecordSettings,
    size: SizeAssessment | None = None,
) -> dict[str, str]:
    """Why each empty field of the record is empty, in the record's field order."""
    price, check = evidence.price, evidence.source_check
    stock = (
        f"; the site's product response states stock level {check.stock_level}"
        if check and check.stock_level
        else ""
    )
    volume_offers = [c for c in deals.classified if c.kind is OfferKind.VOLUME]
    digital_offers = [c for c in deals.classified if c.kind is OfferKind.DIGITAL]
    out: dict[str, str] = {}
    for name, value in record.items():
        if value:
            continue
        if name in ALWAYS_EMPTY:
            reason = "always empty (client rule)"
        elif name == "weight":
            if size_problem:
                reason = size_problem
            elif size is not None and size.resolution is SizeResolution.UNRESOLVED:
                reason = f"unresolved size conflict: {size.reason}"
            elif size is not None and size.resolution is SizeResolution.UNIT_DENOMINATOR:
                reason = size.reason
            elif size_is_unit_price:
                reason = (
                    f"the size slot shows a price per unit ({evidence.size_text!r}); no size is displayed"
                )
            elif not evidence.size_displayed:
                reason = "the tile shows no size, and the product's own data in the page states none"
            else:
                reason = "the card shows no size"
        elif name == "regular_price" and price.is_relative:
            reason = (
                "the card shows only an estimated item price "
                f"({price.sr_text or price.current_text!r}) for a product sold by weight; an estimate is not "
                "a fixed price (kept in the supporting log)"
            )
        elif name == "sale_price" and price.kind is PriceDisplayKind.RELATIVE_SALE:
            reason = (
                f"the sale is shown only as an estimated item price ({price.sr_text!r}); an estimate is "
                "not a fixed price (kept in the supporting log)"
            )
        elif name in ("regular_price", "sale_price") and price.kind is PriceDisplayKind.UNRECOGNIZED:
            reason = (
                f"the tile shows its price in a form this release does not know ({price.sr_text!r}, "
                f"{price.current_text!r}); no price is read from it (PRICE_DISPLAY_UNRECOGNIZED)"
            )
        elif name == "regular_price":
            if price.kind is PriceDisplayKind.NOT_DISPLAYED:
                reason = f"the card shows {price.placeholder_text!r} instead of a price{stock}"
            else:
                reason = f"the card shows no price{stock}"
        elif name == "sale_price":
            reason = "no sale price is displayed"
        elif name == "volume_deals_description":
            other = _offer_texts(deals, (OfferKind.OTHER_PROMO,))
            reason = "no multi-unit offer is displayed" + (
                f" (offer {other} is not a multi-unit offer)" if other else ""
            )
        elif name == "volume_deals_price":
            if not volume_offers:
                reason = "no multi-unit offer is displayed"
            elif RecordFlag.MULTIPLE_VOLUME_PRICES in deals.flags:
                reason = "several multi-unit offers state different prices"
            else:
                reason = (
                    "the offer text states no final price (" + _offer_texts(deals, (OfferKind.VOLUME,)) + ")"
                )
        elif name == "digital_deals_description":
            left_out = []
            if not settings.include_points_offers_in_deals and (
                p := _offer_texts(deals, (OfferKind.POINTS,))
            ):
                left_out.append(f"points offer {p} left out (include_points_offers_in_deals is off)")
            if not settings.include_cashback_in_digital and (c := _offer_texts(deals, (OfferKind.CASHBACK,))):
                left_out.append(f"cash-back offer {c} left out (include_cashback_in_digital is off)")
            reason = no_coupon_reason(evidence) + (f"; {'; '.join(left_out)}" if left_out else "")
        elif name == "digital_deals_price":
            if not digital_offers:
                reason = no_coupon_reason(evidence)
            elif RecordFlag.MULTIPLE_DIGITAL_PRICES in deals.flags:
                reason = "several coupons state different prices"
            elif RecordFlag.DEAL_PRICE_NOT_BELOW_PRICE in deals.flags:
                reason = "the coupon's price is not below the displayed price, so it is not a final price"
            elif any(_terms_unread(c) and c.explicit_price for c in digital_offers):
                reason = (
                    "the coupon's headline states a price ("
                    + "; ".join(
                        repr(c.offer.text) for c in digital_offers if _terms_unread(c) and c.explicit_price
                    )
                    + ") but its complete terms were not read: the quantity, products and conditions it "
                    "applies under are not established"
                )
            else:
                reason = (
                    "the coupon states a discount or no final price ("
                    + _offer_texts(deals, (OfferKind.DIGITAL,))
                    + ")"
                )
        elif name == "ppm":
            if check is None:
                reason = "the card shows no price per measure (no product response was captured to compare)"
            elif check.unit_price_text:
                reason = "the card shows no price per measure, although the site's product response has one"
            else:
                reason = (
                    "the card shows no price per measure, and the site's product response has none either"
                )
        elif name == "image_url":
            reason = "the card's picture has no http(s) address"
        elif name == "store_logo":
            reason = "the page header shows no logo image"
        else:
            reason = "not displayed"
        out[name] = reason
    return out


class MissingKind(StrEnum):
    """Why a field is empty, as a class (release 1.8.0). ``ACCESS_FAILURE`` is a page that was refused or not
    brought: a product never reached has no record to hold it, so it is reported per listing (the coverage
    reconciliation) and on a retained record (``historical.why_kind``)."""

    NOT_DISPLAYED = "not_displayed"
    NOT_ATTEMPTED = "not_attempted"
    ACCESS_FAILURE = "access_failure"
    PARSING_FAILURE = "parsing_failure"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    CLIENT_RULE = "client_rule"


def missing_kinds(missing: Mapping[str, str], *, size_problem: str = "") -> dict[str, str]:
    """The class of each reason :func:`missing_reasons` wrote."""
    out: dict[str, str] = {}
    for name, reason in missing.items():
        if reason == "always empty (client rule)":
            kind = MissingKind.CLIENT_RULE
        elif reason.startswith("unresolved size conflict") or "state different prices" in reason:
            kind = MissingKind.UNRESOLVED_CONFLICT
        elif name == "weight" and size_problem and reason == size_problem:
            # A size given as "N/A" or "Count" states none (release 1.9.0rc2); other texts are misplaced.
            kind = MissingKind.NOT_DISPLAYED if NO_QUANTITY in reason else MissingKind.PARSING_FAILURE
        elif COUPON_UNKNOWN in reason:
            # A tile's coupon, when its product's own page was not read rendered (release 1.9.0rc3).
            kind = MissingKind.NOT_ATTEMPTED
        elif "no product response was captured" in reason:
            kind = MissingKind.NOT_ATTEMPTED
        else:
            kind = MissingKind.NOT_DISPLAYED
        out[name] = kind.value
    return out


def build_product_record(
    evidence: ProductEvidence,
    *,
    store: StoreFields,
    category: CategoryAssignment,
    crawl_date: str,
    settings: RecordSettings,
    detector: PrivateLabelDetector,
    configured_modality: str,
    store_provenance: dict[str, FieldSource] | None = None,
) -> BuiltRecord:
    flags: list[RecordFlag] = list(evidence.flags)
    price = evidence.price
    check = evidence.source_check

    # Weight: displayed size; for relative-price items the size slot holds "$0.69/lb" instead. Text that
    # is not a size ("Front", a picture's view name the retailer put in its size field) is left out.
    # Release 1.9.0rc2: the tile has no size slot; the product's own customer-facing size in the same page's
    # data stands for it (the displayed size equalled it in 1,157 of 1,157 comparable Q2 records), with its
    # source, and goes through the same checks as a displayed size.
    size_shown = evidence.size_text
    size_source: FieldSource | None = None
    if (
        not evidence.size_displayed
        and not size_shown
        and check is not None
        and check.response is not None
        and check.size
    ):
        size_shown = check.size
        flags.append(RecordFlag.SIZE_FROM_PRODUCT_DATA)
        size_source = FieldSource(
            "state",
            "data.products[].item.customerFacingSize (the product's own data in the same page)",
            str(check.response.get("fetch_id") or ""),
            str(check.response.get("sha256")) if check.response.get("sha256") else None,
            str(check.response.get("observed_at") or ""),
        )
    size_is_unit_price = size_slot_is_unit_price(size_shown)
    weight = evidence.pdp_size_text if size_is_unit_price else size_shown
    size_problem = size_text_problem(weight, evidence.title)
    if size_problem:
        weight = ""
        flags.append(RecordFlag.SIZE_TEXT_NOT_A_SIZE)

    # The size as the product's own evidence settles it (release 1.8.0): a serving, the unit of a price per
    # pound or two observations that disagree are not a pack size. ``displayed_weight`` stays what was shown:
    # the approximate-weight rule reads it, whatever is exported.
    displayed_weight = weight
    sold_by_weight = (
        price.is_relative
        or size_is_unit_price
        or (check is not None and check.sold_by.casefold().startswith("weight"))
    )
    size = assess_weight(
        weight,
        evidence,
        sold_by_weight,
        detail=evidence.pdp_size_text if not size_is_unit_price else "",
    )
    weight = size.exported
    if size.resolution is SizeResolution.UNRESOLVED:
        flags.append(RecordFlag.SIZE_CONFLICT_UNRESOLVED)
    elif size.resolution is SizeResolution.UNIT_DENOMINATOR:
        flags.append(RecordFlag.SIZE_IS_UNIT_OF_PRICE)
    elif size.conflict:
        flags.append(RecordFlag.SIZE_CONFLICT_RESOLVED)

    # PPM: displayed only (DOM_ONLY). The relative-price size slot is itself a displayed $/unit.
    ppm = evidence.ppm_text
    if not ppm and size_is_unit_price:
        ppm = evidence.size_text
    if not ppm:
        flags.append(RecordFlag.PPM_NOT_DISPLAYED)
    elif (
        evidence.ppm_text and check is not None and check.unit_price_text and ppm not in check.unit_price_text
    ):
        flags.append(RecordFlag.PPM_DOM_JSON_MISMATCH)

    # The store and fulfillment of the displayed values, as the site's own product response states them.
    location_attested = evidence.location_attested
    if check is not None and check.location_ok is False:
        location_attested = False
    if check is not None and check.modality_ok is False:
        flags.append(RecordFlag.MODALITY_NOT_OFFERED)

    if price.kind is PriceDisplayKind.NOT_DISPLAYED or price.kind is PriceDisplayKind.MISSING:
        flags.append(RecordFlag.PRICE_NOT_DISPLAYED)
    # "about $1.64 each" with "$2.39/lb": an estimated item price for a product sold by weight. The per-pound
    # price is the displayed PPM; the estimate is neither the regular nor the sale price (1.4.0).
    shown_regular, shown_sale = price.regular_price, price.sale_price
    if price.is_relative:
        flags.append(RecordFlag.RELATIVE_PRICE)
        flags.append(RecordFlag.SOLD_BY_WEIGHT)
        flags.append(RecordFlag.ESTIMATED_PRICE_ONLY)
        shown_regular, shown_sale = "", ""
    if not weight and weight_range_in(evidence.title):
        flags.append(RecordFlag.WEIGHT_RANGE_IN_TITLE)
    if is_plu_code(evidence.upc):
        flags.append(RecordFlag.PLU_CODE)
    flags.extend(ppm_source_anomalies(ppm, (shown_regular, shown_sale), check))

    deals = derive_deal_fields(evidence.offers, settings, configured_modality)
    deals = _check_coupon_price(deals, price)
    deals = _require_coupon_terms(deals)
    flags.extend(deals.flags)

    # store_brand from source-backed brand data only (1.3.1): the product's brand as displayed, else as
    # the site's own product data states it. Without either, "no": a title or UPC prefix alone never
    # makes a product private label (the prefixes stay in the record's signals).
    sc = evidence.source_check
    brand, brand_source = evidence.brand or "", "displayed" if evidence.brand else ""
    if not brand and sc is not None and sc.response is not None and sc.brand:
        brand, brand_source = sc.brand, "product_data"
    pl = detector.detect(title=evidence.title, upc=evidence.upc, brand=brand or None, require_brand=True)
    flags.extend(pl.flags)

    record = build_record(
        {
            "zipcode": store.zipcode,
            "store_name": store.store_name,
            "store_location": store.store_location,
            "store_logo": store.store_logo,
            "store_brand": pl.value,
            "category": category.category,
            "sub_category": category.sub_category,
            "product_title": evidence.title,
            "weight": weight,
            "regular_price": shown_regular,
            "sale_price": shown_sale,
            "volume_deals_description": deals.volume_deals_description,
            "volume_deals_price": deals.volume_deals_price,
            "digital_deals_description": deals.digital_deals_description,
            "digital_deals_price": deals.digital_deals_price,
            "image_url": evidence.image_url,
            "url": evidence.url,
            "upc": evidence.upc or "",
            "ppm": ppm,
            "crawl_date": crawl_date,
        }
    )

    problems = shape_violations(record) + format_violations(record)
    if problems:
        flags.append(RecordFlag.SCHEMA_INVALID)

    identity = evidence.upc or evidence.source_key
    approx = approx_weight_wording(
        weight=displayed_weight,
        product_data_size=check.size if check is not None and check.response is not None else "",
        title=evidence.title,
        sold_by_weight=sold_by_weight,
        settings=settings,
    )
    reasons = exclusion_reasons(
        flags=flags,
        weight=weight,
        is_ship_only=evidence.is_ship_only,
        location_attested=location_attested,
        upc=identity,
        settings=settings,
        is_marketplace=evidence.is_marketplace,
        approx_weight=approx,
    )

    # The same product's own data for the store states other prices than the page displays (1.3.0; Honey
    # Smacks, 2026-10-23: "discounted from $8.78" on the card, regular USD 8.79 in the page's own product
    # response). Both observations are kept; the displayed price is exported (prices exactly as displayed),
    # and the record is not counted as verified while they differ.
    conflicts = check.price_conflicts(record) if check is not None else {}
    if conflicts:
        flags.append(RecordFlag.PRICE_DOM_JSON_MISMATCH)
    # A displayed price the product's own data states for no store (1.8.0rc2): exported as displayed, never
    # VALID: a valid record's price is the store's by its own data.
    unattributed = (
        check is not None
        and check.price_store_not_stated
        and bool(record["regular_price"] or record["sale_price"])
    )
    if unattributed:
        flags.append(RecordFlag.PRICE_STORE_NOT_STATED)

    if reasons:
        status = RecordStatus.EXCLUDED
    elif not all(record[k] for k in ("product_title", "url", "category")) or not identity:
        status = RecordStatus.EXPORTED_NOT_VALID
    elif conflicts:
        status = RecordStatus.PRICE_CONFLICT
    elif RecordFlag.PRICE_DISPLAY_UNRECOGNIZED in flags:
        status = RecordStatus.EXPORTED_NOT_VALID
    elif not (record["regular_price"] or record["sale_price"]):
        # A product of the store's assortment without a fixed current price is still a valid identity.
        status = RecordStatus.ELIGIBLE_UNPRICED
    elif unattributed:
        status = RecordStatus.EXPORTED_NOT_VALID
    else:
        status = RecordStatus.VALID

    sources = {**(store_provenance or {}), **evidence.provenance}
    if size_source is not None:
        sources["weight"] = size_source
    provenance = {k: v.as_dict() for k, v in sources.items()}
    if size_source is not None and check is not None:
        provenance["_size_from_product_data"] = {
            "product_data_size": check.size,
            "exported": weight,
            "response": check.response,
            "rule": "the tile served since 2026-11-06 shows no size: the weight is the product's own "
            "customer-facing size in the same page's data, checked by the same size rules (release 1.9.0rc2)",
        }
    if price.kind is PriceDisplayKind.UNRECOGNIZED:
        provenance["_price_display_unrecognized"] = {
            "displayed_current": price.current_text,
            "displayed_original": price.original_text,
            "screen_reader_text": price.sr_text,
            "rule": "only a plain price, 'Sale: $X discounted from $Y' and 'about $X each' are read from a "
            "tile; any other form is kept as shown and no price is exported (release 1.9.0rc2)",
        }
    provenance["_store_brand_signals"] = {
        "signals": pl.signals,
        "brand": brand,
        "brand_source": brand_source or "none",
        "rule": "private label only when the product's own brand is a listed private-label brand",
    }
    if problems:
        provenance["_schema_problems"] = {"problems": problems}
    if evidence.offer_notes:
        provenance["_offers_left_out"] = {"notes": list(evidence.offer_notes)}
    if size.conflict:
        provenance["_size_evidence"] = size.as_dict()
    if price.is_relative:
        provenance["_estimated_price"] = {
            "kind": price.kind.value,
            "displayed_current": price.current_text,
            "displayed_original": price.original_text,
            "screen_reader_text": price.sr_text,
            "estimated_regular": price.regular_price,
            "estimated_sale": price.sale_price,
            "per_unit_price_displayed": ppm,
            "rule": "an estimated item price of a product sold by weight is not a fixed price: the regular "
            "and sale prices are left empty and the displayed price per unit is the PPM",
        }
    if RecordFlag.WEIGHT_RANGE_IN_TITLE in flags:
        provenance["_weight_range_in_title"] = {
            "range": weight_range_in(evidence.title),
            "note": "no weight is displayed; the title states a weight range (listed in the eligibility "
            "report)",
        }
    if approx is not None:
        provenance["_approx_weight"] = {
            "source": approx[0],
            "wording": approx[1],
            "displayed_weight": displayed_weight,
            "product_data_size": check.size if check is not None else "",
            "title": evidence.title,
            "rule": "approximate-weight wording, or a weight range, in the product's weight as displayed, as "
            "its own product data states it, or (sold by weight, with no weight displayed) in its name: "
            "excluded (APPROX_WEIGHT)",
        }
    provenance["_availability"] = availability_of(check)
    if unattributed and check is not None:
        provenance["_price_store_not_stated"] = {
            "displayed": {k: record[k] for k in ("regular_price", "sale_price")},
            "product_data": {
                "regular_price": check.regular_price,
                "promo_price": check.promo_price,
                "price_location": check.price_location,
                "postal_codes_with_a_price": list(check.price_postal_codes),
                "stock_level_at_store": check.stock_level,
                "response": check.response,
            },
            "rule": "the product's own data states this price for no store (price.storePrices has no "
            "sourceLocationId): the displayed price is exported as displayed and the record is not counted "
            "as valid (PRICE_STORE_NOT_STATED)",
        }
    if conflicts and check is not None:
        provenance["_price_observations"] = {
            "conflict": conflicts,
            "displayed": {k: record[k] for k in ("regular_price", "sale_price")},
            "product_data": {
                "regular_price": check.regular_price,
                "promo_price": check.promo_price,
                "price_location": check.price_location,
                "response": check.response,
            },
            "precedence": "the displayed price is exported; the record is not verified while they differ",
            # What the difference looks like: a description, never who caused it.
            "cause": price_conflict_cause(conflicts),
            "cause_rule": "ONE_CENT_TRUNCATION_PATTERN: the displayed price equals the product data's price "
            "truncated to cents in binary floating point (floor(price x 100) / 100); which upstream "
            "component produced the difference is not established. UNEXPLAINED: any other difference",
        }

    missing = missing_reasons(
        record,
        evidence=evidence,
        size_problem=size_problem,
        size_is_unit_price=size_is_unit_price,
        deals=deals,
        settings=settings,
        size=size,
    )
    if COUPON_UNKNOWN in missing.get("digital_deals_description", ""):
        flags.append(RecordFlag.DIGITAL_COUPONS_UNOBSERVED)
    return BuiltRecord(
        upc=identity,
        record=record,
        status=status,
        reasons=tuple(reasons),
        flags=tuple(dict.fromkeys(flags)),
        deals=deals,
        provenance=provenance,
        missing=missing,
        missing_kind=missing_kinds(missing, size_problem=size_problem),
        source_check=check.as_dict() if check is not None else {},
    )
