from __future__ import annotations

from marianos_headless.core.findings import DataMode
from marianos_headless.core.schema import build_record
from marianos_headless.core.settings import Settings
from marianos_headless.validation.gates import (
    AttestationSummary,
    CategoryOutcome,
    GateStatus,
    RunEvidence,
    deal_price_supported,
    run_gates,
)

S = Settings()


def rec(upc: str, **kw: str) -> dict[str, str]:
    base = {
        "upc": upc,
        "product_title": "T",
        "url": f"https://www.marianos.com/p/t/{upc}",
        "category": "Produce",
        "regular_price": "1.00",
        "crawl_date": "2026-10-17",
    }
    return build_record({**base, **kw})


def good_evidence(n: int = 600) -> RunEvidence:
    records = [rec(f"{i:013d}", category=["Produce", "Meat", "Dairy"][i % 3]) for i in range(n)]
    return RunEvidence(
        mode=DataMode.LIVE,
        attestations=(AttestationSummary("preflight", True), AttestationSummary("final", True)),
        categories=(CategoryOutcome(1, "Produce", "DONE", 200, 210, node_coverage={"06111": 0.99}),),
        exported_records=records,
        valid_upcs=frozenset(r["upc"] for r in records),
        contract_canary_ok=True,
        tasks_all_terminal=True,
        artifact_hashes_verified=True,
        manifest_complete=True,
    )


def status(ev: RunEvidence) -> dict[str, GateStatus]:
    return {r.gate: r.status for r in run_gates(ev, S).results}


def test_good_run_is_publishable_and_contest_ready() -> None:
    out = run_gates(good_evidence(), S)
    assert out.publishable and out.contest_ready, [(r.gate, r.findings) for r in out.results if r.findings]


def test_location_failure_blocks_publication() -> None:
    ev = good_evidence()
    ev.attestations = (
        AttestationSummary("preflight", True),
        AttestationSummary("periodic", False, ("A4",)),
        AttestationSummary("final", True),
    )
    out = run_gates(ev, S)
    assert status(ev)["G1"] is GateStatus.FAIL and not out.publishable


def test_duplicate_upc_fails_g7() -> None:
    ev = good_evidence(10)
    ev.exported_records = [*ev.exported_records, ev.exported_records[0]]
    assert status(ev)["G7"] is GateStatus.FAIL


def test_yield_drop_thresholds() -> None:
    ev = good_evidence()
    ev.categories = (CategoryOutcome(1, "Produce", "DONE", 60, 100),)
    assert status(ev)["G4"] is GateStatus.WARN
    ev.categories = (CategoryOutcome(1, "Produce", "DONE", 40, 100),)
    assert status(ev)["G4"] is GateStatus.FAIL
    ev.categories = (CategoryOutcome(1, "Produce", "DONE", 0, 0),)
    assert status(ev)["G4"] is GateStatus.FAIL
    ev.categories = (CategoryOutcome(1, "Produce", "DONE", 0, 0, zero_rule_holds=True),)
    assert status(ev)["G4"] is GateStatus.PASS


def test_coverage_thresholds() -> None:
    ev = good_evidence()
    ev.categories = (CategoryOutcome(1, "Produce", "DONE", 200, None, node_coverage={"06111": 0.95}),)
    assert status(ev)["G3"] is GateStatus.WARN
    ev.categories = (CategoryOutcome(1, "Produce", "DONE", 200, None, node_coverage={"06111": 0.80}),)
    assert status(ev)["G3"] is GateStatus.FAIL
    ev.categories = (CategoryOutcome(1, "Produce", "BLOCKED", 200, None),)
    st = status(ev)
    assert st["G2"] is GateStatus.FAIL and st["G3"] is GateStatus.FAIL


def test_fixture_mode_is_never_contest_ready() -> None:
    ev = good_evidence()
    ev.mode = DataMode.FIXTURE
    out = run_gates(ev, S)
    assert out.publishable and not out.contest_ready


def test_promotion_sanity() -> None:
    assert deal_price_supported("2 For $5.00", "5.00")
    assert deal_price_supported("4/$10 when you buy 4 or more", "10.00")
    assert not deal_price_supported("Buy 1, Get 1 Free", "2.50")
    ev = good_evidence(10)
    ev.exported_records = [
        rec("0000000000001", volume_deals_description="Buy 1, Get 1 Free", volume_deals_price="2.50")
    ]
    assert status(ev)["G11"] is GateStatus.FAIL


def test_missing_integrity_and_contract_fail() -> None:
    ev = good_evidence()
    ev.contract_canary_ok = None
    ev.manifest_complete = False
    st = status(ev)
    assert st["G12"] is GateStatus.FAIL and st["G13"] is GateStatus.FAIL
