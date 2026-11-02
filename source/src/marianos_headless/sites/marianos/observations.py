"""Turn parsed DOM observations into the site-neutral inputs of the record builder."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from marianos_headless.assembly.offers import OfferObservation, OfferSource, text_key
from marianos_headless.assembly.record_builder import FieldSource, ProductEvidence, SourceCheck, StoreFields
from marianos_headless.core.findings import RecordFlag
from marianos_headless.sites.marianos.dom_parsers import (
    DEFAULT_SELECTORS,
    CardObservation,
    CouponCardObservation,
    DrawerOffer,
    HeaderStore,
    Selectors,
)
from marianos_headless.sites.marianos.source_json import SourceIndex, coupon_offer, product_offers
from marianos_headless.sites.marianos.store_context import StoreDetails, store_location_text


def zone_offer(card: CardObservation) -> OfferObservation | None:
    if card.zone is None or not card.zone.text:
        return None
    return OfferObservation(
        source=OfferSource.ZONE,
        text=card.zone.text,
        display_order=0,
        tag=card.zone.label,
        clip_checkbox=card.zone.requires_clip,
    )


@dataclass(frozen=True)
class OfferDetails:
    """What the site's own responses add to a card: the offers its "View Offer" lists, with terms and
    dates, and the product's store, fulfillment and availability."""

    offers: tuple[OfferObservation, ...] = ()
    notes: tuple[str, ...] = ()  # listed offers left out of the record, and why
    check: SourceCheck | None = None
    sources: tuple[dict[str, object], ...] = ()  # the responses read, for the field provenance


def offer_details(
    card: CardObservation, sources: SourceIndex, *, store: str, modality: str, tz: str
) -> OfferDetails:
    """The card's offers from the captured product and coupon responses.

    An offer the card's savings zone shows is enriched by its details (merged by text). Other offers of
    the product are what its "View Offer" dialog lists: kept when they apply to the configured fulfillment,
    otherwise left out with a note (an in-store record never carries a pickup- or delivery-only offer)."""
    shown = {text_key(t) for t in ((card.zone.text, card.zone.checkbox_label) if card.zone else ()) if t}
    offers: list[OfferObservation] = []
    notes: list[str] = []
    refs: list[dict[str, object]] = []
    product = sources.product(card.upc)
    candidates = [coupon_offer(c, tz=tz, order=i) for i, c in enumerate(sources.coupons_for(card.upc))]
    if product is not None:
        candidates.extend(product_offers(product, tz=tz))
    for o in candidates:
        if text_key(o.text) not in shown and o.modalities and modality.upper() not in o.modalities:
            notes.append(f"{o.text!r} applies only to {', '.join(o.modalities)}, not {modality.upper()}")
            continue
        offers.append(o)
    for c in sources.coupons_for(card.upc):
        refs.append({"coupon_id": c.coupon_id, **c.ref.as_dict()})
    if product is not None:
        refs.append({"upc": product.upc, **product.ref.as_dict()})
    return OfferDetails(
        offers=tuple(offers),
        notes=tuple(notes),
        check=product.check(store, modality) if product is not None else None,
        sources=tuple(refs),
    )


def drawer_offers(offers: Iterable[DrawerOffer]) -> list[OfferObservation]:
    return [
        OfferObservation(
            source=OfferSource.DRAWER_COUPON if o.source == "drawer_coupon" else OfferSource.DRAWER_OFFER,
            text=o.text,
            display_order=o.display_order,
            tag=o.tag,
            ctas=o.ctas,
            expiry_text=o.expiry_text,
            coupon_id=o.coupon_id,
        )
        for o in offers
    ]


def coupon_card_offer(c: CouponCardObservation) -> OfferObservation:
    return OfferObservation(
        source=OfferSource.COUPON_CARD,
        text=c.description or c.title,
        display_order=c.position,
        tag=c.savings_tag or "Coupon",
        ctas=c.ctas,
        expiry_text=c.expiry_text,
        extra_tags=c.other_tags,
        coupon_id=c.coupon_id,
    )


def card_evidence(
    card: CardObservation,
    *,
    fetch_id: str,
    observed_at: str,
    location_attested: bool,
    extra_offers: Iterable[OfferObservation] = (),
    details: OfferDetails | None = None,
    sel: Selectors = DEFAULT_SELECTORS,
) -> ProductEvidence:
    offers = [o for o in (zone_offer(card),) if o is not None]
    offers.extend(extra_offers)
    if details is not None:
        offers.extend(details.offers)

    def src(ref: str) -> FieldSource:
        return FieldSource("dom_card", ref, fetch_id, None, observed_at)

    deal_src = src(sel.savings_zone)
    provenance = {
        "product_title": src(sel.title),
        "weight": src(sel.size),
        "regular_price": src(sel.price_block),
        "sale_price": src(sel.price_block),
        "volume_deals_description": deal_src,
        "digital_deals_description": deal_src,
        "image_url": src(sel.product_image),
        "url": src(sel.product_link),
        "upc": src(sel.product_link + " (href)"),
        **({"ppm": src(sel.size + " (the $/unit slot)")} if card.ppm_text else {}),
    }
    if details is not None and details.sources:
        # Terms, dates and the offers "View Offer" lists come from the site's own responses.
        for ref in details.sources:
            key = f"_offer_details_{ref.get('coupon_id') or ref.get('kind')}"
            provenance[key] = FieldSource(
                f"json_{ref.get('kind')}",
                "data.coupons[]"
                if ref.get("kind") == "coupons"
                else "data.products[] (price.storePrices, offers)",
                str(ref.get("fetch_id")),
                str(ref.get("sha256")) if ref.get("sha256") else None,
                str(ref.get("observed_at")),
            )
    return ProductEvidence(
        upc=card.upc,
        url=card.url,
        title=card.title,
        size_text=card.size_text,
        price=card.price,
        offers=tuple(offers),
        image_url=card.image_url,
        ppm_text=card.ppm_text,
        location_attested=location_attested,
        provenance=provenance,
        flags=tuple(RecordFlag(f) for f in card.flags),
        source_check=details.check if details is not None else None,
        offer_notes=details.notes if details is not None else (),
    )


def store_fields(details: StoreDetails, header: HeaderStore | None) -> StoreFields:
    """Q-01 default: vanity name and address as displayed (state fields until the live header
    address selector is confirmed in Phase 0)."""
    name = header.vanity_name if header and header.vanity_name else details.vanity_name
    return StoreFields(
        zipcode=details.postal_code,
        store_name=name,
        store_location=store_location_text(details),
        store_logo=header.logo_url if header else "",
    )
