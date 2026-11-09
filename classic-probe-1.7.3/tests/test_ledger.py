"""The shared campaign limits (OFFLINE, isolated ledgers in temporary folders; never a production budget)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
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


# -- 1.7.0 (the client's second review, finding C3 and the capture index of C4) ---------------------------


def test_the_time_is_read_only_while_the_write_lock_is_held(tmp_path: Path, clock: FakeClock) -> None:
    reads: list[bool] = []
    holder: dict[str, ledger.Ledger] = {}

    def watched() -> Any:
        led_ = holder.get("led")
        reads.append(bool(led_ and led_.conn.in_transaction))
        return clock()

    led = ledger.Ledger.create(tmp_path / "t.sqlite3", "c", ledger.Limits(), offline=True, clock=watched)
    holder["led"] = led
    try:
        reads.clear()
        reserve(led, "walmart")
        assert reads and all(reads)  # every reading of the time by reserve() was under the lock
    finally:
        led.close()


def test_a_reservation_that_waited_for_the_lock_is_checked_against_the_time_left_when_it_gets_it(
    tmp_path: Path, clock: FakeClock
) -> None:
    import threading

    path = tmp_path / "wait.sqlite3"
    led = ledger.Ledger.create(path, "c", ledger.Limits(), offline=True, clock=clock)
    try:
        reserve(led, "walmart", timeout=60)  # starts the campaign
        other = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
        locked = threading.Event()

        def hold() -> None:
            other.execute("BEGIN IMMEDIATE")
            locked.set()
            time.sleep(0.6)
            clock.advance(30 * 60 - 180 - 30)  # while the lock is held, the time runs out
            other.execute("COMMIT")

        t = threading.Thread(target=hold)
        t.start()
        assert locked.wait(5)
        with pytest.raises(ledger.LimitReached) as exc:
            led.reserve(
                retailer="walmart",
                step="waited",
                purpose="t",
                request_class="walmart_search",
                attempt=1,
                payload_sha256="0" * 64,
                amount_usd=money.usd("0.003"),
                request_timeout_s=60.0,
                lock_wait_s=5.0,
            )
        t.join()
        other.close()
        assert exc.value.stop is Stop.DEADLINE and len(led.rows()) == 1  # a time read before the lock is gone
    finally:
        led.close()


def test_the_wait_for_the_lock_is_bounded_and_reserves_nothing(tmp_path: Path) -> None:
    path = tmp_path / "busy.sqlite3"
    led = ledger.Ledger.create(path, "c", ledger.Limits(), offline=True)
    other = sqlite3.connect(path, timeout=5, isolation_level=None)
    try:
        other.execute("BEGIN IMMEDIATE")
        t0 = time.monotonic()
        with pytest.raises(ledger.LimitReached) as exc:
            led.reserve(
                retailer="walmart",
                step="s",
                purpose="t",
                request_class="walmart_search",
                attempt=1,
                payload_sha256="0" * 64,
                amount_usd=money.usd("0.003"),
                request_timeout_s=60.0,
                lock_wait_s=0.4,
            )
        assert time.monotonic() - t0 < 3.0  # not the connection's 30 s
        assert exc.value.stop is Stop.DEADLINE and "nothing was reserved" in exc.value.detail
        other.execute("COMMIT")
        assert led.rows() == []
    finally:
        other.close()
        led.close()


def test_the_last_check_before_sending_refuses_a_late_request_and_records_it_as_never_sent(
    make_ledger: Any, clock: FakeClock
) -> None:
    led = make_ledger()
    early = reserve(led, "walmart", timeout=60)
    led.mark_sent(early, allowance_s=60)
    late = reserve(led, "walmart", step="late", timeout=60)
    clock.advance(30 * 60 - 180 - 30)  # the time between reserving and sending ran out
    with pytest.raises(ledger.LimitReached) as exc:
        led.mark_sent(late, allowance_s=60)
    assert exc.value.stop is Stop.DEADLINE
    rows = {r["seq"]: r for r in led.rows()}
    assert rows[late]["state"] == ledger.NOT_SENT and rows[early]["state"] == ledger.SENT
    totals = led.totals()
    assert totals.not_sent == 1 and totals.dispatched_total == 1
    assert totals.committed_usd == Decimal("0.003")  # the request never sent holds no money
    with pytest.raises(sqlite3.DatabaseError):  # and it can never be sent afterwards
        led.conn.execute("UPDATE dispatch SET state = 'sent' WHERE seq = ?", (late,))
    with pytest.raises(sqlite3.DatabaseError):  # only a reservation never handed over can become not sent
        led.conn.execute("UPDATE dispatch SET state = 'not_sent' WHERE seq = ?", (early,))
    with pytest.raises(ledger.LedgerRefused):
        led.mark_sent(late, allowance_s=1)


def test_a_stop_recorded_by_another_invocation_is_seen_at_the_last_check(make_ledger: Any) -> None:
    led = make_ledger()
    seq = reserve(led, "walmart")
    led.stop(Stop.BLOCKED, "the other invocation saw a challenge")
    with pytest.raises(ledger.LimitReached) as exc:
        led.mark_sent(seq, allowance_s=10)
    assert exc.value.stop is Stop.BLOCKED and led.rows()[0]["state"] == ledger.NOT_SENT


def test_requests_never_sent_do_not_use_the_quotas(make_ledger: Any) -> None:
    led = make_ledger()
    for i in range(3):
        led.release_unsent(reserve(led, "walmart", step=f"refused{i}"), "refused before sending (test)")
    for i in range(10):
        reserve(led, "walmart", step=f"w{i}")
    with pytest.raises(ledger.LimitReached):
        reserve(led, "walmart", step="w10")
    assert led.totals().dispatched_by_retailer == {"walmart": 10} and led.totals().not_sent == 3


def test_a_capture_index_row_is_never_changed_or_deleted(make_ledger: Any) -> None:
    led = make_ledger()
    seq = reserve(led, "walmart")
    record = {
        "file": "response_001.json.gz",
        "http_status": 200,
        "body_bytes": 10,
        "truncated": False,
        "original_sha256": "a" * 64,
        "kept_sha256": "b" * 64,
        "sanitized": True,
        "detail": {"step": "s"},
    }
    led.record_capture(seq, record)
    assert led.captures()[0]["kept_sha256"] == "b" * 64
    with pytest.raises(sqlite3.DatabaseError):
        led.conn.execute("UPDATE capture SET kept_sha256 = 'c' WHERE seq = ?", (seq,))
    with pytest.raises(sqlite3.DatabaseError):
        led.conn.execute("DELETE FROM capture")
    with pytest.raises(sqlite3.IntegrityError):
        led.record_capture(seq, record)  # one capture per dispatch


def test_a_ledger_of_the_earlier_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    led = ledger.Ledger.create(path, "c", ledger.Limits(), offline=True)
    genesis = led.genesis_id
    led.conn.execute("DROP TRIGGER meta_never_deleted")
    led.conn.execute("DELETE FROM meta")  # as a 1.6.0 ledger: no schema version
    led.close()
    with pytest.raises(ledger.LedgerRefused) as exc:
        ledger.Ledger.open(path, campaign_id="c", genesis_id=genesis)
    assert "earlier schema" in str(exc.value)
