"""The Mariano's steps (added in 1.6.0), OFFLINE.

Two kinds of input, never mixed up with evidence of what Classic returns:

- ``captures_marianos/``: two pages saved through the Oxylabs **Web API** on 2026-11-02 at Mariano's Vernon
  Hills (53100502) Pickup, already passed through the Mariano's collector's sanitizer. Here they are wrapped
  in a **SYNTHETIC** Classic envelope. They show that the probe reads a real Mariano's page as the collector
  does; they are not a Classic response.
- invented pages (``state_page``): **SYNTHETIC**, shaped like the page state the collector reads.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from classic_probe import campaign, checks, contract, gates, ledger, marianos, money, targets
from classic_probe.stops import Stop
from classic_probe.targets import Target
from classic_probe.transport import ProviderResponse, ReplayTransport
from tests import fixture_builder as fb
from tests.conftest import SYNTHETIC_RATES

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = Path(__file__).resolve().parent / "captures_marianos"
STORE = "53100502"
LAKESHORE = "53100503"
RATES: dict[str, Any] = {
    **SYNTHETIC_RATES,
    "rates": {
        **SYNTHETIC_RATES["rates"],
        "marianos_search": {"unit": "usd_per_result", "plain": "0.0015", "rendered": "0.0020"},
        "marianos_product": {"unit": "usd_per_result", "plain": "0.0015", "rendered": "0.0020"},
    },
}
VERNON = Target(
    retailer="marianos",
    store_id=STORE,
    store_address="Marianos Vernon Hills, 1720 N Milwaukee Ave, Vernon Hills, IL 60061",
    fulfillment="PICKUP",
    store_id_verified=True,
    store_id_evidence="test",
    adapter="marianos",
    search_query="cereal",
    category_probe_url="https://www.marianos.com/pl/cereal-granola/03001",
)


def saved(name: str) -> str:
    return gzip.decompress((CAPTURES / name).read_bytes()).decode("utf-8")


def envelope(html: str, *, status_code: int = 200, forced: bool = False) -> bytes:
    """A SYNTHETIC Classic envelope (the documented ``results[]`` of the Realtime method) around one page."""
    result = {
        "content": html,
        "status_code": status_code,
        "job_id": "job-synthetic",
        "is_render_forced": forced,
    }
    return json.dumps({"results": [result]}).encode("utf-8")


def state_page(state: dict[str, Any]) -> str:
    """A SYNTHETIC page holding ``state`` the way Mariano's pages do (``JSON.parse('…')``)."""
    literal = json.dumps(state).replace("\\", "\\\\").replace("'", "\\'")
    script = f"<script>window.__INITIAL_STATE__ = JSON.parse('{literal}');</script>"
    return f"<html><head></head><body>{script}</body></html>"


def preferences(store: str = STORE, modality: str = "PICKUP") -> dict[str, Any]:
    return {
        "getModalityPreferences": {
            "default": {
                "response": {
                    "data": {
                        "modalityPreferences": {
                            "modalities": [{"modalityType": modality, "destination": {"locationId": store}}]
                        }
                    }
                }
            }
        }
    }


def product_html(upc: str, store: str = STORE, page_store: str = STORE, modality: str = "PICKUP") -> str:
    data = {
        "upc": upc,
        "price": {"storePrices": {"sourceLocationId": store, "regular": {"price": "USD 3.99"}}},
    }
    state = {
        "calypso": {
            "useCases": preferences(page_store, modality),
            "domains": {"products": {upc: {"data": data}}},
        }
    }
    return state_page(state)


def inspect(body: bytes) -> checks.Inspection:
    return checks.provider(ProviderResponse(200, body))


# -- the documented contract ---------------------------------------------------------------------------------


def test_the_mariano_payloads_are_the_documented_ones() -> None:
    assert contract.marianos_search("cereal", STORE) == {
        "source": "marianos_search",
        "query": "cereal",
        "store_id": STORE,
        "fulfillment_type": "pickup",
    }
    assert contract.marianos_product("0001600027528", STORE)["product_id"] == "0001600027528"


@pytest.mark.parametrize("key", ["start_page", "pages", "parse", "domain", "page", "sort_by"])
def test_a_parameter_the_marianos_page_does_not_document_is_refused(key: str) -> None:
    payload = {**contract.marianos_search("cereal", STORE), key: 2}
    with pytest.raises(contract.UndocumentedRequest):
        contract.assert_documented(payload)


