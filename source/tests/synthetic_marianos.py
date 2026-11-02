"""SYNTHETIC Mariano's-like pages for tests: never real data, never contest evidence.

Card and header markup copy the shapes of the saved 2026-10-17 homepage (FIXTURE); the product-page
markup is what ``sites/marianos/pdp.py`` assumes, not a confirmed site contract. Prices are invented.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from typing import Any

LOCATION_ID = "53100503"


def store_details(
    location_id: str = LOCATION_ID,
    *,
    address: str = "333 E Benton Pl",
    vanity: str = "Marianos Lakeshore East",
    postal: str = "60601",
) -> dict[str, Any]:
    return {
        "locationId": location_id,
        "divisionNumber": location_id[:3],
        "storeNumber": location_id[3:],
        "vanityName": vanity,
        "address": {
            "address": {
                "addressLines": [address],
                "cityTown": "Chicago",
                "stateProvince": "IL",
                "postalCode": postal,
            }
        },
        "allowedModalities": ["PICKUP", "IN_STORE"],
        "brand": "MARIANOS",
        "banner": "marianos",
    }


def state_script(
    *,
    modality: str = "IN_STORE",
    source: str = "STORE_SELECTION",
    trusted: bool = True,
    location_id: str = LOCATION_ID,
    address: str = "333 E Benton Pl",
    vanity: str = "Marianos Lakeshore East",
    postal: str = "60601",
    extra: dict[str, Any] | None = None,
) -> str:
    details = store_details(location_id, address=address, vanity=vanity, postal=postal)
    state = {
        "meta": {"siteVersion": "synthetic"},
        "calypso": {
            "useCases": {
                "getModalityPreferences": {
                    "default": {
                        "response": {
                            "data": {
                                "modalityPreferences": {
                                    "activeModality": modality,
                                    "storeDetails": [details],
                                    "modalities": [
                                        {
                                            "modalityType": modality,
                                            "source": source,
                                            "isTrustedSource": trusted,
                                            "destination": {"locationId": location_id},
                                        }
                                    ],
                                    "lafObject": [
                                        {"modality": {"handoffLocation": {"storeId": location_id}}}
                                    ],
                                }
                            }
                        }
                    }
                }
            }
        },
        "modalitySelectorState": {"hasManuallySetActiveModality": not source.startswith("DEFAULT_")},
        "dynamicdata": {f"marianos/home/IL/{location_id[:3]}/{location_id[3:]}": {}},
    }
    for key, value in (extra or {}).items():
        if key == "calypso":
            state["calypso"] = {**state["calypso"], **value}
        else:
            state[key] = value
    raw = json.dumps(state).replace("\\", "\\\\").replace("'", "\\'")
    return f"<script>window.__INITIAL_STATE__ = JSON.parse('{raw}')</script>"


def header(
    *,
    modality_word: str = "In-Store",
    name: str = "Marianos Lakeshore East",
    address: str = "333 E Benton Pl",
) -> str:
    return (
        '<section aria-label="Currently Shopping" data-testid="CurrentModality">'
        f'<button aria-label="{modality_word} at {name}, open modal to change how you are shopping" '
        'data-testid="CurrentModality-button" onclick="openDialog()">'
        '<span data-testid="CurrentModality-textV2"><span data-testid="CurrentModality-modalityType">'
        f"<span>&nbsp;{modality_word}</span><span><span>&nbsp;at</span><span>&nbsp;"
        f'<span data-testid="CurrentModality-vanityName">{name}</span></span></span></span></span></button>'
        f'<div data-testid="PickupAddress"><span data-testid="PickupAddressText">{address}</span></div>'
        "</section>"
    )


@dataclass(frozen=True)
class Product:
    upc: str
    slug: str
    title: str
    size: str
    price: str  # current displayed price, e.g. "$3.19"
    original: str = ""  # struck-through price when on sale
    zone: str = ""  # savings zone text
    clip: bool = False  # the zone shows a coupon checkbox
    ppm: str = ""  # displayed price per measure on the product page

    def url(self, base: str) -> str:
        return f"{base}/p/{self.slug}/{self.upc}"


PRODUCTS = (
    Product(
        "0001111003962",
        "kroger-100-apple-juice",
        "Kroger® 100% Apple Juice",
        "64 fl oz",
        "$3.19",
        ppm="$0.05/fl oz",
    ),
    Product(
        "0002400016293",
        "del-monte-sweet-corn",
        "Del Monte® Sweet Corn",
        "15.25 oz",
        "$1.25",
        original="$1.79",
        zone="2 For $5.00",
        ppm="$0.08/oz",
    ),
    Product(
        "0005100025163",
        "campbells-tomato-soup",
        "Campbell's® Tomato Soup",
        "10.75 oz",
        "$1.49",
        zone="Save $0.50 with digital coupon",
        clip=True,
    ),
    Product("0001111085209", "kroger-black-beans", "Kroger® Black Beans", "15.5 oz", "$0.99"),
)


def card(i: int, p: Product, base: str) -> str:
    sale = bool(p.original)
    price_cls = "citrus-Price citrus-Price--compact" + (" citrus-Price--promotional" if sale else "")
    original = (
        f'<span class="citrus-Price--original-price"><span class="citrus-Price--original-price-value">'
        f"{p.original}</span></span>"
        if sale
        else ""
    )
    zone = ""
    if p.zone:
        box = (
            f'<input aria-label="{escape(p.zone)}" data-testid="coupon-checkbox" type="checkbox">'
            if p.clip
            else ""
        )
        zone = (
            f'<div data-testid="savings-zone"><div data-testid="savings-zone-card">{box}'
            f"<a>{escape(p.zone)}</a></div></div>"
        )
    return (
        f'<div data-testid="carousel-product-card-{i}" aria-label="{escape(p.title)}">'
        f'<div data-testid="product-image"><a href="{p.url(base)}"><img src="https://www.example.invalid/img/{p.upc}.png"></a></div>'
        f'<div data-testid="product-item-unit-price" class="{price_cls}">'
        f'<span class="citrus-Price--current-price">{p.price}</span>{original}</div>'
        f'<a href="{p.url(base)}"><span data-testid="cart-page-item-description">{escape(p.title)}</span></a>'
        f'<div><span data-testid="product-item-sizing">{p.size}</span></div>{zone}</div>'
    )


def grid_card(i: int, p: Product, base: str) -> str:
    """A listing (grid) card as on the live Canned Foods page of 2026-10-20: the per-measure price and
    the size in two sizing slots, the offer text beside a "View Offer" link, ``?fulfillment=`` links."""
    sale = bool(p.original)
    price_cls = "citrus-Price citrus-Price--compact" + (" citrus-Price--promotional" if sale else "")
    original = (
        f'<span class="citrus-Price--original-price"><span class="citrus-Price--original-price-value">'
        f"{p.original}</span></span>"
        if sale
        else ""
    )
    href = f"{p.url(base)}?fulfillment=PICKUP"
    ppm = f'<span data-testid="product-item-sizing">{p.ppm}</span>' if p.ppm else ""
    zone = (
        f'<div data-testid="savings-zone"><span data-testid="savings-zone-text">{escape(p.zone)}</span>'
        '<button data-testid="savings-zone-link-text">View Offer</button></div>'
        if p.zone
        else ""
    )
    if p.zone and p.clip:  # a coupon, as on the live grid of 2026-10-20: "Coupon: …" and "View Offer"
        zone = (
            '<div data-testid="savings-zone"><div data-testid="savings-zone-card">'
            f'<input aria-label="{escape(p.zone)}" disabled data-testid="coupon-checkbox" type="checkbox">'
            f'<div><span data-testid="savings-zone-coupon-text">Coupon: {escape(p.zone)}</span>'
            f'<button aria-label="Details link for {escape(p.zone)}" data-testid="open-coupon-modal-button">'
            "View Offer</button></div></div></div>"
        )
    price = (
        f'<div data-testid="product-item-unit-price" class="{price_cls}">'
        f'<span class="citrus-Price--current-price">{p.price}</span>{original}</div>'
        if p.price
        # No price shown (out of stock), as on the live grid of 2026-10-20: a text in the price area.
        else '<div><span data-citrus-component="Text" class="block citrus-Text">Prices May Vary</span></div>'
    )
    return (
        f'<div data-testid="auto-grid-cell"><div data-testid="product-card-{i}">'
        f'<div data-testid="product-image"><a href="{href}"><img src="https://www.example.invalid/img/{p.upc}"></a></div>'
        f"{price}"
        f'<a href="{href}"><span data-testid="cart-page-item-description">{escape(p.title)}</span></a>'
        f'<div>{ppm}<span data-testid="product-item-sizing">{p.size} | </span>'
        f'<a href="{href}"><span data-testid="product-variant-text">2 more sizes</span></a></div>'
        f"{zone}</div></div>"
    )


# The store picker as recorded live (ModalitySelectorModal): an In Store tab, a ZIP search, store cards
# with a radio per location ID, a confirm button. ``stores`` is the result list the search shows.
def store_picker(stores: tuple[tuple[str, str, str], ...]) -> str:
    cards = "".join(
        f'<div data-testid="ModalityOption-Store-Card-{loc[3:]}"><label data-testid="IN_STORE-{loc}">'
        f'<input type="radio" name="Store Options Radio Group" value="{loc}">{name}, {addr}</label></div>'
        for loc, name, addr in stores
    )
    return (
        '<dialog data-testid="ModalitySelectorModal" role="dialog" aria-modal="true" id="picker">'
        '<button role="tab" onclick="document.getElementById(\'pick\').hidden=false">Pickup</button>'
        '<button role="tab" onclick="document.getElementById(\'pick\').hidden=true;'
        "document.getElementById('instore').hidden=false\">In Store</button>"
        '<section id="pick" role="tabpanel"><input data-testid="PostalCodeSearchBox-input" type="search">'
        '<button data-testid="Start-Shopping-PICKUP">Start Shopping</button></section>'
        '<section id="instore" role="tabpanel" hidden><form onsubmit="showStores();return false">'
        '<input data-testid="PostalCodeSearchBox-input" type="search" aria-label="Search"></form>'
        '<div id="results"></div><button data-testid="Start-Shopping-PICKUP" onclick="confirmStore()">'
        "Plan Your Visit</button></section></dialog>"
        f"<script>const CARDS = {json.dumps(cards)};"
        "function openDialog(){document.getElementById('picker').setAttribute('open','')}"
        "function showStores(){document.getElementById('results').innerHTML = CARDS}"
        "function confirmStore(){const r = document.querySelector('#results input:checked');"
        "if (r) {document.cookie = 'store=' + r.value + '; path=/';"
        "document.cookie = 'mod=IN_STORE; path=/'}"
        "document.getElementById('picker').removeAttribute('open')}</script>"
    )


def default_store_state() -> str:
    """The site's own default for an unknown visitor (live: Marianos Frankfort, Pickup, a default source)."""
    return state_script(
        modality="PICKUP",
        source="DEFAULT_MODALITY_ADDRESS",
        trusted=False,
        location_id="53100509",
        address="21001 S La Grange Rd",
        vanity="Marianos Frankfort",
        postal="60423",
    )


