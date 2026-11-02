"""The site's own JSON responses on a listing page: checks and offer details, never displayed values.

A listing page requests the data of the products it shows and their coupons. Shapes as captured live on
2026-10-20 (run 01M5BWAPJ0RF9972ZF8G87REVE, Marianos Lakeshore East, in store):

- ``/atlas/v1/product/v2/products?filter.gtin13s=…``: ``data.products[]`` with ``item.upc``,
  ``item.customerFacingSize``, ``price.storePrices.sourceLocationId``, ``price.storePrices.{regular,promo}``
  (``defaultDescription``, ``expirationDate.value``, ``nfor``, ``price`` as ``"USD 3.99"``,
  ``equivalizedUnitPriceString`` such as ``"$0.29/fl oz"`` when the site formats a unit price),
  ``price.{sellBy,orderBy,displayTemplate}``, ``offers[]`` (``defaultDescription``, ``endDate.value``,
  ``modalities``), ``fulfillmentOptions`` and ``inventory.locations[]`` (``locationId``, ``stockLevel``);
  on 2026-10-23 also the stock per fulfillment type, ``inventorySummaries[]`` (``modalityType``,
  ``details[]``: ``sourceId``, ``stockLevel``, ``availableToSell``), the only stock some products stated;
  it is read for the configured fulfillment first;
- ``/atlas/v1/savings-coupons/v2/coupons?filter.upc=…``: ``data.coupons[]`` with ``id``,
  ``displayDescription`` (the text the card's coupon shows), ``requirementDescription`` (the terms the
  coupon's "View Offer" dialog shows), ``expirationDate``, ``modalities``, ``type``, ``upcs`` and
  ``requirementQuantity``.

They are used to verify the store, fulfillment and availability of each product (the store the price is
for), to read the terms and validity of the offers a card's "View Offer" opens, and to explain a missing
value. Prices, sizes and the price per measure always come from the page (``ppm_source_policy``
DOM_ONLY); nothing here fills them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from marianos_headless.assembly.offers import OfferObservation, OfferSource, is_volume_text
from marianos_headless.assembly.record_builder import SourceCheck
from marianos_headless.core.text import collapse_ws
from marianos_headless.sites.marianos.search_state import taxonomy_ids

PRODUCTS = "products_v2"
COUPONS = "coupons"


@dataclass(frozen=True)
class ResponseRef:
    """The captured response a fact was read from."""

    kind: str
    fetch_id: str
    sha256: str | None
    observed_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "fetch_id": self.fetch_id,
            "sha256": self.sha256,
            "observed_at": self.observed_at,
        }


@dataclass(frozen=True)
class ProductOffer:
    text: str
    template: str
    ends_at: str | None
    modalities: tuple[str, ...]
    starts_at: str | None = None
    code: str = ""


@dataclass(frozen=True)
class ProductFacts:
    upc: str
    ref: ResponseRef
    size: str
    price_location: str | None
    sell_by: str
    order_by: str
    template: str
    promo_text: str
    promo_nfor: int | None
    promo_ends_at: str | None
    unit_price_text: tuple[str, ...]
    offers: tuple[ProductOffer, ...]
    fulfillment: tuple[str, ...]
    stock: Mapping[str, str] = field(default_factory=dict)  # location ID -> stock level
    # fulfillment type -> location ID -> stock level (inventorySummaries, live 2026-10-23)
    stock_by_modality: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    # The store's unit prices as the response states them ("8.79"), for the record's price comparison.
    regular_price: str = ""
    promo_price: str = ""
    brand: str = ""  # the product's own brand (item.brand.name), "" when the response states none
    # The site's listing IDs the product belongs to, most specific first (``item.taxonomies``): decides
    # whether a sponsored card shown on a listing is a product of that listing (release 1.5.0).
    taxonomy_ids: tuple[str, ...] = ()
    # The product data's own size facts, compared with the displayed size (release 1.8.0).
    size_quantity: str = ""
    size_unit: str = ""
    package_weight: str = ""
    unit_price_amount: str = ""
    unit_price_unit: str = ""
    variant_group: str = (
        ""  # itemsV1.product.variantGroupId: reported per listing, never used to fill a value
    )
    # The postal codes ``postalCodes[]`` states a price for (release 1.8.0rc2): explains a price stated for no
    # store; never a store's price.
    price_postal_codes: tuple[str, ...] = ()

    def stock_level(self, store: str, modality: str) -> str:
        """The stock level the response states for the store and the configured fulfillment."""
        return (self.stock_by_modality.get(modality.upper()) or {}).get(store) or self.stock.get(store, "")

    def check(self, store: str, modality: str) -> SourceCheck:
        return SourceCheck(
            response=self.ref.as_dict(),
            store=store,
            modality=modality,
            price_location=self.price_location,
            fulfillment=self.fulfillment,
            stock_level=self.stock_level(store, modality),
            unit_price_text=self.unit_price_text,
            size=self.size,
            sold_by=f"{self.sell_by}/{self.order_by}" if self.sell_by or self.order_by else "",
            regular_price=self.regular_price,
            promo_price=self.promo_price,
            brand=self.brand,
            size_quantity=self.size_quantity,
            size_unit=self.size_unit,
            package_weight=self.package_weight,
            unit_price_amount=self.unit_price_amount,
            unit_price_unit=self.unit_price_unit,
            price_postal_codes=self.price_postal_codes,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "response": self.ref.as_dict(),
            "size": self.size,
            "size_quantity": self.size_quantity,
            "size_unit": self.size_unit,
            "package_weight": self.package_weight,
            "unit_price_amount": self.unit_price_amount,
            "unit_price_unit": self.unit_price_unit,
            "price_location": self.price_location,
            "sold_by": f"{self.sell_by}/{self.order_by}",
            "template": self.template,
            "promo_text": self.promo_text,
            "promo_ends_at": self.promo_ends_at,
            "unit_price_text": list(self.unit_price_text),
            "offers": [
                {
                    "text": o.text,
                    "template": o.template,
                    "starts_at": o.starts_at,
                    "ends_at": o.ends_at,
                    "modalities": list(o.modalities),
                    "code": o.code,
                }
                for o in self.offers
            ],
            "fulfillment": list(self.fulfillment),
            "stock": dict(self.stock),
            "stock_by_modality": {m: dict(v) for m, v in self.stock_by_modality.items()},
            "variant_group": self.variant_group,
            "price_postal_codes": list(self.price_postal_codes),
        }


@dataclass(frozen=True)
class CouponFacts:
    coupon_id: str
    ref: ResponseRef
    text: str
    terms: str
    expires_at: str | None
    modalities: tuple[str, ...]
    coupon_type: str
    upcs: tuple[str, ...]
    quantity: int | None
    special: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "coupon_id": self.coupon_id,
            "response": self.ref.as_dict(),
            "text": self.text,
            "terms": self.terms,
            "expires_at": self.expires_at,
            "modalities": list(self.modalities),
            "type": self.coupon_type,
            "quantity": self.quantity,
            "special": list(self.special),
        }


def _get(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, Mapping):
            return None
        obj = obj.get(key)
    return obj


def _text(value: Any) -> str:
    return collapse_ws(value) if isinstance(value, str) else ""


_AMOUNT = re.compile(r"^\s*(?:USD\s*|\$)?(\d+(?:\.\d+)?)\s*$")


def _amount(value: Any) -> str:
    """A unit price as stated ("USD 8.79", "$8.79") in two-decimal form; "" for anything else."""
    m = _AMOUNT.match(value) if isinstance(value, str) else None
    return f"{Decimal(m.group(1)).quantize(Decimal('0.01'))}" if m else ""


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _strings(obj: Any, key: str) -> list[str]:
    out: list[str] = []
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if k == key and isinstance(v, str) and v.strip():
                out.append(collapse_ws(v))
            else:
                out.extend(_strings(v, key))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_strings(v, key))
    return out


def parse_product(p: Mapping[str, Any], ref: ResponseRef) -> ProductFacts | None:
    upc = _text(_get(p, "item", "upc")) or _text(p.get("id"))
    if not upc:
        return None
    store_prices = _get(p, "price", "storePrices") or {}
    promo = store_prices.get("promo") or {}
    unit_price = (store_prices.get("regular") or {}).get("equivalizedUnitPrice") or {}
    stock: dict[str, str] = {}
    for loc in _get(p, "inventory", "locations") or []:
        if isinstance(loc, Mapping) and loc.get("locationId") and loc.get("stockLevel"):
            stock[str(loc["locationId"])] = str(loc["stockLevel"])
    by_modality: dict[str, dict[str, str]] = {}
    for summary in p.get("inventorySummaries") or []:
        if not isinstance(summary, Mapping) or not summary.get("modalityType"):
            continue
        for d in summary.get("details") or []:
            if isinstance(d, Mapping) and d.get("sourceId") and d.get("stockLevel"):
                levels = by_modality.setdefault(str(summary["modalityType"]).upper(), {})
                levels[str(d["sourceId"])] = str(d["stockLevel"])
    offers = tuple(
        ProductOffer(
            text=_text(o.get("defaultDescription")),
            template=_text(o.get("displayTemplate")),
            ends_at=_text(_get(o, "endDate", "value")) or None,
            modalities=tuple(str(m).upper() for m in o.get("modalities") or []),
            starts_at=_text(_get(o, "startDate", "value")) or None,
            code=_text(o.get("offerCode")),
        )
        for o in p.get("offers") or []
        if isinstance(o, Mapping) and _text(o.get("defaultDescription"))
    )
    return ProductFacts(
        upc=upc,
        ref=ref,
        variant_group=_text(_get(p, "itemsV1", "product", "variantGroupId")),
        size=_text(_get(p, "item", "customerFacingSize")),
        price_location=_text(store_prices.get("sourceLocationId")) or None,
        sell_by=_text(_get(p, "price", "sellBy")),
        order_by=_text(_get(p, "price", "orderBy")),
        template=_text(_get(p, "price", "displayTemplate")),
        promo_text=_text(promo.get("defaultDescription")),
        promo_nfor=_int(promo.get("nfor")),
        promo_ends_at=_text(_get(promo, "expirationDate", "value")) or None,
        unit_price_text=tuple(dict.fromkeys(_strings(store_prices, "equivalizedUnitPriceString"))),
        offers=offers,
        fulfillment=tuple(str(x).upper() for x in p.get("fulfillmentOptions") or []),
        stock=stock,
        stock_by_modality=by_modality,
        # "price" ("USD 8.79"); without it the regular description ("$8.79"). A promotion's description may
        # be a multi-buy ("2 For $5.00"): only its "price" is a unit price.
        regular_price=_amount(
            (store_prices.get("regular") or {}).get("price")
            or (store_prices.get("regular") or {}).get("defaultDescription")
        ),
        promo_price=_amount(promo.get("price")),
        brand=_brand(_get(p, "item", "brand")),
        taxonomy_ids=tuple(taxonomy_ids(p)),
        size_quantity=_scalar(_get(p, "item", "pidSizeQuantity")),
        size_unit=_text(_get(p, "item", "pidSizeUnitOfMeasureName")),
        package_weight=_text(_get(p, "item", "weight")),
        unit_price_amount=_scalar(unit_price.get("amount") if isinstance(unit_price, Mapping) else None),
        unit_price_unit=_text(unit_price.get("unit") if isinstance(unit_price, Mapping) else None),
        price_postal_codes=tuple(
            dict.fromkeys(
                _text(pc.get("postalCode"))
                for pc in p.get("postalCodes") or []
                if isinstance(pc, Mapping) and _text(pc.get("postalCode")) and pc.get("prices")
            )
        ),
    )


def _scalar(value: Any) -> str:
    """A number or text the response states, as text ("" for anything else)."""
    if isinstance(value, bool) or value is None:
        return ""
    return _text(value) if isinstance(value, str) else str(value) if isinstance(value, int | float) else ""


def _brand(value: Any) -> str:
    """``item.brand`` is an object with a ``name`` (live 2026-10-28); a plain string is taken as is."""
    if isinstance(value, Mapping):
        return _text(value.get("name"))
    return _text(value) if isinstance(value, str) else ""


def parse_coupon(c: Mapping[str, Any], ref: ResponseRef) -> CouponFacts | None:
    cid = _text(str(c.get("id") or ""))
    text = _text(c.get("displayDescription")) or _text(c.get("shortDescription"))
    if not cid or not text:
        return None
    return CouponFacts(
        coupon_id=cid,
        ref=ref,
        text=text,
        terms=_text(c.get("requirementDescription")) or _text(c.get("longDescription")),
        expires_at=_text(c.get("expirationDate")) or _text(c.get("displayEndDate")) or None,
        modalities=tuple(str(m).upper() for m in c.get("modalities") or []),
        coupon_type=_text(c.get("type")).upper(),
        upcs=tuple(_text(u) for u in c.get("upcs") or [] if _text(u)),
        quantity=_int(c.get("requirementQuantity")),
        special=tuple(
            _text(s.get("displayName")) for s in c.get("specialSavings") or [] if isinstance(s, Mapping)
        ),
    )


class SourceIndex:
    """Products and coupons from the responses of the pages read so far (a later response wins)."""

    def __init__(self) -> None:
        self.products: dict[str, ProductFacts] = {}
        self.coupons: dict[str, CouponFacts] = {}
        self._coupons_by_upc: dict[str, list[str]] = {}

    def add(self, kind: str, body: bytes | str, ref: ResponseRef) -> int:
        """Index one captured response. Returns how many products or coupons it held (0 if unreadable)."""
        if kind not in (PRODUCTS, COUPONS):
            return 0
        try:
            doc = json.loads(body)
        except (ValueError, TypeError):
            return 0
        data = doc.get("data") if isinstance(doc, Mapping) else None
        items = (
            (data or {}).get("products" if kind == PRODUCTS else "coupons")
            if isinstance(data, Mapping)
            else None
        )
        if not isinstance(items, list):
            return 0
        n = 0
        for item in items:
            if not isinstance(item, Mapping):
                continue
            if kind == PRODUCTS:
                facts = parse_product(item, ref)
                if facts is not None:
                    self.products[facts.upc] = facts
                    n += 1
            else:
                coupon = parse_coupon(item, ref)
                if coupon is not None:
                    self.coupons[coupon.coupon_id] = coupon
                    for upc in coupon.upcs:
                        ids = self._coupons_by_upc.setdefault(upc, [])
                        if coupon.coupon_id not in ids:
                            ids.append(coupon.coupon_id)
                    n += 1
        return n

    def product(self, upc: str | None) -> ProductFacts | None:
        return self.products.get(upc or "")

    def coupons_for(self, upc: str | None) -> list[CouponFacts]:
        return [self.coupons[i] for i in self._coupons_by_upc.get(upc or "", [])]


def expiry_text(when: str | None, tz: str) -> str:
    """``"2026-10-21T03:59:59.999Z"`` -> ``"Exp. 10/20/2026"`` (the store's local date); "" if unreadable."""
    if not when:
        return ""
    try:
        ts = datetime.fromisoformat(when.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if ts.tzinfo is not None:
        ts = ts.astimezone(ZoneInfo(tz))
    return f"Exp. {ts:%m/%d/%Y}"


def coupon_offer(c: CouponFacts, *, tz: str, order: int) -> OfferObservation:
    return OfferObservation(
        source=OfferSource.JSON_COUPONS,
        text=c.text,
        display_order=order,
        coupon_type=c.coupon_type or None,
        modalities=c.modalities or None,
        expiry_text=expiry_text(c.expires_at, tz),
        coupon_id=c.coupon_id,
        terms=c.terms,
        quantity=c.quantity,
    )


def product_offers(p: ProductFacts, *, tz: str) -> list[OfferObservation]:
    """The product's multi-unit offers ("2 For $4.00", "Buy 1, Get 1 Free", "Save $1 each when you buy 5
    or more"). A promotional price alone ("$3.99", "about $3.98 each") is the card's sale price, and so is a
    saving on one unit ("Buy 1 Save $1"): the ``offers`` list below keeps anything else the product states."""
    out: list[OfferObservation] = []
    if p.promo_text and is_volume_text(p.promo_text):
        out.append(
            OfferObservation(
                source=OfferSource.JSON_PRODUCTS,
                text=p.promo_text,
                display_order=0,
                expiry_text=expiry_text(p.promo_ends_at, tz),
            )
        )
    for i, o in enumerate(p.offers, 1):
        out.append(
            OfferObservation(
                source=OfferSource.JSON_PRODUCTS,
                text=o.text,
                display_order=i,
                modalities=o.modalities or None,
                expiry_text=expiry_text(o.ends_at, tz),
                starts_at=o.starts_at or "",
                ends_at=o.ends_at or "",
                offer_code=o.code,
            )
        )
    return out
