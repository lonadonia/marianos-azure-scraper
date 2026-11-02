"""The shared campaign limits (OFFLINE, isolated ledgers in temporary folders; never a production budget)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from classic_probe import ledger, money
from classic_probe.stops import Stop
from tests.conftest import FakeClock, reserve

ROOT = Path(__file__).resolve().parents[1]


def test_the_eleventh_request_of_a_retailer_and_the_twenty_first_of_the_campaign_are_never_reserved(
    make_ledger: Any,
) -> None:
    led = make_ledger()
    for i in range(10):
        reserve(led, "walmart", step=f"w{i}")
    with pytest.raises(ledger.LimitReached) as exc:
        reserve(led, "walmart", step="w10")
    assert exc.value.stop is Stop.RETAILER_QUOTA
    for i in range(10):  # the other retailer's ten are still there: nothing was borrowed
        reserve(led, "marianos", step=f"m{i}")
    with pytest.raises(ledger.LimitReached) as exc:
        reserve(led, "marianos", step="m10")
    assert exc.value.stop is Stop.TOTAL_REQUESTS
    rows = led.rows()
    assert len(rows) == 20
    assert sum(r["retailer"] == "walmart" for r in rows) == 10


def test_one_retailer_cannot_take_the_other_retailers_requests_or_money(make_ledger: Any) -> None:
    led = make_ledger()
    for i in range(10):
        reserve(led, "walmart", step=f"w{i}")
    assert led.retailer_stopped("walmart") is None  # a refusal is not yet a stop
    with pytest.raises(ledger.LimitReached):
        reserve(led, "walmart", step="w10")
    assert led.totals().dispatched_by_retailer == {"walmart": 10}
    # Money: each retailer's share is half of what may be spent (USD 5.00 less 0.50 of headroom).
    led2 = make_ledger("money.sqlite3")
    assert led2.limits.retailer_share_usd() == Decimal("2.25")
    reserve(led2, "walmart", amount="2.25", step="big")
    with pytest.raises(ledger.LimitReached) as exc:
        reserve(led2, "walmart", amount="0.01", step="more")
    assert exc.value.stop is Stop.RETAILER_FUNDS
    reserve(led2, "marianos", amount="2.25", step="its share")  # still there


def test_setup_calls_retries_and_failed_responses_count_like_any_request(make_ledger: Any) -> None:
    led = make_ledger()
    setup = reserve(led, "walmart", step="setup", purpose="setup")
    led.mark_sent(setup)
    led.settle(
        setup,
        billing=ledger.UNKNOWN,
        estimated_usd=None,
        provider_status=401,
        retailer_status=None,
        parser_status=None,
        job_id=None,
        note="STOP_AUTHORIZATION",
    )
    first = reserve(led, "walmart", step="p1", attempt=1)
    led.settle(
        first,
        billing=ledger.NOT_BILLED,
        estimated_usd=Decimal(0),
        provider_status=500,
        retailer_status=None,
        parser_status=None,
        job_id=None,
        note="HTTP 500",
    )
    reserve(led, "walmart", step="p1", attempt=2)
    totals = led.totals()
    assert totals.dispatched_by_retailer == {"walmart": 3}
    # A response documented as not billed keeps its reservation until a charge is read from the account.
    assert totals.committed_usd == Decimal("0.009")
    assert totals.estimated_usd == Decimal(0)


def test_a_restart_continues_the_same_counters_and_finds_unfinished_requests(
    tmp_path: Path, clock: FakeClock
) -> None:
    led = ledger.Ledger.create(tmp_path / "l.sqlite3", "c1", ledger.Limits(), offline=True, clock=clock)
    genesis = led.genesis_id
    for i in range(4):
        seq = reserve(led, "walmart", step=f"w{i}")
        if i < 3:
            led.mark_sent(seq)
    led.close()  # the process ends; two rows were left reserved or sent
    again = ledger.Ledger.open(tmp_path / "l.sqlite3", campaign_id="c1", genesis_id=genesis, clock=clock)
    try:
        assert again.recover() == 4
        assert again.totals().dispatched_total == 4 and again.totals().unknown_billing == 4
        for i in range(6):
            reserve(again, "walmart", step=f"after{i}")
        with pytest.raises(ledger.LimitReached):
            reserve(again, "walmart", step="eleventh")
    finally:
        again.close()


def _workers(
    path: Path, led: ledger.Ledger, retailer: str, n: int, tries: int, *extra: str
) -> list[subprocess.Popen[str]]:
    args = [str(path), led.campaign_id, led.genesis_id, retailer, str(tries), *extra]
    return [
        subprocess.Popen(
            [sys.executable, "-m", "tests.ledger_worker", *args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(n)
    ]


def test_concurrent_invocations_never_pass_the_shared_caps(tmp_path: Path) -> None:
    path = tmp_path / "shared.sqlite3"
    led = ledger.Ledger.create(path, "concurrent", ledger.Limits(), offline=True)
    try:
        procs = _workers(path, led, "walmart", 4, 8) + _workers(path, led, "marianos", 4, 8)
        made = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            assert p.returncode == 0, err
            made.append(int(out.strip()))
        assert sum(made) == 20  # 64 attempts: exactly the caps
        rows = led.rows()
        assert len(rows) == 20 and sum(r["retailer"] == "walmart" for r in rows) == 10
    finally:
        led.close()


def test_a_crash_after_a_reservation_keeps_it_counted(tmp_path: Path) -> None:
    path = tmp_path / "crash.sqlite3"
    led = ledger.Ledger.create(path, "crash", ledger.Limits(), offline=True)
    try:
        for p in _workers(path, led, "walmart", 3, 1, "crash"):
            p.communicate(timeout=60)
            assert p.returncode == 17  # killed right after reserving
        assert led.recover() == 3
        rows = led.rows()
        assert len(rows) == 3 and {r["state"] for r in rows} == {ledger.IN_FLIGHT_UNKNOWN}
        assert led.totals().committed_usd == Decimal("0.009")  # nothing returned to the budget
        procs = _workers(path, led, "walmart", 2, 10)
        made = [int(p.communicate(timeout=60)[0].strip()) for p in procs]
        assert sum(made) == 7  # 3 + 7 = the retailer's 10
    finally:
        led.close()


def test_money_is_exact_and_units_are_never_mixed(make_ledger: Any) -> None:
    with pytest.raises(TypeError):
        money.usd(0.1)  # a float has lost its exactness already
    assert money.usd("0.1") + money.usd("0.2") == Decimal("0.3")
    led = make_ledger()
    a = reserve(led, "walmart", amount="0.0030")
    b = reserve(led, "walmart", amount="0.0030", step="b")
    led.confirm_charge(a, "0.0015", "usd", "dashboard reading (test)")
    led.confirm_charge(b, "2", "credits", "a statement in credits (test)")
    totals = led.totals()
    assert totals.confirmed_usd == Decimal("0.0015")
    assert totals.other_units == {"credits": "2"}  # kept apart, never added to dollars
    assert totals.committed_usd == Decimal("0.0045")  # b's reservation stays: credits are not dollars
    card = money.RateCard.load(
        {
            "confirmed_by": "t",
            "confirmed_at": "t",
            "basis": "t",
            "rates": {"walmart_search": {"unit": "credits", "plain": "1", "rendered": "5"}},
        }
    )
    with pytest.raises(money.UnknownRate):
        card.worst_case("walmart_search", 2)


def test_a_charge_above_the_remaining_funds_is_never_reserved(make_ledger: Any) -> None:
    led = make_ledger(limits=ledger.Limits(total_usd=Decimal("1.00"), billing_headroom_usd=Decimal("0.20")))
    reserve(led, "walmart", amount="0.40")
    with pytest.raises(ledger.LimitReached) as exc:
        reserve(led, "walmart", amount="0.01", step="x")  # the retailer's share of 0.80 is 0.40
    assert exc.value.stop is Stop.RETAILER_FUNDS
    reserve(led, "marianos", amount="0.39")
    with pytest.raises(ledger.LimitReached) as exc:
        reserve(led, "marianos", amount="0.02", step="y")
    assert exc.value.stop in (Stop.RETAILER_FUNDS, Stop.FUNDS)
    assert led.totals().committed_usd == Decimal("0.79")  # never past 0.80, never into the headroom


def test_the_deadline_keeps_time_for_export_and_cleanup(make_ledger: Any, clock: FakeClock) -> None:
    led = make_ledger()
    reserve(led, "walmart", timeout=60)  # starts the campaign's 30 minutes
    clock.advance(30 * 60 - 180 - 30)  # 30 s before the 3 minutes kept for export and cleanup
    with pytest.raises(ledger.LimitReached) as exc:
        reserve(led, "walmart", step="late", timeout=60)  # would still be open when the export must start
    assert exc.value.stop is Stop.DEADLINE
    reserve(led, "walmart", step="short", timeout=20)


def test_history_is_never_deleted_or_rewritten(make_ledger: Any) -> None:
    led = make_ledger()
    seq = reserve(led, "walmart")
    with pytest.raises(sqlite3.DatabaseError):
        led.conn.execute("DELETE FROM dispatch")
    with pytest.raises(sqlite3.DatabaseError):
        led.conn.execute("UPDATE dispatch SET reserved_usd = '0' WHERE seq = ?", (seq,))
    with pytest.raises(sqlite3.DatabaseError):
        led.conn.execute("UPDATE campaign SET started_at = '2030-01-01T00:00:00+00:00'")
    led.stop(Stop.BLOCKED, "first reason")
    led.stop(Stop.FUNDS, "a later reason")
    assert led.stopped() == ("STOP_BLOCKED", "first reason")  # the first stop stays the campaign's reason
    with pytest.raises(ledger.LimitReached):
        reserve(led, "marianos", step="after the stop")


def test_a_disconnected_execution_cannot_grant_itself_a_new_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "campaign.sqlite3"
    led = ledger.Ledger.create(path, "shared", ledger.Limits(), offline=True)
    genesis = led.genesis_id
    ledger.write_manifest(tmp_path / "manifest.json", led)
    led.close()
    with pytest.raises(ledger.LedgerRefused):  # never created by opening
        ledger.Ledger.open(tmp_path / "elsewhere.sqlite3", campaign_id="shared", genesis_id=genesis)
    with pytest.raises(ledger.LedgerRefused):  # another campaign's ledger
        ledger.Ledger.open(path, campaign_id="other", genesis_id=genesis)
    second = ledger.Ledger.create(tmp_path / "second.sqlite3", "shared", ledger.Limits(), offline=True)
    try:
        assert second.genesis_id != genesis
        with pytest.raises(ledger.LedgerRefused):  # a second ledger of the same campaign is not the one named
            ledger.Ledger.open(tmp_path / "second.sqlite3", campaign_id="shared", genesis_id=genesis)
    finally:
        second.close()
    with pytest.raises(ledger.LedgerRefused):  # the file exists: a ledger is never replaced
        ledger.Ledger.create(path, "shared", ledger.Limits(), offline=True)
    monkeypatch.setattr(ledger, "host_id", lambda: "another-host")
    with pytest.raises(ledger.LedgerRefused):  # a copy on another machine would spend the budget twice
        ledger.open_from_manifest(tmp_path / "manifest.json")
    with pytest.raises(ledger.LedgerRefused):
        ledger.Ledger.create(Path("//server/share/ledger.sqlite3"), "x", ledger.Limits(), offline=True)


def test_the_proposed_ceilings_cannot_be_raised() -> None:
    with pytest.raises(ValueError):
        ledger.Limits(per_retailer_requests=11)
    with pytest.raises(ValueError):
        ledger.Limits(total_requests=21)
    with pytest.raises(ValueError):
        ledger.Limits(campaign_minutes=31)
    with pytest.raises(ValueError):
        ledger.Limits(total_usd=Decimal("5.01"))