def page(body: str, *, state: str = "", head_extra: str = "") -> str:
    return f"<!doctype html><html><head><title>t</title>{head_extra}</head><body>{body}{state}</body></html>"


def listing_page(
    base: str,
    *,
    state: str,
    hdr: str,
    products: tuple[Product, ...] = PRODUCTS,
    search_url: str = "",
    grid: bool = False,
) -> str:
    cards = "".join((grid_card if grid else card)(i, p, base) for i, p in enumerate(products))
    fetch = f"<script>fetch('{search_url}')</script>" if search_url else ""
    return page(f"{hdr}<main>{cards}</main>{fetch}", state=state)


def product_page(base: str, p: Product, *, state: str, hdr: str, similar: tuple[Product, ...] = ()) -> str:
    sale = bool(p.original)
    price_cls = "citrus-Price" + (" citrus-Price--promotional" if sale else "")
    original = (
        f'<span class="citrus-Price--original-price"><span class="citrus-Price--original-price-value">'
        f"{p.original}</span></span>"
        if sale
        else ""
    )
    ppm = f'<span class="unit">{p.ppm}</span>' if p.ppm else ""
    carousel = "".join(card(10 + i, s, base) for i, s in enumerate(similar))
    body = (
        f'{hdr}<main><h1 data-testid="product-details-name">{escape(p.title)}</h1>'
        f'<span data-testid="product-details-upc">UPC: {p.upc}</span>'
        f'<span id="ProductDetails-sellBy-unit">{p.size}</span>'
        f'<div data-testid="product-details-price"><div data-testid="product-item-unit-price" '
        f'class="{price_cls}"><span class="citrus-Price--current-price">{p.price}</span>{original}</div>'
        f"{ppm}</div>"
        f'<img src="https://www.example.invalid/product/images/large/front/{p.upc}">'
        f"<section>{carousel}</section></main>"
    )
    return page(body, state=state)


