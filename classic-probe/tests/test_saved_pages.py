"""The probe's checks on saved walmart.com pages: OFFLINE REPLAY of AUTHENTIC pages inside SYNTHETIC Classic
envelopes.

The pages are real Walmart pages that the Walmart collector saved; tests/captures/MANIFEST.json says where
each came from, and none came through Classic. The Classic envelope around each page and its parsed
counterpart are SYNTHETIC, built from the page's own data. These tests show that the probe reads real Walmart
page data as the collector does; they show nothing about what Classic returns for these pages.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from classic_probe import campaign, checks, ledger, money
from classic_probe.stops import Stop
from classic_probe.transport import ProviderResponse, ReplayTransport
from classic_probe.vendor import walmart_page_data as wpd
from tests import fixture_builder as fb
from tests.test_campaign import WALMART

CAPTURES = Path(__file__).parent / "captures"


def page(name: str) -> str:
    return gzip.decompress((CAPTURES / name).read_bytes()).decode("utf-8")


def parsed_for(html: str, *, page_no: int, last: int, store: str = "3891") -> dict[str, Any]:
    """A SYNTHETIC parsed result made from the page's own products (what a parser that agrees would say)."""
    items = wpd.page_items(wpd.next_data(html))
    return {
        "location": {"city": "Waukegan", "state": "IL", "store_id": store, "zipcode": "60085"},
        "page_details": {"last_visible_page": last, "page": page_no, "total_results": 1200},
        "parse_status_code": 12000,
        "results": [
            {
                "general": {"product_id": it.item_id, "title": it.name, "sponsored": it.sponsored},
                "seller": {"name": it.seller_name},
            }
            for it in items
        ],
    }


def inspect(raw: str | None, parsed: dict[str, Any] | None) -> checks.Inspection:
    return checks.provider(ProviderResponse(200, fb.envelope(raw, parsed)))


P1, P2 = "w1_diapering_page1.html.gz", "w1_diapering_page2.html.gz"
PRODUCT, CHALLENGE, CATEGORY = (
    "product_walmart_seller_15268670678.html.gz",
    "store_3891_challenge.html.gz",
    "strawberries_page1.html.gz",
)


def test_each_saved_page_is_the_recorded_copy() -> None:
    manifest = json.loads((CAPTURES / "MANIFEST.json").read_text("utf-8"))
    files = {f["file"]: f["sha256"] for f in manifest["files"]}
    assert set(files) == {p.name for p in CAPTURES.glob("*.html.gz")}
    for name, sha in files.items():
        assert hashlib.sha256((CAPTURES / name).read_bytes()).hexdigest() == sha, name


def test_a_real_result_page_for_store_3891_pickup_passes_the_search_checks() -> None:
    html = page(P1)
    ins = checks.search_page(inspect(html, parsed_for(html, page_no=1, last=25)), "3891", 1, None)
    assert ins.stop is None, ins.detail
    f = ins.facts
    assert (f["page_store"], f["page_intent"], f["parsed_store"]) == ("3891", "PICKUP", "3891")
    assert (f["items"], f["walmart_seller"], f["sponsored"], f["with_pickup_line"]) == (50, 39, 10, 33)
    assert (f["page_data_page"], f["page_data_max_page"]) == (1, 25)
    assert f["challenge_signals"] == []


def test_the_same_real_page_is_refused_for_any_other_store() -> None:
    html = page(P1)
    ins = checks.search_page(
        inspect(html, parsed_for(html, page_no=1, last=25, store="5260")), "5260", 1, None
    )
    assert ins.stop is Stop.WRONG_CONTEXT
    assert "store 3891 PICKUP, not 5260" in ins.detail