def test_the_documented_filters_and_the_store_rule() -> None:
    contract.assert_documented({**contract.marianos_search("cereal", STORE), "brand": "Kellogg's"})
    contract.assert_documented({**contract.marianos_search("cereal", STORE), "price_range": "2.00-5.00"})
    with pytest.raises(contract.UndocumentedRequest):
        contract.assert_documented({"source": "marianos_search", "query": "x", "fulfillment_type": "pickup"})
    with pytest.raises(contract.UndocumentedRequest):
        contract.marianos_product("4119211060", STORE)  # not the documented 13-digit ID


def test_no_second_page_can_be_planned_for_marianos() -> None:
    with pytest.raises(contract.UndocumentedRequest):
        contract.next_page_payload(contract.marianos_search("cereal", STORE), 2, 2)
    assert "start_page" in marianos.NOT_PLANNED["marianos-search-p2"]
    steps = [p.step for p in marianos.planned_steps(VERNON)]
    assert steps == ["marianos-search-p1", "marianos-product", "marianos-category-url"]
    assert marianos.planned_steps(VERNON)[2].payload == {
        "url": VERNON.category_probe_url
    }  # no store parameter


def test_the_shipped_targets_name_vernon_hills_and_never_lakeshore_east() -> None:
    _, tgts = targets.load(ROOT / "config" / "targets.json")
    m = tgts["marianos"]
    assert (m.store_id, m.fulfillment, m.adapter, m.store_id_verified) == (STORE, "PICKUP", "marianos", True)
    assert m.live_problems() == []
    data = json.loads((ROOT / "config" / "targets.json").read_text("utf-8"))
    data["retailers"]["marianos"]["store_id"] = LAKESHORE
    with pytest.raises(targets.TargetRefused):
        targets._target("marianos", data["retailers"]["marianos"])


# -- reading a page ------------------------------------------------------------------------------------------


def test_a_saved_vernon_hills_search_page_passes_in_a_synthetic_envelope() -> None:
    ins = marianos.search_page(inspect(envelope(saved("search_cereal_p1.html.gz"))), STORE)
    assert ins.stop is None, ins.detail
    assert (ins.facts["selected_location_id"], ins.facts["selected_modality"]) == (STORE, "PICKUP")
    assert ins.facts["request_location_id"] == STORE and ins.facts["product_stores"] == [STORE]
    assert len(ins.facts["ranked_upcs"]) == 24


def test_the_same_page_for_another_store_stops_the_campaign() -> None:
    html = saved("search_cereal_p1.html.gz").replace(STORE, LAKESHORE)
    ins = marianos.search_page(inspect(envelope(html)), STORE)
    assert ins.stop is Stop.WRONG_CONTEXT


def test_another_fulfillment_stops_the_campaign() -> None:
    html = state_page({"calypso": {"useCases": preferences(STORE, "IN_STORE")}})
    ins = marianos.search_page(inspect(envelope(html)), STORE)
    assert ins.stop is Stop.WRONG_CONTEXT and "IN_STORE" in ins.detail


@pytest.mark.parametrize(
    ("html", "status", "stop"),
    [
        ("<html><title>Access Denied</title>Reference #18.1a2b.123</html>", 200, Stop.BLOCKED),
        ("<html><body>no state at all</body></html>", 200, Stop.UNVERIFIED_CONTEXT),
        ("<html></html>", 403, Stop.BLOCKED),
    ],
)
def test_a_refusal_or_a_page_without_state_stops_the_campaign(html: str, status: int, stop: Stop) -> None:
    ins = marianos.search_page(inspect(envelope(html, status_code=status)), STORE)
    assert ins.stop is stop


def test_a_saved_category_page_passes_and_a_product_page_needs_its_own_product() -> None:
    cat = marianos.category_page(inspect(envelope(saved("listing_03001_p1.html.gz"), forced=True)), STORE)
    assert cat.stop is None, cat.detail
    ok = marianos.product_page(inspect(envelope(product_html("0001600027528"))), STORE, "0001600027528")
    assert ok.stop is None, ok.detail
    other = marianos.product_page(inspect(envelope(product_html("0001600027528"))), STORE, "0003800000001")
    assert other.stop is Stop.WRONG_IDENTITY
    priced_elsewhere = marianos.product_page(
        inspect(envelope(product_html("0001600027528", store=LAKESHORE))), STORE, "0001600027528"
    )
    assert priced_elsewhere.stop is Stop.WRONG_CONTEXT


# -- the campaign on the shared ledger -----------------------------------------------------------------------