# -- server-rendered search pages, as the Oxylabs Web API serves them (shapes of the probe pages of
# 2026-10-28: search.searchAll and calypso.domains.products in the page state; SYNTHETIC values) -----------


def state_product(
    p: Product, *, taxonomy: str, location_id: str = LOCATION_ID, regular: str = "", promo: str = ""
) -> dict[str, Any]:
    """A product of ``calypso.domains.products.<upc>.data`` (the products_v2 shape). ``taxonomy`` is the
    department + commodity + sub-commodity code, e.g. ``0300100001``."""
    price = regular or (p.original or p.price).lstrip("$")
    prices: dict[str, Any] = {
        "sourceLocationId": location_id,
        "regular": {"price": f"USD {price}", "defaultDescription": f"${price}"},
    }
    if p.original or promo:
        sale = promo or p.price.lstrip("$")
        prices["promo"] = {
            "price": f"USD {sale}",
            "defaultDescription": f"${sale}",
            "expirationDate": {"value": "2026-11-03T03:59:59Z"},
        }
    return {
        "id": p.upc,
        "item": {
            "upc": p.upc,
            "customerFacingSize": p.size,
            "taxonomies": [
                {
                    "department": {"code": taxonomy[:2], "name": "Dept"},
                    "commodity": {"code": taxonomy[2:5], "name": "Commodity"},
                    "subCommodity": {"code": taxonomy[5:], "name": "Sub"},
                }
            ],
        },
        # A product that shows no price states none (``price`` empty; live 2026-10-29, out of stock).
        "price": {"sellBy": "Unit", "orderBy": "Unit", "storePrices": prices} if price else {},
        "fulfillmentOptions": ["IN_STORE", "PICKUP"],
        "inventory": {
            "locations": [
                {"locationId": location_id, "stockLevel": "HIGH" if price else "TEMPORARILY_OUT_OF_STOCK"}
            ]
        },
    }