def test_real_page_2_advances_and_page_1_served_again_is_refused() -> None:
    p1, p2 = page(P1), page(P2)
    first = checks.search_page(inspect(p1, parsed_for(p1, page_no=1, last=25)), "3891", 1, None)
    ids = frozenset(first.facts["item_ids"])
    second = checks.search_page(inspect(p2, parsed_for(p2, page_no=2, last=25)), "3891", 2, ids)
    assert second.stop is None, second.detail
    assert second.facts["page_data_page"] == 2 and set(second.facts["item_ids"]) - ids
    again = checks.search_page(inspect(p1, parsed_for(p1, page_no=1, last=25)), "3891", 2, ids)
    assert again.stop is Stop.REPEATED_PAGE


def test_a_parsed_result_naming_a_product_the_page_does_not_hold_is_refused() -> None:
    html = page(P1)
    parsed = parsed_for(html, page_no=1, last=25)
    parsed["results"].append({"general": {"product_id": "999999999999"}})
    ins = checks.search_page(inspect(html, parsed), "3891", 1, None)
    assert ins.stop is Stop.UNSUPPORTED_RESPONSE


def test_a_real_product_page_passes_identity_store_and_upc_and_refuses_for_another_item() -> None:
    html = page(PRODUCT)
    parsed = fb.parsed_product("15268670678", gtin="070969002636")
    ins = checks.product_page(inspect(html, parsed), "3891", "15268670678")
    assert ins.stop is None, ins.detail
    f = ins.facts
    assert (f["page_item"], f["upc"], f["parsed_gtin"], f["page_store"], f["page_intent"]) == (
        "15268670678",
        "070969002636",
        "070969002636",
        "3891",
        "PICKUP",
    )
    other = checks.product_page(inspect(html, fb.parsed_product("15163163334")), "3891", "15163163334")
    assert other.stop is Stop.WRONG_IDENTITY


def test_the_real_challenge_page_stops_as_blocked() -> None:
    ins = checks.search_page(inspect(page(CHALLENGE), fb.parsed_search(fb.PAGE1)), "3891", 1, None)
    assert ins.stop is Stop.BLOCKED
    assert {"perimeterx_captcha", "perimeterx_robot_or_human"} <= set(ins.facts["challenge_signals"])


def test_a_real_category_page_shows_the_store_it_was_served_for() -> None:
    ins = checks.category_page(inspect(page(CATEGORY), None), "3891")
    assert ins.stop is None, ins.detail
    assert (ins.facts["page_store"], ins.facts["page_intent"], ins.facts["items"]) == ("3891", "PICKUP", 2)
    assert checks.category_page(inspect(page(CATEGORY), None), "5260").stop is Stop.WRONG_CONTEXT


def test_a_campaign_on_saved_pages_stops_at_a_product_page_for_another_item(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    p1, p2 = page(P1), page(P2)
    steps = {
        "walmart-search-p1": [ProviderResponse(200, fb.envelope(p1, parsed_for(p1, page_no=1, last=25)))],
        "walmart-search-p2": [ProviderResponse(200, fb.envelope(p2, parsed_for(p2, page_no=2, last=25)))],
        # The saved product page is item 15268670678's, not the first product of the diapering page.
        "walmart-product": [
            ProviderResponse(200, fb.envelope(page(PRODUCT), fb.parsed_product("15268670678")))
        ],
        "walmart-category-url": [ProviderResponse(200, fb.envelope(page(CATEGORY), None))],
    }
    led = make_ledger()
    tr = ReplayTransport(steps)
    result = campaign.Campaign(led, tr, WALMART, card, out_dir=tmp_path / "out").run()
    assert [r.step for r in tr.dispatched] == ["walmart-search-p1", "walmart-search-p2", "walmart-product"]
    assert result.stop == Stop.WRONG_IDENTITY.value
    chosen = tr.dispatched[2].payload["product_id"]
    first = wpd.page_items(wpd.next_data(p1))
    expected = next(
        it.item_id
        for it in first
        if it.seller_name == "Walmart.com"
        and not it.sponsored
        and any(x.kind == "PICKUP" for x in it.fulfillment)
    )
    assert chosen == expected != "15268670678"
    assert [r["state"] for r in led.rows()] == [ledger.ANSWERED] * 3
    assert "walmart-category-url" not in {r["step"] for r in led.rows()}  # nothing is sent after a stop