def complete() -> dict[str, list[tuple[int, bytes]]]:
    search = saved("search_cereal_p1.html.gz")
    first = marianos.search_page(inspect(envelope(search)), STORE).facts["ranked_upcs"][0]
    return {
        "marianos-search-p1": [(200, envelope(search))],
        "marianos-product": [(200, envelope(product_html(first), forced=True))],
        "marianos-category-url": [(200, envelope(saved("listing_03001_p1.html.gz"), forced=True))],
    }


def run_marianos(led: ledger.Ledger, tmp: Path, steps: dict[str, list[tuple[int, bytes]]], **kw: Any) -> Any:
    tr = ReplayTransport({k: [ProviderResponse(s, b) for s, b in v] for k, v in steps.items()})
    card = money.RateCard.load(kw.pop("rates", RATES))
    result = marianos.MarianosCampaign(led, tr, kw.pop("target", VERNON), card, out_dir=tmp, **kw).run()
    return result, tr


def test_a_complete_answer_takes_three_requests_each_reserved_first(make_ledger: Any, tmp_path: Path) -> None:
    led = make_ledger()
    result, tr = run_marianos(led, tmp_path / "out", complete())
    assert result.stop is None, result.detail
    assert [r.step for r in tr.dispatched] == [
        "marianos-search-p1",
        "marianos-product",
        "marianos-category-url",
    ]
    rows = led.rows()
    assert [r["retailer"] for r in rows] == ["marianos"] * 3 and all(r["state"] == "answered" for r in rows)
    assert any("marianos-search-p2" in e["detail"] for e in led.events() if e["kind"] == "SKIPPED")
    evidence = json.loads((tmp_path / "out" / "campaign_evidence.json").read_text("utf-8"))
    assert all(p["state_script_kept"] for r in evidence["responses"] for p in r["raw_pages"])


def test_both_retailers_share_one_ledger_and_neither_gets_a_fresh_allowance(
    make_ledger: Any, tmp_path: Path
) -> None:
    led = make_ledger()
    w = campaign.Campaign(
        led,
        ReplayTransport({k: [ProviderResponse(s, b) for s, b in v] for k, v in fb.complete().items()}),
        targets.load(ROOT / "config" / "targets.json")[1]["walmart"],
        money.RateCard.load(RATES),
        out_dir=tmp_path / "w",
    ).run()
    assert w.stop is None, w.detail
    m, _ = run_marianos(led, tmp_path / "m", complete())
    assert m.stop is None, m.detail
    totals = led.totals().as_dict()
    assert totals["dispatched_total"] == 7 and totals["dispatched_by_retailer"] == {
        "walmart": 4,
        "marianos": 3,
    }
    # a restart of the Mariano's part on the same ledger continues the counts: nothing is reset
    run_marianos(led, tmp_path / "m2", complete())
    assert led.totals().as_dict()["dispatched_by_retailer"]["marianos"] == 6


def test_a_wrong_store_category_page_stops_and_nothing_more_is_sent(make_ledger: Any, tmp_path: Path) -> None:
    steps = complete()
    steps["marianos-category-url"] = [
        (200, envelope(saved("listing_03001_p1.html.gz").replace(STORE, LAKESHORE)))
    ]
    result, tr = run_marianos(make_ledger(), tmp_path / "out", steps)
    assert result.stop == Stop.WRONG_CONTEXT.value and len(tr.dispatched) == 3


def test_an_unknown_marianos_rate_prevents_the_first_dispatch(make_ledger: Any, tmp_path: Path) -> None:
    led = make_ledger()
    result, tr = run_marianos(led, tmp_path / "out", complete(), rates=SYNTHETIC_RATES)
    assert result.stop == Stop.FUNDS.value and tr.dispatched == [] and led.rows() == []


def test_live_is_refused_for_marianos_and_lists_what_it_lacks(make_ledger: Any) -> None:
    missing = gates.evaluate(
        make_ledger(), approval=None, entitlement=None, rates=None, credentials=False, retailer="marianos"
    )
    assert "no explicit approval" in missing and "credentials are not present" in missing
    entitled = {
        "verified": True,
        "verified_by": "x",
        "targets": ["walmart_search"],
        "response_mode": "realtime",
    }
    missing = gates.evaluate(
        make_ledger("l2.sqlite3"),
        approval=None,
        entitlement=entitled,
        rates=RATES,
        credentials=False,
        retailer="marianos",
    )
    assert "no verified entitlement for marianos_search" in missing
    assert any("SYNTHETIC" in m for m in missing)
    assert gates.LIVE_ENABLED is False
