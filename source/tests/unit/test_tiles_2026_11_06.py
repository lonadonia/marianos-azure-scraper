"""Release 1.9.0rc2: the product tile Mariano's serves since 2026-11-06, read from REAL pages saved at
Vernon Hills (store 53100502, PICKUP) by stage S1 (the collector's own copies) and stage O2 (provider answers,
sanitized as the collector stores pages): tests/fixtures/oxylabs_2026-11-06, origins in SOURCES_TILES.json.

The tiles go through the same code as the live collector (``grid_cards`` and ``build_card``), with the
products of the same page's own state as the product data. Two tests change one text of a real tile to show
what an unknown form does; each says which text it changed. The sizes that state no quantity are also read
from the cards run Q2 saved (SOURCES_RC2_SIZES.json)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest
from selectolax.lexbor import LexborHTMLParser

from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import CategoryAssignment, RecordStatus, StoreFields
from marianos_headless.collection.live import CardBuild, grid_cards
from marianos_headless.collection.live import build_card as _build_card
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig, load_stores
from marianos_headless.sites.marianos.dom_parsers import CardObservation, PriceDisplayKind
from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.search_state import search_summary, state_products
from marianos_headless.sites.marianos.source_json import PRODUCTS, ResponseRef, SourceIndex

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "oxylabs_2026-11-06"
SOURCES = json.loads((FIX / "SOURCES_TILES.json").read_text("utf-8"))
VH = StoreFields(
    "60061",
    "Marianos Vernon Hills",
    "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
    "https://www.marianos.com/cdn/images/multiColor-4Jf6i6B.svg",
)


def page(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode("utf-8")


def state_of(html: str) -> list[dict[str, Any]]:
    return state_products(parse_initial_state(html))


def index(html: str, name: str) -> SourceIndex:
    """The page's own product data, as the collector indexes it (the page state's products)."""
    idx = SourceIndex()
    doc = {"data": {"products": state_of(html)}}
    sha = SOURCES[name].get("file_sha256") or SOURCES[name].get("sanitized_html_sha256")
    idx.add(PRODUCTS, json.dumps(doc), ResponseRef(PRODUCTS, f"fetch-{name}", sha, "2026-11-06T19:45:00Z"))
    return idx


def tiles(html: str) -> dict[str, CardObservation]:
    grid, cards, _, _ = grid_cards(html)
    assert grid
    return {c.upc or "": c for c in cards}


@pytest.fixture(scope="module")
def vh_store() -> StoreConfig:
    stores = load_stores(ROOT / "config" / "stores.yaml").stores
    return next(s for s in stores if s.key == "marianos-53100502-pickup")


@pytest.fixture
def build(settings: Settings, vh_store: StoreConfig, private_label: PrivateLabelConfig) -> Any:
    detector = PrivateLabelDetector(private_label, settings.records.store_brand_positive_value)

    def run(card: CardObservation, idx: SourceIndex, sub: str = "Cat Treats") -> CardBuild:
        return _build_card(
            card,
            fetch_id="F-tile",
            observed_at="2026-11-06T19:45:00+00:00",
            store=vh_store,
            store_values=VH,
            store_provenance={},
            category=CategoryAssignment("Pet Supplies", sub),
            crawl_date="2026-11-06",
            settings=settings,
            detector=detector,
            sources=idx,
        )

    return run


# -- the listing tile ----------------------------------------------------------------------------------------


def test_every_listing_tile_is_read_and_matches_the_page_state() -> None:
    html = page("s1_catfood_p1_tiles.html.gz")
    grid, cards, sponsored, _ = grid_cards(html)
    state = parse_initial_state(html)
    summary = search_summary(state)
    assert grid and len(cards) == 24 and not sponsored
    assert summary is not None and summary.total == 232
    assert {c.upc for c in cards} == {p["id"] for p in state_products(state)}
    assert {c.card_testid.rsplit("-", 1)[0] for c in cards} == {"horizontal-product-card"}
    assert all(c.layout == "tile" and not c.size_displayed and c.size_text == "" for c in cards)
    friskies = next(c for c in cards if c.upc == "0005000057201")
    assert friskies.title == "Friskies Shreds With Salmon in Sauce Wet Cat Food"
    assert (
        friskies.url
        == "https://www.marianos.com/p/friskies-shreds-with-salmon-in-sauce-wet-cat-food/0005000057201"
    )
    assert friskies.image_url == "https://www.kroger.com/product/images/medium/front/0005000057201"
    assert friskies.price.kind is PriceDisplayKind.REGULAR
    assert (friskies.price.current_text, friskies.price.sr_text, friskies.price.regular_price) == (
        "$1.00",
        "$1.00",
        "1.00",
    )
    assert friskies.price_tag == "Everyday Low Price" and friskies.ppm_text == "$0.18/oz"
    assert friskies.zone is None and friskies.flags == ()


def test_a_tile_weight_is_the_size_its_own_product_data_states(build: Any) -> None:
    name = "s1_catfood_p1_tiles.html.gz"
    html = page(name)
    out = build(tiles(html)["0005000057201"], index(html, name), "Cat Food").built
    rec = out.record
    assert (rec["weight"], rec["regular_price"], rec["sale_price"], rec["ppm"]) == (
        "5.5 oz.",
        "1.00",
        "",
        "$0.18/oz",
    )
    assert out.status is RecordStatus.VALID
    assert RecordFlag.SIZE_FROM_PRODUCT_DATA in out.flags
    src = out.provenance["weight"]
    assert src["source"] == "state" and "customerFacingSize" in src["selector_or_path"]
    assert src["fetch_id"] == f"fetch-{name}"
    assert out.provenance["_size_from_product_data"]["product_data_size"] == "5.5 oz."
    # The displayed fields name the tile's own selectors.
    assert out.provenance["product_title"]["selector_or_path"] == '[data-testid="product-description"]'
    assert out.provenance["ppm"]["selector_or_path"] == '[data-testid="product-price-equivalized-unit-price"]'


def test_a_tile_without_a_price_keeps_the_product_unpriced(build: Any) -> None:
    name = "s1_catfood_p1_tiles.html.gz"
    html = page(name)
    card = tiles(html)["0005000044569"]  # the page state: temporarily out of stock, no price stated
    assert card.price.kind is PriceDisplayKind.NOT_DISPLAYED
    assert card.price.placeholder_text == "Prices May Vary" and card.ppm_text == ""
    out = build(card, index(html, name), "Cat Food").built
    assert out.status is RecordStatus.ELIGIBLE_UNPRICED
    assert out.record["regular_price"] == "" and RecordFlag.PRICE_NOT_DISPLAYED in out.flags
    assert "'Prices May Vary' instead of a price" in out.missing["regular_price"]


def test_a_sale_tile_gives_the_regular_and_the_sale_price(build: Any) -> None:
    name = "o2_cattreats_p1_tiles.html.gz"
    html = page(name)
    card = tiles(html)["0005849672306"]
    p = card.price
    assert p.kind is PriceDisplayKind.SALE
    assert (p.current_text, p.original_text, p.sr_text) == (
        "$2.99",
        "$3.29",
        "Sale: $2.99 discounted from $3.29",
    )
    assert card.price_tag == "Price Cut" and card.ppm_text == "$1.00/oz"
    out = build(card, index(html, name)).built
    assert (out.record["regular_price"], out.record["sale_price"], out.record["weight"]) == (
        "3.29",
        "2.99",
        "3 oz",
    )
    assert out.status is RecordStatus.VALID


def test_a_size_the_product_data_states_as_not_applicable_is_not_a_weight(build: Any) -> None:
    name = "o2_cattreats_p1_tiles.html.gz"
    html = page(name)
    card = tiles(html)["0002310032784"]  # "Tmpt Tn 3 Oz": the product data states the size "N/A"
    out = build(card, index(html, name)).built
    assert out.record["weight"] == ""  # nothing is taken from the title
    assert RecordFlag.SIZE_TEXT_NOT_A_SIZE in out.flags
    assert out.missing["weight"] == "the size is given as 'N/A', which states no quantity: not a pack size"
    assert out.missing_kind["weight"] == "not_displayed"
    assert out.provenance["_size_from_product_data"]["product_data_size"] == "N/A"
    # The prices are unaffected: the record stays valid.
    assert (out.record["regular_price"], out.record["sale_price"]) == ("3.29", "2.99")
    assert out.status is RecordStatus.VALID


@pytest.mark.parametrize(
    ("upc", "shown", "sub"),
    [("0002310032784", "N/A", "Cat Treats"), ("0019283330664", "Count", "Candles Home Fragrances")],
)
def test_a_card_size_that_states_no_quantity_is_not_a_weight(
    build: Any, upc: str, shown: str, sub: str
) -> None:
    # Run Q2 exported these two texts as weights; the cards are Q2's own (SOURCES_RC2_SIZES.json).
    grid, cards, _, _ = grid_cards((FIX / "q2_cards_rc2_no_quantity.html").read_text("utf-8"))
    card = next(c for c in cards if c.upc == upc)
    assert grid and card.layout == "card" and card.size_text == shown
    idx = SourceIndex()
    doc = (FIX / "q2_state_products_rc2_no_quantity.json").read_text("utf-8")
    idx.add(PRODUCTS, doc, ResponseRef(PRODUCTS, "F-q2", "c" * 64, "2026-11-02T20:00:00Z"))
    out = build(card, idx, sub).built
    assert out.record["weight"] == "" and RecordFlag.SIZE_TEXT_NOT_A_SIZE in out.flags
    assert (
        out.missing["weight"] == f"the size is given as {shown!r}, which states no quantity: not a pack size"
    )
    assert out.missing_kind["weight"] == "not_displayed"
    assert RecordFlag.SIZE_FROM_PRODUCT_DATA not in out.flags  # the card displays its size itself


def test_a_multi_unit_regular_price_is_shown_as_its_unit_price(build: Any) -> None:
    # The product data states "4 For $9.00" as the regular price; the tile shows $2.25, as Q2 recorded it.
    name = "o2_dogfood_p1_tiles.html.gz"
    html = page(name)
    card = tiles(html)["0002310001527"]
    assert card.price.kind is PriceDisplayKind.REGULAR and card.price.current_text == "$2.25"
    out = build(card, index(html, name), "Dog Food").built
    rec = out.record
    assert (rec["regular_price"], rec["volume_deals_description"], rec["volume_deals_price"]) == (
        "2.25",
        "",
        "",
    )


# -- the search tile -----------------------------------------------------------------------------------------


def test_a_search_tile_is_read_like_a_listing_tile() -> None:
    html = page("o2_search_bananas_tiles.html.gz")
    grid, cards, sponsored, _ = grid_cards(html)
    assert grid and len(cards) == 23
    assert {c.card_testid.rsplit("-", 1)[0] for c in cards} == {"default-product-card"}
    assert sponsored == {"default-product-card-5", "default-product-card-9"}  # "Sponsored" on the tile
    bananas = next(c for c in cards if c.upc == "0000000004011")
    p = bananas.price
    assert p.kind is PriceDisplayKind.RELATIVE
    assert (p.current_text, p.sr_text) == ("$1.45", "about $1.45 each")
    assert bananas.ppm_text == ""  # the tile shows no price per pound for it


def test_an_estimated_item_price_is_never_exported_as_a_price(build: Any) -> None:
    name = "o2_search_bananas_tiles.html.gz"
    html = page(name)
    out = build(tiles(html)["0000000004011"], index(html, name), "Fresh Fruit").built
    assert out.record["regular_price"] == "" and out.record["sale_price"] == ""
    assert {RecordFlag.RELATIVE_PRICE, RecordFlag.ESTIMATED_PRICE_ONLY, RecordFlag.SOLD_BY_WEIGHT} <= set(
        out.flags
    )
    assert out.status is not RecordStatus.VALID


def test_the_savings_zone_is_read_and_a_one_cent_conflict_is_kept(build: Any) -> None:
    name = "o2_search_nutrl_tiles.html.gz"
    html = page(name)
    card = tiles(html)["0001820020352"]
    assert card.zone is not None
    assert (card.zone.text, card.zone.details, card.zone.requires_clip) == ("Buy 1 Save $2", True, False)
    assert (card.price.original_text, card.price.current_text) == ("$18.98", "$16.99")
    out = build(card, index(html, name), "Hard Seltzer").built
    # Displayed $18.98, the product's own data USD 18.99: both kept, the record is not counted as valid.
    assert out.status is RecordStatus.PRICE_CONFLICT
    assert RecordFlag.PRICE_DOM_JSON_MISMATCH in out.flags
    assert out.provenance["_price_observations"]["conflict"]["regular_price"] == {
        "displayed": "18.98",
        "product_data": "18.99",
    }
    # A buy-one saving is not a multi-unit volume offer (M6).
    assert out.record["volume_deals_description"] == "" and out.record["volume_deals_price"] == ""


def test_a_coupon_is_not_shown_on_the_tile() -> None:
    # Purina ONE: coupons 4257015 and 4257014 are on the product's own rendered page (stage O1), not its tile.
    html = page("o2_search_purina_one_tiles.html.gz")
    found = tiles(html)
    for upc in ("0001780014939", "0001780014941"):
        assert found[upc].zone is None and found[upc].price.kind is PriceDisplayKind.REGULAR


# -- rendered pages ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["s1_catfood_p1_rendered_nogrid.html.gz", "o2_cattreats_p2_rendered_nogrid.html.gz"]
)
def test_a_rendered_listing_page_has_no_tile_while_its_state_lists_the_products(name: str) -> None:
    assert SOURCES[name]["provider_run_js"] is True
    html = page(name)
    grid, cards, _, _ = grid_cards(html)
    assert not grid and cards == []
    assert len(state_of(html)) == 24


# -- what is not known is never read -------------------------------------------------------------------------


def edited_tile(name: str, upc: str, old: str, new: str) -> tuple[CardObservation, SourceIndex]:
    """A real tile with one text changed (``old`` -> ``new``), inside the grid container the parser reads."""
    html = page(name)
    assert grid_cards(html)[0]

    node = next(
        n
        for n in LexborHTMLParser(html).css('[data-testid^="horizontal-product-card-"]')
        if upc in (n.css_first('a[href*="/p/"]').attributes.get("href") or "")
    )
    outer = node.html or ""
    assert outer.count(old) == 1
    _, parsed, _, _ = grid_cards(f'<div data-testid="paginate-items">{outer.replace(old, new)}</div>')
    return parsed[0], index(html, name)


def test_a_price_form_not_seen_on_the_tile_gives_no_price(build: Any) -> None:
    # Changed: the sale tile's current price "$2.99" -> "2 For $5.00" (its screen-reader text unchanged).
    card, idx = edited_tile(
        "o2_cattreats_p1_tiles.html.gz",
        "0005849672306",
        '<span aria-hidden="true" class="citrus-Price--current-price ">$2.99</span>',
        '<span aria-hidden="true" class="citrus-Price--current-price ">2 For $5.00</span>',
    )
    assert card.price.kind is PriceDisplayKind.UNRECOGNIZED
    assert (card.price.regular_price, card.price.sale_price) == ("", "")
    assert "PRICE_DISPLAY_UNRECOGNIZED" in card.flags
    out = build(card, idx).built
    assert out.status is RecordStatus.EXPORTED_NOT_VALID
    assert out.record["regular_price"] == "" and out.record["sale_price"] == ""
    assert "does not know" in out.missing["regular_price"]
    assert out.provenance["_price_display_unrecognized"]["displayed_current"] == "2 For $5.00"


def test_a_price_per_measure_element_without_one_is_not_exported(build: Any) -> None:
    # Changed: the tile's price-per-measure text "$1.00/oz" -> "See store".
    card, idx = edited_tile(
        "o2_cattreats_p1_tiles.html.gz",
        "0005849672306",
        ">$1.00/oz<",
        ">See store<",
    )
    assert card.ppm_text == "" and "PPM_TEXT_UNRECOGNIZED" in card.flags
    out = build(card, idx).built
    assert out.record["ppm"] == "" and RecordFlag.PPM_TEXT_UNRECOGNIZED in out.flags


def test_the_cards_before_2026_11_06_are_read_as_before() -> None:
    grid, cards, _, _ = grid_cards((FIX / "q2_cards_m4.html").read_text("utf-8"))
    assert grid and len(cards) == 4
    assert all(c.layout == "card" and c.size_displayed and c.size_text for c in cards)
