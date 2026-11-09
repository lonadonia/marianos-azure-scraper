"""Deterministic promotion classifier (brief §7, docx §7).

Only displayed text is used. A deal price is set only when the displayed text states the final price
explicitly; nothing is ever computed from "% off", "$ off", BOGO or cash-back wording.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum

from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import DealDescriptionFormat, OtherPromoTarget, RecordSettings
from marianos_headless.core.text import collapse_ws, normalize_amount_str


class OfferSource(StrEnum):
    ZONE = "zone"  # card savings zone (one offer)
    DRAWER_OFFER = "drawer_offer"  # drawer savings-side-offer ("Sale", "Shop Deal")
    DRAWER_COUPON = "drawer_coupon"  # drawer savings-side-coupon ("Sign In To Clip")
    PDP = "pdp"
    COUPON_CARD = "coupon_card"  # coupon catalogue / carousel card
    JSON_COUPONS = "json_coupons"
    JSON_PRODUCTS = "json_products"


# Display order between sources: zone first, then drawer order (§7.2 step 5).
_SOURCE_RANK = {
    OfferSource.ZONE: 0,
    OfferSource.DRAWER_OFFER: 1,
    OfferSource.DRAWER_COUPON: 1,
    OfferSource.PDP: 2,
    OfferSource.COUPON_CARD: 3,
    OfferSource.JSON_COUPONS: 4,
    OfferSource.JSON_PRODUCTS: 5,
}


class OfferKind(StrEnum):
    CASHBACK = "cashback"
    POINTS = "points"
    DIGITAL = "digital"
    VOLUME = "volume"
    OTHER_PROMO = "other_promo"


@dataclass(frozen=True)
class OfferObservation:
    source: OfferSource
    text: str  # full displayed offer sentence (never a split-price join)
    display_order: int = 0
    tag: str = ""  # displayed tag; "" means the tag was not observed
    clip_checkbox: bool | None = None  # zone only: a coupon checkbox is present
    ctas: tuple[str, ...] = ()
    expiry_text: str = ""
    coupon_type: str | None = None  # coupons JSON: STANDARD | CASH_BACK
    modalities: tuple[str, ...] | None = None  # structured modality list, when known
    extra_tags: tuple[str, ...] = ()  # other displayed tags, e.g. "Pickup & Delivery Only"
    coupon_id: str | None = None
    sources: tuple[OfferSource, ...] = ()  # filled when observations are merged
    # The offer's details as its "View Offer" dialog shows them: quantity, limits, eligibility, dates.
    terms: str = ""
    quantity: int | None = None  # units the offer requires (a coupon's requirementQuantity), if known
    # The product's own offer data, when it states them (release 1.8.0): never computed.
    starts_at: str = ""
    ends_at: str = ""
    offer_code: str = ""

    @property
    def sort_key(self) -> tuple[int, int]:
        return _SOURCE_RANK[self.source], self.display_order


@dataclass(frozen=True)
class ClassifiedOffer:
    offer: OfferObservation
    requires_clip: bool
    kind: OfferKind
    explicit_price: str  # "" unless the text states the final price
    per_weight_price: bool
    restricted_to: frozenset[str] | None  # modalities named by a restriction, if any
    flags: tuple[RecordFlag, ...] = ()


_CLIP_TAGS = {"coupon", "weekly digital deal", "digital coupon", "digital deal"}
_NO_CLIP_TAGS = {"sale"}
_CLIP_CTA = re.compile(
    r"\bclip\b|\bactivate\b|\b(?:load|add|save)\b(?:\s+\w+)?\s+(?:coupon|offer|to card)\b", re.I
)
_NO_CLIP_CTA = re.compile(r"^shop deal$", re.I)

# Rewards paid later are never an immediate price reduction (shared requirements §7): cash back, Walmart
# Cash, mail-in or manufacturer rebates.
_CASHBACK = re.compile(r"\bcash\s*back\b|\bwalmart\s+cash\b|\brebate\b", re.I)
_POINTS = re.compile(
    r"\b\d+\s*x\s+(?:fuel\s+)?points\b|\bearn\b[^.]*\bpoints\b|\bfuel\s+points\b|\bpoints\s+event\b"
    r"|\bbonus\s+points\b",
    re.I,
)
_NUMBER_WORD = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_NUMBER_VALUES = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}  # fmt: skip
# A second product or a free unit: a condition on several retail units whatever the first number says
# ("Buy 1, Get 1 Free", "Buy One Sandwich, Get One Coke for $2"). The number that a pack holds is never read
# here.
_SEVERAL_UNITS = [
    re.compile(rf"\bbuy\s+{_NUMBER_WORD}\b.*\bget\b", re.I),
    re.compile(r"\bmix\s*(?:or|&|and)\s*match\b", re.I),
    re.compile(r"\bget\s+\d+\s+free\b", re.I),
    re.compile(r"\bBOGO\b", re.I),
]
# The retail units the offer's condition requires, as its text states them. "Save $1.00 on 2 Cereals" names
# units; "Save $1 on 12 oz" names a pack size, so a number followed by a measure is not read.
_MEASURE_WORD = (
    r"(?:oz|ounces?|fl|lbs?|pounds?|ct|count|pk|packs?|gal|gallons?|liters?|l|ml|qt|pt|in|inch|inches)\b"
)
_REQUIRED = [
    re.compile(r"^\s*(\d+)\s*(?:for|/)\s*\$", re.I),
    re.compile(rf"\bbuy\s+({_NUMBER_WORD})\b", re.I),
    re.compile(rf"\bmust\s+buy\s+({_NUMBER_WORD})\b", re.I),
    re.compile(rf"\bsave\b.*\bon\s+({_NUMBER_WORD})\s+(?!{_MEASURE_WORD})", re.I),
]

_PRICE_NFOR = re.compile(r"^(\d+)\s*(?:for|/)\s*\$(\d+(?:\.\d{2})?)\b", re.I)
_PRICE_EACH_WHEN_BUY = re.compile(r"^\$(\d+\.\d{2})\s*(?:each|ea)?\b.*\bwhen you buy\b", re.I)
_PRICE_MUST_BUY = re.compile(r"must buy\s*\d+\s*:?\s*\$(\d+\.\d{2})\s*each", re.I)
_PRICE_HEADLINE = re.compile(r"^\$(\d+\.\d{2})(\s*/?\s*lb)?\s+(?!off\b)(?!cash back\b)\S", re.I)
_PRICE_EACH_DIGITAL = re.compile(r"\$(\d+\.\d{2})\s*each with digital coupon", re.I)

_RESTRICTIONS: list[tuple[re.Pattern[str], frozenset[str]]] = [
    (re.compile(r"\bpickup\s*(?:or|&|and)\s*delivery\s+only\b", re.I), frozenset({"PICKUP", "DELIVERY"})),
    (re.compile(r"\bdelivery\s*(?:or|&|and)\s*pickup\s+only\b", re.I), frozenset({"PICKUP", "DELIVERY"})),
    (re.compile(r"\bdelivery\s+only\b", re.I), frozenset({"DELIVERY"})),
    (re.compile(r"\bpickup\s+only\b", re.I), frozenset({"PICKUP"})),
    (re.compile(r"\bin[-\s]?stores?\s+(?:purchases?\s+)?only\b", re.I), frozenset({"IN_STORE"})),
    (re.compile(r"\bship(?:ping)?\s+only\b", re.I), frozenset({"SHIP"})),
]


def requires_clip(offer: OfferObservation) -> bool:
    tag = offer.tag.strip().lower()
    # A merged offer counts as a coupon if any sighting showed it as one (e.g. zone + drawer coupon).
    seen_in = {offer.source, *offer.sources}
    # Explicit negatives (drawer "Sale" offer, "Shop Deal", zone without checkbox) and unknown
    # signals both mean "no clipping shown".
    return (
        bool(seen_in & {OfferSource.DRAWER_COUPON, OfferSource.COUPON_CARD})
        or (OfferSource.ZONE in seen_in and offer.clip_checkbox is True)
        or tag in _CLIP_TAGS
        or any(_CLIP_CTA.search(c) for c in offer.ctas)
        or (offer.coupon_type or "").upper() == "STANDARD"
    )


def states_bundle_price(text: str) -> bool:
    """The text prices several units together ("2 For $5.00", "4/$10 when you buy 4 or more")."""
    return bool(_PRICE_NFOR.search(collapse_ws(text)))


def required_quantity(text: str) -> int | None:
    """The retail units the offer's condition requires, as its wording states it; None when it states none.

    ``Buy 1 Save $1`` requires one unit, whatever that unit holds: a 12-pack sold as one item is one unit."""
    t = collapse_ws(text)
    for rx in _REQUIRED:
        m = rx.search(t)
        if m:
            word = m.group(1).casefold()
            return int(word) if word.isdigit() else _NUMBER_VALUES[word]
    return None


def is_volume_text(text: str) -> bool:
    """The text states a condition on several retail units ("2 For $5.00", "Buy 1, Get 1 Free", "when you
    buy 5"). A saving on one unit ("Buy 1 Save $1", "1/$3") and a pack label ("Family Pack") do not."""
    if any(rx.search(text) for rx in _SEVERAL_UNITS):
        return True
    needed = required_quantity(text)
    return needed is not None and needed >= 2


def classify_kind(offer: OfferObservation, clip: bool) -> OfferKind:
    tag = offer.tag.strip().lower()
    if tag == "cash back" or (offer.coupon_type or "").upper() == "CASH_BACK" or _CASHBACK.search(offer.text):
        return OfferKind.CASHBACK
    if tag == "points event" or _POINTS.search(offer.text):
        return OfferKind.POINTS
    if clip:
        return OfferKind.DIGITAL
    if is_volume_text(offer.text):
        return OfferKind.VOLUME
    return OfferKind.OTHER_PROMO


def extract_explicit_price(text: str, kind: OfferKind, quantity: int | None = None) -> tuple[str, bool]:
    """Return ``(price, per_weight)``; price is ``""`` unless the text states the final price.

    A coupon headline price ("$4.99 Kroger Seedless Grapes") is the price of one unit; when the coupon
    requires several units (``quantity`` > 1) the headline does not say what one unit costs, so no price."""
    if kind not in (OfferKind.VOLUME, OfferKind.DIGITAL):
        return "", False
    t = collapse_ws(text)
    m = _PRICE_NFOR.search(t)
    if m:
        return normalize_amount_str(m.group(2)), False
    m = _PRICE_EACH_WHEN_BUY.search(t)
    if m:
        return normalize_amount_str(m.group(1)), False
    m = _PRICE_MUST_BUY.search(t)
    if m:
        return normalize_amount_str(m.group(1)), False
    if kind is OfferKind.DIGITAL:
        m = _PRICE_HEADLINE.search(t)
        if m and (quantity is None or quantity <= 1):
            return normalize_amount_str(m.group(1)), bool(m.group(2))
        m = _PRICE_EACH_DIGITAL.search(t)
        if m:
            return normalize_amount_str(m.group(1)), False
    return "", False


def modality_restriction(offer: OfferObservation) -> frozenset[str] | None:
    if offer.modalities:
        return frozenset(m.upper() for m in offer.modalities)
    for candidate in (offer.text, *offer.extra_tags):
        for rx, allowed in _RESTRICTIONS:
            if rx.search(candidate):
                return allowed
    return None


def classify(offer: OfferObservation, configured_modality: str) -> ClassifiedOffer:
    clip = requires_clip(offer)
    kind = classify_kind(offer, clip)
    price, per_weight = extract_explicit_price(offer.text, kind, offer.quantity)
    restricted = modality_restriction(offer)
    flags: list[RecordFlag] = []
    if restricted is not None and configured_modality.upper() not in restricted:
        flags.append(RecordFlag.MODALITY_RESTRICTED_OFFER)
    if per_weight and price:
        flags.append(RecordFlag.PER_WEIGHT_DEAL_PRICE)
    if kind is OfferKind.DIGITAL and not offer.tag:
        flags.append(RecordFlag.OFFER_TAG_UNOBSERVED)
    return ClassifiedOffer(offer, clip, kind, price, per_weight, restricted, tuple(flags))


def restriction_reason(c: ClassifiedOffer) -> str | None:
    """Why an offer is left out of the deal fields for the configured fulfillment: it names only other
    fulfillments ("Pickup or Delivery Only" on an In Store collection; release 1.4.0). It stays in the
    offers file and the supporting log with this reason."""
    if RecordFlag.MODALITY_RESTRICTED_OFFER not in c.flags or not c.restricted_to:
        return None
    named = " / ".join(sorted(c.restricted_to))
    return f"restricted to {named}: not an offer of the configured fulfillment, left out of the deal fields"


_MIX_AND_MATCH = re.compile(r"\bmix\s*(?:or|&|and)\s*match\b", re.I)
_LIMIT = re.compile(r"\blimit\s+\d+\b[^.;,]*", re.I)
_MEMBERSHIP = re.compile(
    r"\bwith\s+(?:your\s+)?(?:\w+\s+)?(?:card|membership)\b|\b(?:\w+\s+)?members?\s+only\b|\bwith\s+boost\b",
    re.I,
)
_QUALIFYING = re.compile(
    r"\bon\s+(?:any\s+|select\s+)?(?!\d+\s*(?:oz|lb))([^.;]+?)(?=\s+(?:when|with|limit)\b|[.;]|$)", re.I
)


def offer_terms(c: ClassifiedOffer) -> dict[str, object]:
    """Every condition of an offer the source shows, for the supporting files. A term the source does not show
    stays empty: nothing here is computed, and no price is derived from a saving, a percentage or a
    multi-buy."""
    o = c.offer
    wording = collapse_ws(" ".join(x for x in (o.text, o.terms) if x))
    limit = _LIMIT.search(wording)
    membership = _MEMBERSHIP.search(wording)
    qualifying = _QUALIFYING.search(wording)
    return {
        "required_quantity": o.quantity if o.quantity is not None else required_quantity(wording),
        "mix_and_match": bool(_MIX_AND_MATCH.search(wording)),
        "qualifying_products": qualifying.group(1) if qualifying else "",
        "clipping_required": c.requires_clip,
        "membership": membership.group(0) if membership else "",
        "limit": limit.group(0) if limit else "",
        "valid_from": o.starts_at,
        "valid_to": o.ends_at or o.expiry_text,
        "fulfillment_restriction": sorted(c.restricted_to) if c.restricted_to else [],
        "explicit_price": c.explicit_price,
        "offer_code": o.offer_code,
    }


def text_key(text: str) -> str:
    return collapse_ws(text).casefold().rstrip(" .")


def merge_observations(offers: Iterable[OfferObservation]) -> list[OfferObservation]:
    """Merge the same offer seen in several places (zone + drawer, card + JSON).

    Offers are matched by their displayed text. The merged offer keeps the earliest display position
    and fills tag, expiry, CTAs and IDs from whichever observation displayed them.
    """
    ordered = sorted(offers, key=lambda o: o.sort_key)
    merged: dict[str, OfferObservation] = {}
    for o in ordered:
        key = text_key(o.text)
        if not key:
            continue
        if key not in merged:
            merged[key] = replace(o, sources=(o.source,))
            continue
        cur = merged[key]
        merged[key] = replace(
            cur,
            tag=cur.tag or o.tag,
            clip_checkbox=cur.clip_checkbox if cur.clip_checkbox is not None else o.clip_checkbox,
            ctas=cur.ctas + tuple(c for c in o.ctas if c not in cur.ctas),
            expiry_text=cur.expiry_text or o.expiry_text,
            coupon_type=cur.coupon_type or o.coupon_type,
            modalities=cur.modalities or o.modalities,
            extra_tags=cur.extra_tags + tuple(t for t in o.extra_tags if t not in cur.extra_tags),
            coupon_id=cur.coupon_id or o.coupon_id,
            sources=(*cur.sources, o.source),
            terms=cur.terms or o.terms,
            quantity=cur.quantity if cur.quantity is not None else o.quantity,
            starts_at=cur.starts_at or o.starts_at,
            ends_at=cur.ends_at or o.ends_at,
            offer_code=cur.offer_code or o.offer_code,
        )
    return list(merged.values())


def format_description(offer: OfferObservation, fmt: DealDescriptionFormat) -> str:
    """``TAG_TEXT_EXPIRY``: "Coupon: $4.99 Kroger Seedless Grapes — <terms> (Exp. 10/20/2026)"; the terms
    (quantity, limits, eligibility, dates) only when the offer's details were read."""
    text = collapse_ws(offer.text)
    if fmt is DealDescriptionFormat.TEXT_ONLY:
        return text
    out = f"{collapse_ws(offer.tag)}: {text}" if offer.tag else text
    terms = collapse_ws(offer.terms)
    if terms and text_key(terms) != text_key(text):
        out += f" — {terms}"
    # Release 1.9.0 (M4): a coupon read from the product's own page also names the clipping instruction the
    # page displays ("Sign In To Clip"), with the expiry it displays.
    clip = (
        next((collapse_ws(c) for c in offer.ctas if _CLIP_CTA.search(c)), "")
        if OfferSource.PDP in {offer.source, *offer.sources}
        else ""
    )
    when = "; ".join(x for x in (collapse_ws(offer.expiry_text), clip) if x)
    if when:
        out += f" ({when})"
    return out


@dataclass(frozen=True)
class DealFields:
    volume_deals_description: str = ""
    volume_deals_price: str = ""
    digital_deals_description: str = ""
    digital_deals_price: str = ""
    flags: tuple[RecordFlag, ...] = ()
    classified: tuple[ClassifiedOffer, ...] = field(default_factory=tuple)


def _pick_price(
    offers: Sequence[ClassifiedOffer], multi_flag: RecordFlag, flags: list[RecordFlag]
) -> tuple[str, ClassifiedOffer | None]:
    priced = [o for o in offers if o.explicit_price]
    if len(priced) == 1:
        return priced[0].explicit_price, priced[0]
    if len(priced) > 1:
        flags.append(multi_flag)
    return "", None


def derive_deal_fields(
    observations: Iterable[OfferObservation], settings: RecordSettings, configured_modality: str
) -> DealFields:
    merged = merge_observations(observations)
    classified = [classify(o, configured_modality) for o in merged]
    flags: list[RecordFlag] = []
    volume: list[ClassifiedOffer] = []
    digital: list[ClassifiedOffer] = []
    volume_text_only: list[ClassifiedOffer] = []
    digital_text_only: list[ClassifiedOffer] = []

    for c in classified:
        # An offer of another fulfillment reaches no field of this record, whatever its kind.
        if restriction_reason(c) is not None:
            flags.append(RecordFlag.MODALITY_RESTRICTED_OFFER)
            continue
        if c.kind is OfferKind.CASHBACK:
            if settings.include_cashback_in_digital:
                digital_text_only.append(c)
            else:
                flags.append(RecordFlag.CASHBACK_OFFER_EXCLUDED)
            continue
        if c.kind is OfferKind.POINTS:
            if settings.include_points_offers_in_deals:
                digital_text_only.append(c)
            else:
                flags.append(RecordFlag.POINTS_OFFER_EXCLUDED)
            continue
        if c.kind is OfferKind.OTHER_PROMO:
            flags.append(RecordFlag.OTHER_PROMO_UNCLASSIFIED)
            if settings.other_promo_target is OtherPromoTarget.VOLUME_DESCRIPTION:
                volume_text_only.append(c)
            continue
        flags.extend(c.flags)
        (digital if c.kind is OfferKind.DIGITAL else volume).append(c)

    fmt = settings.deal_description_format
    sep = settings.deal_description_separator

    def describe(items: Sequence[ClassifiedOffer]) -> str:
        ordered = sorted(items, key=lambda c: c.offer.sort_key)
        return sep.join(format_description(c.offer, fmt) for c in ordered)

    volume_price, _ = _pick_price(volume, RecordFlag.MULTIPLE_VOLUME_PRICES, flags)
    digital_price, chosen = _pick_price(digital, RecordFlag.MULTIPLE_DIGITAL_PRICES, flags)
    if chosen is None or not chosen.per_weight_price:
        flags = [f for f in flags if f is not RecordFlag.PER_WEIGHT_DEAL_PRICE]

    return DealFields(
        volume_deals_description=describe([*volume, *volume_text_only]),
        volume_deals_price=volume_price,
        digital_deals_description=describe([*digital, *digital_text_only]),
        digital_deals_price=digital_price,
        flags=tuple(dict.fromkeys(flags)),
        classified=tuple(classified),
    )
