"""Release 1.9.0rc3: a tile's empty coupon zone is not an observed absence.

Stage O2 (2026-11-06, Vernon Hills 53100502, PICKUP) saved the search page for "purina one dry dog food": its
tiles for 0001780014939 and 0001780014941 show no savings zone at all. Stage O1, about an hour earlier, saved
the same products' own pages: 0001780014939's, rendered, shows coupon 4257015 ("Save $10.00 on 2 Purina ONE")
and the cash-back offer 4257014; the provider brought 0001780014941's without running its scripts, where no
coupon can be seen. All pages are real (tests/fixtures/oxylabs_2026-11-06: SOURCES_TILES.json, SOURCES.json);
the live collector reads a product's page in the same run as its tile, these tests combine the two stages'
captures. One test adds a hand-made Savings document (a rendered page without coupons), marked as such: no
saved product page was both rendered and without coupons."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from marianos_headless.assembly.offers import OfferKind, OfferSource
from marianos_headless.assembly.private_label import PrivateLabelDetector
from marianos_headless.assembly.record_builder import (
    COUPON_UNKNOWN,
    CategoryAssignment,
    MissingKind,
    RecordStatus,
    StoreFields,
)
from marianos_headless.collection.live import CardBuild, build_card, grid_cards
from marianos_headless.core.findings import RecordFlag
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig, load_stores
from marianos_headless.sites.marianos.dom_parsers import CardObservation
from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.pdp_savings import savings_document
from marianos_headless.sites.marianos.search_state import state_products
from marianos_headless.sites.marianos.source_json import PDP_SAVINGS, PRODUCTS, ResponseRef, SourceIndex

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "oxylabs_2026-11-06"
SOURCES = json.loads((FIX / "SOURCES_TILES.json").read_text("utf-8"))
SEARCH = "o2_search_purina_one_tiles.html.gz"
RENDERED = "pdp_0001780014939_rendered.html.gz"
UNRENDERED = "pdp_0001780014941_unrendered.html.gz"
PURINA, PURINA_LAMB = "0001780014939", "0001780014941"
VH = StoreFields(
    "60061",
    "Marianos Vernon Hills",
    "1720 N Milwaukee Ave, Vernon Hills, IL 60061",
    "https://www.marianos.com/cdn/images/multiColor-4Jf6i6B.svg",
)


def page(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode("utf-8")


def index(
    pdp: dict[str, tuple[str, bool | None]] | None = None, *, hand_made: dict[str, Any] | None = None
) -> SourceIndex:
    """The search page's own product data (as the collector indexes it), plus the Savings section of the given
    product pages (``upc: (page, rendered)``) or of hand-made documents (``hand_made``)."""
    html = page(SEARCH)
    idx = SourceIndex()
    doc = {"data": {"products": state_products(parse_initial_state(html))}}
    sha = SOURCES[SEARCH].get("file_sha256") or SOURCES[SEARCH].get("sanitized_html_sha256")
    idx.add(PRODUCTS, json.dumps(doc), ResponseRef(PRODUCTS, "O2-search", sha, "2026-11-06T19:48:00Z"))
    for upc, (name, rendered) in (pdp or {}).items():
        sd = savings_document(page(name), upc=upc, rendered=rendered, requested_run_js=True)
        idx.add(
            PDP_SAVINGS,
            json.dumps(sd),
            ResponseRef(PDP_SAVINGS, "O1-" + upc, "d" * 64, "2026-11-06T18:40:00Z"),
        )
    for upc, sd in (hand_made or {}).items():
        idx.add(
            PDP_SAVINGS,
            json.dumps(sd),
            ResponseRef(PDP_SAVINGS, "HAND-" + upc, "e" * 64, "2026-11-06T18:40:00Z"),
        )
    return idx


@pytest.fixture(scope="module")
def tiles() -> dict[str, CardObservation]:
    grid, cards, _, _ = grid_cards(page(SEARCH))
    assert grid
    out = {c.upc or "": c for c in cards}
    for upc in (PURINA, PURINA_LAMB):  # the tiles show no savings zone at all
        assert out[upc].layout == "tile" and out[upc].zone is None
    return out


@pytest.fixture
def build(settings: Settings, private_label: PrivateLabelConfig) -> Any:
    store: StoreConfig = next(
        s for s in load_stores(ROOT / "config" / "stores.yaml").stores if s.key == "marianos-53100502-pickup"
    )
    detector = PrivateLabelDetector(private_label, settings.records.store_brand_positive_value)

    def run(card: CardObservation, idx: SourceIndex) -> CardBuild:
        return build_card(
            card,
            fetch_id="F-search",
            observed_at="2026-11-06T19:48:00+00:00",
            store=store,
            store_values=VH,
            store_provenance={},
            category=CategoryAssignment("Pet Supplies", "Dog Food"),
            crawl_date="2026-11-06",
            settings=settings,
            detector=detector,
            sources=idx,
        )

    return run


def test_a_tile_whose_page_was_not_read_leaves_the_coupon_unknown(
    tiles: dict[str, CardObservation], build: Any
) -> None:
    b = build(tiles[PURINA], index()).built
    assert b.record["digital_deals_description"] == "" and b.record["digital_deals_price"] == ""
    for name in ("digital_deals_description", "digital_deals_price"):
        assert COUPON_UNKNOWN in b.missing[name] and "was not read" in b.missing[name]
        assert "no digital coupon is displayed" not in b.missing[name]
        assert b.missing_kind[name] == MissingKind.NOT_ATTEMPTED.value
    assert RecordFlag.DIGITAL_COUPONS_UNOBSERVED in b.flags
    # Informational: the record's disposition is decided as before (1.9.0rc2 gave the same).
    assert b.status is RecordStatus.VALID


def test_a_tile_whose_rendered_page_shows_coupons_gets_them_with_their_terms(
    tiles: dict[str, CardObservation], build: Any
) -> None:
    b = build(tiles[PURINA], index({PURINA: (RENDERED, True)})).built
    desc = b.record["digital_deals_description"]
    assert desc.startswith(
        "Coupon: Save $10.00 on 2 Purina ONE — Save $10.00 on any TWO (2) Purina ONE Dry Dog Food bags "
        "(8 lb or larger) or Wet Dog Food 12-count packages (13 oz cans). Mix or match. NOT FOR RESALE."
    )
    assert desc.endswith("(Exp. Nov. 10; Sign In To Clip)")
    assert b.record["digital_deals_price"] == ""  # savings wording: no price derived
    digital = [c for c in b.deals.classified if c.kind is OfferKind.DIGITAL]
    assert len(digital) == 1 and digital[0].offer.coupon_id == "4257015"
    assert set(digital[0].offer.sources) == {OfferSource.PDP}  # the tile showed none
    assert RecordFlag.DIGITAL_COUPONS_UNOBSERVED not in b.flags
    assert RecordFlag.DIGITAL_TERMS_UNREAD not in b.flags
    assert "digital_deals_description" not in b.missing


def test_a_tile_whose_page_came_unrendered_stays_unknown(
    tiles: dict[str, CardObservation], build: Any
) -> None:
    b = build(tiles[PURINA_LAMB], index({PURINA_LAMB: (UNRENDERED, False)})).built
    assert b.record["digital_deals_description"] == ""
    reason = b.missing["digital_deals_description"]
    assert COUPON_UNKNOWN in reason and "was not brought rendered" in reason
    assert b.missing_kind["digital_deals_description"] == MissingKind.NOT_ATTEMPTED.value
    assert RecordFlag.DIGITAL_COUPONS_UNOBSERVED in b.flags


def test_a_rendered_page_without_coupons_is_an_observed_absence(
    tiles: dict[str, CardObservation], build: Any
) -> None:
    # HAND-MADE Savings document (not a capture): the page rendered, its Savings section without any row.
    none = {
        "data": {"upc": PURINA_LAMB, "requested_run_js": True, "rendered": True, "section": False, "rows": []}
    }
    b = build(tiles[PURINA_LAMB], index(hand_made={PURINA_LAMB: none})).built
    reason = b.missing["digital_deals_description"]
    assert reason.startswith("neither the tile nor the product's own page, rendered, shows an applicable")
    assert COUPON_UNKNOWN not in reason
    assert b.missing_kind["digital_deals_description"] == MissingKind.NOT_DISPLAYED.value
    assert RecordFlag.DIGITAL_COUPONS_UNOBSERVED not in b.flags


def test_a_card_with_an_empty_zone_keeps_its_observed_absence(build: Any) -> None:
    # The cards up to 2026-11-04 show a product's coupon in its savings zone: an empty zone is an absence.
    grid, cards, _, _ = grid_cards((FIX / "q2_cards_rc2_no_quantity.html").read_text("utf-8"))
    assert grid and cards
    card = next(c for c in cards if c.zone is None)
    assert card.layout == "card"
    b = build(card, SourceIndex()).built
    assert b.missing["digital_deals_description"] == "no digital coupon is displayed"
    assert b.missing_kind["digital_deals_description"] == MissingKind.NOT_DISPLAYED.value
    assert RecordFlag.DIGITAL_COUPONS_UNOBSERVED not in b.flags