def search_page(
    base: str,
    products: tuple[tuple[Product, str], ...],
    *,
    query: str,
    total: int,
    sponsored: tuple[str, ...] = (),
    location_id: str = LOCATION_ID,
    request_location_id: str | None = None,
    price_location: dict[str, str] | None = None,
    source: str = "FALLBACK_ACTIVE_MODALITY_COOKIE",
    product_data: dict[str, dict[str, Any]] | None = None,
    page_number: int | None = 1,
    taxonomy_id: str | None = None,
    ranks: dict[str, int] | None = None,
    available: int | None = None,
    departments: list[dict[str, Any]] | None = None,
    brands: list[dict[str, Any]] | None = None,
    modality: str = "IN_STORE",
    show_cards: bool = True,
    store_name: str = "Marianos Lakeshore East",
    store_address: str = "333 E Benton Pl",
    store_postal: str = "60601",
) -> str:
    """A search result page, or (with ``taxonomy_id`` and ``ranks``) a listing's page: the grid's cards and
    the page state (``products``: (product, taxonomy)). ``show_cards=False`` is a page brought without its
    page state (``products``: (product, taxonomy)). ``show_cards=False`` is a page brought without its grid (a
    later page without rendering, probe L9 of 2026-11-02). ``store_*`` name the selected store the page
    shows."""
    cards = "".join(grid_card(i, p, base) for i, (p, _) in enumerate(products)) if show_cards else ""
    grid = f'<div data-testid="paginate-items">{cards}</div>'
    data = {
        p.upc: (product_data or {}).get(p.upc)
        or state_product(p, taxonomy=tax, location_id=(price_location or {}).get(p.upc, location_id))
        for p, tax in products
    }
    extra = {
        "calypso": {"domains": {"products": {u: {"data": d} for u, d in data.items()}}},
        "search": {
            "searchAll": {
                "requestVars": {
                    "query": query,
                    **({"page": page_number} if page_number is not None else {}),
                    **({"taxonomyId": taxonomy_id} if taxonomy_id else {}),
                    "fulfillment": "all",
                    "locationId": request_location_id or location_id,
                    "activeModalityType": modality,
                },
                "response": {
                    "upcs": [p.upc for p, _ in products],
                    "sponsoredItems": [{"upc": u} for u in sponsored],
                    "loadedPages": [page_number] if page_number is not None else [],
                    "productsInfo": {
                        **({"totalCount": total} if page_number is not None else {}),
                        "availableCount": min(total, 250) if available is None else available,
                        "waysToShop": [{"name": "In-Store", "slug": "in_store"}],
                        **({"departments": departments} if departments is not None else {}),
                        **({"brands": brands} if brands is not None else {}),
                    },
                    "products": [
                        {
                            "upc": p.upc,
                            "subCommodityCode": [tax],
                            **({"searchEngineRank": ranks[p.upc]} if ranks and p.upc in ranks else {}),
                        }
                        for p, tax in products
                    ],
                },
            }
        },
    }
    state = state_script(
        source=source,
        trusted=False,
        location_id=location_id,
        modality=modality,
        extra=extra,
        address=store_address,
        vanity=store_name,
        postal=store_postal,
    )
    word = "Pickup" if modality == "PICKUP" else "In-Store"
    return page(
        f"{header(modality_word=word, name=store_name, address=store_address)}<main>{grid}</main>",
        state=state,
    )


def coupons_page(n: int = 3) -> str:
    """The Coupons page as rendered (coupon cards; no products in its state)."""
    cards = "".join(
        f'<div data-testid="CouponCard-{9000 + i}" data-brand="Brand {i}" data-category="Cat">'
        f'<h3 aria-label="Save $1.00 on Brand {i}">Save $1.00</h3>'
        f'<span data-testid="CouponDesc-{9000 + i}">on any Brand {i} item</span>'
        f'<span data-testid="CouponExpiration">Exp. 11/03/26</span></div>'
        for i in range(n)
    )
    return page(
        f"{header()}<main>{cards}</main>",
        state=state_script(source="FALLBACK_ACTIVE_MODALITY_COOKIE", trusted=False),
    )
