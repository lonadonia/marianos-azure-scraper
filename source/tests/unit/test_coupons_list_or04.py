"""OR-04 (release 1.10.0rc6): what a rendered page shows of its coupons, read as one of three states.

The Coupons page (the client's CSV row 0). REAL pages stored on 2026-11-16
(``tests/fixtures/oxylabs_2026-11-16``): one with its list loaded ("450 Coupons", 24 coupon cards) and one
rendered before its list loaded (the site's loading indicator in the coupons tab, no count, no card), which
1.10.0rc5 recorded as read with 0 coupons, as in seven of twelve runs. No stored page shows a loaded, empty
list: the tests that need one DERIVE it from the loaded page (cards removed, its count set) and say so.

A product's own page (the coupon terms of one product). DERIVED from the REAL rendered page of 0001780014939
(stage O1, 2026-11-06): its Savings section replaced by the site's loading indicator. A page still loading
cannot prove that a product has no coupon.

Expected to FAIL on 1.10.0rc5, which has none of these readings."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from types import SimpleNamespace

from selectolax.lexbor import LexborHTMLParser

from marianos_headless.assembly import record_builder
from marianos_headless.collection.nodes import load_seed, plan_nodes
from marianos_headless.sites.marianos import dom_parsers, observations, pdp_savings
from marianos_headless.sites.marianos.source_json import PDP_SAVINGS, ResponseRef, SourceIndex

FIX = Path(__file__).resolve().parents[1] / "fixtures"
LOADED = FIX / "oxylabs_2026-11-16" / "coupons_loaded_24_cards.html.gz"
SPINNER = FIX / "oxylabs_2026-11-16" / "coupons_not_loaded_spinner.html.gz"
PDP = FIX / "oxylabs_2026-11-06" / "pdp_0001780014939_rendered.html.gz"
INDICATOR = (
    '<div data-citrus-component="LoadingIndicator" role="status" class="citrus-LoadingIndicator">'
    '<svg aria-hidden="true" viewBox="0 0 100 100"></svg></div>'
)


def _html(path: Path) -> str:
    return gzip.decompress(path.read_bytes()).decode("utf-8")


def _derived_list(count: str | None, *, cards: bool = False, indicator: bool = False) -> str:
    """DERIVED from the real loaded Coupons page: its coupon cards removed (unless ``cards``), its count
    replaced (or removed when ``count`` is None), the loading indicator added in the coupons tab if asked."""
    tree = LexborHTMLParser(_html(LOADED))
    if not cards:
        for n in tree.css('[data-testid^="CouponCard-"]'):
            n.decompose()
    html = tree.html or ""
    stated = tree.css_first('[data-testid="coupons-count-format"]')
    assert stated is not None
    shown = stated.html or ""
    if count is None:
        html = html.replace(shown, "", 1)
    else:
        html = html.replace(shown, shown.replace("450 Coupons", count), 1)
    if indicator:
        html = html.replace('<div class="infinite-scroll-component__outerdiv">', INDICATOR, 1)
    return html


def test_or04_the_real_coupons_page_with_its_list_loaded_is_read_with_its_cards() -> None:
    r = dom_parsers.coupon_list_reading(_html(LOADED))
    assert (r.state, r.count_stated, r.cards, r.loading_indicator) == ("loaded_with_cards", 450, 24, False)
    assert "24 coupon card" in r.detail and "450 Coupons" in r.detail


def test_or04_the_real_coupons_page_rendered_before_its_list_loaded_is_not_read() -> None:
    r = dom_parsers.coupon_list_reading(_html(SPINNER))
    assert (r.state, r.count_stated, r.cards, r.loading_indicator) == ("not_loaded", None, 0, True)
    assert "loading indicator" in r.detail and "no coupon count" in r.detail


def test_or04_a_loaded_empty_list_derived_from_the_real_page_is_read_as_empty() -> None:
    r = dom_parsers.coupon_list_reading(_derived_list("0 Coupons"))
    assert (r.state, r.count_stated, r.cards, r.loading_indicator) == ("loaded_empty", 0, 0, False)


def test_or04_derived_lists_that_prove_nothing_are_not_read() -> None:
    # a count of coupons and no card drawn; no count and no card; an empty count beside the loading indicator
    for html in (
        _derived_list("450 Coupons"),
        _derived_list(None),
        _derived_list("0 Coupons", indicator=True),
    ):
        r = dom_parsers.coupon_list_reading(html)
        assert r.state == "not_loaded" and r.cards == 0, r


def test_or04_cards_drawn_are_read_even_beside_a_loading_indicator() -> None:
    # (the next cards of the infinite list loading below the first ones)
    r = dom_parsers.coupon_list_reading(_derived_list("450 Coupons", cards=True, indicator=True))
    assert (r.state, r.cards, r.loading_indicator) == ("loaded_with_cards", 24, True)


def _loading_pdp() -> str:
    """DERIVED from the real rendered product page of 0001780014939: its Savings section replaced by the
    site's loading indicator."""
    tree = LexborHTMLParser(_html(PDP))
    section = tree.css_first(pdp_savings.SECTION)
    assert section is not None
    html = tree.html or ""
    return html.replace(section.html or "", INDICATOR, 1)


def test_or04_a_product_page_still_loading_is_read_as_loading_and_proves_no_absence() -> None:
    real = pdp_savings.savings_document(_html(PDP), upc="0001780014939", rendered=True, requested_run_js=True)
    assert real["data"]["loading"] is False and real["data"]["rows"]
    doc = pdp_savings.savings_document(
        _loading_pdp(), upc="0001780014939", rendered=True, requested_run_js=True
    )
    assert doc["data"]["loading"] is True and doc["data"]["rows"] == [] and doc["data"]["section"] is False
    sources = SourceIndex()
    ref = ResponseRef(kind=PDP_SAVINGS, fetch_id="f-1", sha256=None, observed_at="2026-11-16T18:00:00Z")
    sources.add(PDP_SAVINGS, json.dumps(doc), ref)
    read = sources.terms_read("0001780014939")
    assert read is not None and read.loading is True and read.coupon_ids == ()
    assert observations.page_read_of(read) == "loading"
    assert observations.page_read_of(None) == ""


def test_or04_a_tile_whose_product_page_was_still_loading_has_an_unknown_coupon() -> None:
    evidence = SimpleNamespace(listing_shows_coupons=False, product_page_read="loading")
    reason = record_builder.no_coupon_reason(evidence)  # type: ignore[arg-type]
    assert "still loading" in reason and record_builder.COUPON_UNKNOWN in reason


def test_or04_the_plan_names_the_coupons_row_as_a_route_of_the_run() -> None:
    seed = load_seed()
    sources = {
        int(r["row_index"]): (r["category"], f"id{r['row_index']}", str(r.get("url") or ""))
        for r in seed["rows"]
    }
    sources[0] = ("Coupons", "id0", "https://www.marianos.com/savings/cl/coupons/")
    _, skipped = plan_nodes(seed, sources, [], {})
    [route] = [s for s in skipped if s.get("route")]
    assert route["route"] == "coupons" and route["row"] == 0 and route["category"] == "Coupons"
    assert route["url"] == "https://www.marianos.com/savings/cl/coupons/"
    _, narrowed = plan_nodes(seed, sources, [8], {})
    assert not [s for s in narrowed if s.get("route")]  # a run without the Coupons row has no such route
