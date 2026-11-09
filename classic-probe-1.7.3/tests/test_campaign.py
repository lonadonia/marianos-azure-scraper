"""The Walmart steps against SYNTHETIC Classic responses (OFFLINE REPLAY): what is sent, what the ledger
keeps, and which response stops the campaign before anything more is sent."""

from __future__ import annotations

import gzip
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from classic_probe import campaign, cli, ledger, money
from classic_probe.stops import Stop
from classic_probe.targets import Target
from classic_probe.transport import ProviderRequest, ProviderResponse, ReplayTransport
from tests import fixture_builder as fb
from tests.conftest import SYNTHETIC_RATES, FakeClock

WALMART = Target(
    retailer="walmart",
    store_id="3891",
    store_address="3900 Fountain Square Pl, Waukegan, IL 60085",
    fulfillment="PICKUP",
    store_id_verified=True,
    store_id_evidence="test",
    adapter="walmart",
    search_query="milk",
    category_probe_url="https://www.walmart.com/browse/food/fresh-fruits/976759_976793_9756351",
)
MARIANOS = Target("marianos", "", "1720 N Milwaukee Ave, Vernon Hills, IL 60061", "PICKUP", False, "", "none")


def run(
    make_ledger: Any,
    tmp_path: Path,
    card: money.RateCard,
    steps: dict[str, list[tuple[int, bytes]]],
    **kw: Any,
) -> tuple[campaign.CampaignResult, ReplayTransport, ledger.Ledger]:
    led = make_ledger()
    tr = ReplayTransport({k: [ProviderResponse(s, b) for s, b in v] for k, v in steps.items()})
    result = campaign.Campaign(led, tr, kw.pop("target", WALMART), card, out_dir=tmp_path / "out", **kw).run()
    return result, tr, led


def sent(tr: ReplayTransport) -> list[str]:
    return [r.step for r in tr.dispatched]


def test_a_complete_answer_takes_four_requests_each_reserved_first(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    result, tr, led = run(make_ledger, tmp_path, card, fb.complete())
    assert result.stop is None, result.detail
    assert sent(tr) == ["walmart-search-p1", "walmart-search-p2", "walmart-product", "walmart-category-url"]
    rows = led.rows()
    assert [r["step"] for r in rows] == sent(tr)
    assert {r["state"] for r in rows} == {ledger.ANSWERED}
    # Upper bounds reserved at the rendered rate for every result type asked for (raw and parsed: 2).
    assert [r["reserved_usd"] for r in rows] == ["0.0040", "0.0040", "0.0040", "0.0015"]
    assert led.totals().committed_usd == Decimal("0.0135")
    assert tr.dispatched[0].url == "https://realtime.oxylabs.io/v1/queries?type=raw,parsed"
    assert tr.dispatched[1].payload["start_page"] == 2
    assert tr.dispatched[2].payload == {
        "source": "walmart_product",
        "product_id": "7101",
        "store_id": "3891",
        "fulfillment_type": "pickup",
        "parse": True,
    }
    p1 = result.steps[0]["attempts"][0]["facts"]
    assert p1["page_store"] == "3891" and p1["page_intent"] == "PICKUP" and p1["parsed_store"] == "3891"
    assert p1["walmart_seller"] == 2 and p1["sponsored"] == 1
    product = result.steps[2]["attempts"][0]["facts"]
    assert product["page_item"] == "7101" and product["upc"] == "012345678905" == product["parsed_gtin"]
    evidence = json.loads((tmp_path / "out" / "campaign_evidence.json").read_text("utf-8"))
    assert (
        evidence["offline"] is True and len(evidence["dispatches"]) == 4 and len(evidence["responses"]) == 4
    )


@pytest.mark.parametrize(
    ("name", "steps", "stop", "dispatched"),
    [
        (
            "blocked",
            {"walmart-search-p1": [(200, fb.envelope(fb.CHALLENGE_HTML, fb.parsed_search(fb.PAGE1)))]},
            Stop.BLOCKED,
            1,
        ),
        (
            "retailer_refused",
            {
                "walmart-search-p1": [
                    (200, fb.envelope(fb.search_html(fb.PAGE1), fb.parsed_search(fb.PAGE1), status_code=403))
                ]
            },
            Stop.BLOCKED,
            1,
        ),
        (
            "wrong_store",
            {
                "walmart-search-p1": [
                    (
                        200,
                        fb.envelope(
                            fb.search_html(fb.PAGE1, store=fb.OTHER_STORE),
                            fb.parsed_search(fb.PAGE1, store=fb.OTHER_STORE),
                        ),
                    )
                ]
            },
            Stop.WRONG_CONTEXT,
            1,
        ),
        (
            "wrong_fulfillment",
            {
                "walmart-search-p1": [
                    (
                        200,
                        fb.envelope(fb.search_html(fb.PAGE1, intent="SHIPPING"), fb.parsed_search(fb.PAGE1)),
                    )
                ]
            },
            Stop.WRONG_CONTEXT,
            1,
        ),
        (
            "parsed_disagrees",
            {
                "walmart-search-p1": [
                    (200, fb.envelope(fb.search_html(fb.PAGE1), fb.parsed_search(fb.PAGE1, store="1314")))
                ]
            },
            Stop.WRONG_CONTEXT,
            1,
        ),
        (
            "no_raw",
            {"walmart-search-p1": [(200, fb.envelope(None, fb.parsed_search(fb.PAGE1)))]},
            Stop.UNVERIFIED_CONTEXT,
            1,
        ),
        (
            "parser_failed",
            {
                "walmart-search-p1": [
                    (200, fb.envelope(fb.search_html(fb.PAGE1), fb.parsed_search(fb.PAGE1, code=12002)))
                ]
            },
            Stop.PARSER_FAILED,
            1,
        ),
        (
            "malformed",
            {"walmart-search-p1": [(200, b"<html>not the documented JSON</html>")]},
            Stop.UNSUPPORTED_RESPONSE,
            1,
        ),
        ("no_results", {"walmart-search-p1": [(200, b'{"results": []}')]}, Stop.UNSUPPORTED_RESPONSE, 1),
        (
            "unauthorized",
            {"walmart-search-p1": [(401, b'{"message": "Client not found"}')]},
            Stop.AUTHORIZATION,
            1,
        ),
        ("no_entitlement", {"walmart-search-p1": [(403, b'{"message": "Forbidden"}')]}, Stop.ENTITLEMENT, 1),
        ("bad_request", {"walmart-search-p1": [(400, b'{"message": "invalid"}')]}, Stop.BAD_REQUEST, 1),
        (
            "repeated_page",
            {
                **fb.complete(),
                "walmart-search-p2": [
                    (200, fb.envelope(fb.search_html(fb.PAGE1), fb.parsed_search(fb.PAGE1)))
                ],
            },
            Stop.REPEATED_PAGE,
            2,
        ),
        (
            "page_2_with_page_1s_products",
            {
                **fb.complete(),
                "walmart-search-p2": [
                    (200, fb.envelope(fb.search_html(fb.PAGE1, page=2), fb.parsed_search(fb.PAGE1, page=2)))
                ],
            },
            Stop.REPEATED_PAGE,
            2,
        ),
        (
            "empty_page_2",
            {
                **fb.complete(),
                "walmart-search-p2": [
                    (200, fb.envelope(fb.search_html([], page=2), fb.parsed_search([], page=2)))
                ],
            },
            Stop.EMPTY_RESPONSE,
            2,
        ),
        (
            "wrong_product",
            {
                **fb.complete(),
                "walmart-product": [
                    (200, fb.envelope(fb.product_html("7101", page_item="9999"), fb.parsed_product("9999")))
                ],
            },
            Stop.WRONG_IDENTITY,
            3,
        ),
        (
            "product_for_other_store",
            {
                **fb.complete(),
                "walmart-product": [
                    (
                        200,
                        fb.envelope(
                            fb.product_html("7101", store=fb.OTHER_STORE),
                            fb.parsed_product("7101", store=fb.OTHER_STORE),
                        ),
                    )
                ],
            },
            Stop.WRONG_CONTEXT,
            3,
        ),
        (
            "category_page_for_a_random_store",
            {
                **fb.complete(),
                "walmart-category-url": [
                    (200, fb.envelope(fb.search_html(fb.PAGE1, store=fb.OTHER_STORE), None))
                ],
            },
            Stop.WRONG_CONTEXT,
            4,
        ),
    ],
)
def test_a_response_that_fails_its_check_stops_the_campaign_with_nothing_more_sent(
    make_ledger: Any,
    tmp_path: Path,
    card: money.RateCard,
    name: str,
    steps: dict[str, Any],
    stop: Stop,
    dispatched: int,
) -> None:
    result, tr, led = run(make_ledger, tmp_path, card, steps)
    assert result.stop == stop.value, (name, result.detail)
    assert len(tr.dispatched) == dispatched
    assert len(led.rows()) == dispatched  # every dispatch, the failed one included, is in the ledger
    assert led.stopped() is not None and led.stopped()[0] == stop.value
    with pytest.raises(ledger.LimitReached):  # and nothing more can be reserved by anyone
        led.reserve(
            retailer="marianos",
            step="x",
            purpose="x",
            request_class="walmart_search",
            attempt=1,
            payload_sha256="0" * 64,
            amount_usd=Decimal("0.001"),
            request_timeout_s=10,
        )
    assert (tmp_path / "out" / "campaign_evidence.json").is_file()  # the stop is exported


def test_a_documented_temporary_error_is_retried_once_and_the_retry_is_a_new_dispatch(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    steps = fb.complete()
    steps["walmart-search-p1"] = [(500, b'{"message": "Internal Server Error"}'), *steps["walmart-search-p1"]]
    waits: list[float] = []
    result, tr, led = run(make_ledger, tmp_path, card, steps, sleep=waits.append)
    assert result.stop is None
    assert sent(tr)[:2] == ["walmart-search-p1", "walmart-search-p1"] and len(tr.dispatched) == 5
    rows = led.rows()
    assert [(r["step"], r["attempt"], r["provider_status"]) for r in rows[:2]] == [
        ("walmart-search-p1", 1, 500),
        ("walmart-search-p1", 2, 200),
    ]
    assert rows[0]["billing"] == ledger.NOT_BILLED and rows[0]["reserved_usd"] == "0.0040"  # still reserved
    assert waits == [5.0]


def test_a_temporary_error_that_does_not_clear_stops_after_the_last_attempt(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    steps = {"walmart-search-p1": [(429, b"{}"), (429, b"{}"), (200, b"{}")]}
    result, tr, led = run(make_ledger, tmp_path, card, steps)
    assert result.stop == Stop.RETRIES_EXHAUSTED.value and len(tr.dispatched) == 2 == len(led.rows())


def test_a_retry_that_would_end_after_the_deadline_is_not_sent(
    make_ledger: Any, tmp_path: Path, card: money.RateCard, clock: FakeClock
) -> None:
    steps = {"walmart-search-p1": [(500, b"{}"), (200, b"{}")]}

    class LateTransport(ReplayTransport):
        def send(self, request: ProviderRequest, timeout_s: float) -> ProviderResponse:
            clock.advance(30 * 60 - 180 - 3)  # the first answer comes 3 s before the time kept for export
            return super().send(request, timeout_s)

    led = make_ledger()
    tr = LateTransport({k: [ProviderResponse(s, b) for s, b in v] for k, v in steps.items()})
    result = campaign.Campaign(led, tr, WALMART, card, out_dir=tmp_path / "out").run()
    assert result.stop == Stop.DEADLINE.value and len(tr.dispatched) == 1


def test_a_request_still_open_at_its_deadline_keeps_its_reservation_and_its_outcome_stays_unknown(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    # 1.7.0 (C2): the request goes through the isolated worker to a loopback stub that never answers, and
    # the worker is killed at the request's deadline. An in-process transport is no longer bounded by a
    # thread: only a process that can be killed is.
    from classic_probe import gates
    from classic_probe.transport import IsolatedHttpTransport
    from tests import loopback_stub

    led = make_ledger()
    with loopback_stub.Stub(loopback_stub.hang) as stub:
        tr = IsolatedHttpTransport(
            gates.Credentials("loopback-user", "loopback-password"),
            work_dir=tmp_path / "work",
            loopback_port=stub.port,
        )
        started = time.monotonic()
        result = campaign.Campaign(
            led, tr, WALMART, card, out_dir=tmp_path / "out", request_timeout_s=0.3
        ).run()
        assert time.monotonic() - started < 1.9  # the wait was bounded, not the request's own time
    assert result.stop == Stop.IN_FLIGHT_UNKNOWN.value
    [row] = led.rows()
    assert row["state"] == ledger.IN_FLIGHT_UNKNOWN and row["billing"] == ledger.UNKNOWN
    assert row["reserved_usd"] == "0.0040" and led.totals().unknown_billing == 1
    assert "may have reached the provider" in result.steps[0]["attempts"][0]["outcome"]
    assert (tmp_path / "out" / "campaign_evidence.json").is_file()


def test_an_export_or_cleanup_error_sends_nothing_keeps_the_history_and_the_first_reason(
    make_ledger: Any, tmp_path: Path, card: money.RateCard, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_a: Any, **_k: Any) -> None:
        raise OSError("disk full (test)")

    monkeypatch.setattr(campaign, "write_json", broken)
    steps = {"walmart-search-p1": [(200, fb.envelope(fb.CHALLENGE_HTML, fb.parsed_search(fb.PAGE1)))]}
    led = make_ledger()
    tr = ReplayTransport({k: [ProviderResponse(s, b) for s, b in v] for k, v in steps.items()})
    run_ = campaign.Campaign(led, tr, WALMART, card, out_dir=tmp_path / "out")
    result = run_.run()
    assert result.stop == Stop.BLOCKED.value  # the primary failure is not replaced by the export's
    assert result.export_errors == ["OSError: disk full (test)"]
    assert len(tr.dispatched) == 1 and len(led.rows()) == 1
    with monkeypatch.context() as m:  # undone before the fixture closes the ledger for real
        m.setattr(led, "close", broken)
        run_.close()
    assert result.cleanup_errors == ["OSError: disk full (test)"]
    assert len(tr.dispatched) == 1 and result.stop == Stop.BLOCKED.value
    assert led.stopped() == (Stop.BLOCKED.value, result.detail)


def test_kept_evidence_has_no_session_identifier_token_or_cookie(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    steps = fb.complete()
    page = fb.search_html(fb.PAGE1).replace(
        '"query": {', '"isomorphicSessionId": "sess-SECRET-1", "traceId": "trace-SECRET-2", "query": {'
    )
    page = page.replace("</body>", '<script>window.__t = "tok-SECRET-3";</script></body>')
    assert page.count("SECRET") == 3
    responses = {k: [ProviderResponse(s, b) for s, b in v] for k, v in steps.items()}
    responses["walmart-search-p1"] = [
        ProviderResponse(
            200,
            fb.envelope(page, fb.parsed_search(fb.PAGE1)),
            {"Set-Cookie": "sid=cookie-SECRET-4", "x-ratelimit-requests-remaining": "9"},
        )
    ]
    led = make_ledger()
    result = campaign.Campaign(led, ReplayTransport(responses), WALMART, card, out_dir=tmp_path / "out").run()
    assert result.stop is None, (
        result.detail
    )  # the checks read the page as served; only the kept copy is cleaned
    out = tmp_path / "out"
    kept = [gzip.decompress(p.read_bytes()).decode("utf-8") for p in sorted(out.glob("response_*.json.gz"))]
    evidence = (out / "campaign_evidence.json").read_text("utf-8")
    assert len(kept) == 4 and all("SECRET" not in k for k in [*kept, evidence])
    assert "[REDACTED]" in kept[0] and "3891" in kept[0]  # the store and products stay
    first = json.loads(evidence)["responses"][0]
    assert first["sanitized"] is True and first["raw_pages"][0]["page_data_values_redacted"] == 2
    assert first["headers"] == {"Set-Cookie": "[REMOVED]", "x-ratelimit-requests-remaining": "9"}


def test_the_marianos_target_plans_nothing_and_keeps_its_share(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    assert MARIANOS.live_problems() == [
        "marianos: this probe has no adapter for it (its share of the limits stays reserved)",
        "marianos: the retailer's store ID is not verified from the source",
    ]
    with pytest.raises(ValueError):
        campaign.Campaign(make_ledger(), ReplayTransport({}), MARIANOS, card, out_dir=tmp_path)


def test_an_unknown_rate_prevents_the_first_dispatch(make_ledger: Any, tmp_path: Path) -> None:
    rates = {**SYNTHETIC_RATES, "rates": {"walmart_product": SYNTHETIC_RATES["rates"]["walmart_product"]}}
    result, tr, led = run(make_ledger, tmp_path, money.RateCard.load(rates), fb.complete())
    assert result.stop == Stop.FUNDS.value and "no reliable upper bound" in result.detail
    assert tr.dispatched == [] and led.rows() == []


def test_the_replay_command_runs_the_steps_from_saved_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    spec: dict[str, Any] = {"steps": {}}
    for step, answers in fb.complete().items():
        spec["steps"][step] = []
        for i, (status, body) in enumerate(answers):
            (fixtures / f"{step}-{i}.json").write_bytes(body)
            spec["steps"][step].append({"http_status": status, "body_file": f"{step}-{i}.json"})
    (fixtures / "replay.json").write_text(json.dumps(spec), "utf-8")
    rates = tmp_path / "rates.json"
    rates.write_text(json.dumps(SYNTHETIC_RATES), "utf-8")
    targets = Path(__file__).resolve().parents[1] / "config" / "targets.json"
    code = cli.main(
        [
            "replay",
            "--targets",
            str(targets),
            "--fixtures",
            str(fixtures),
            "--rates",
            str(rates),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    body = json.loads(capsys.readouterr().out)
    assert code == 0 and body["OFFLINE REPLAY"] is True and body["dispatched"] == 4 and body["stop"] is None


# -- 1.7.0 (the client's second review: C3, C4, C5) -------------------------------------------------------


def replay(steps: dict[str, list[tuple[int, bytes]]]) -> ReplayTransport:
    return ReplayTransport({k: [ProviderResponse(s, b) for s, b in v] for k, v in steps.items()})


def test_a_backoff_is_a_real_wait_by_default(make_ledger: Any, tmp_path: Path, card: money.RateCard) -> None:
    run_ = campaign.Campaign(make_ledger(), ReplayTransport({}), WALMART, card, out_dir=tmp_path / "out")
    assert run_.sleep is time.sleep  # no silent no-op: an injected sleep is a test's own choice
    steps = fb.complete()
    steps["walmart-search-p1"] = [(429, b"{}"), *steps["walmart-search-p1"]]
    t0 = time.monotonic()
    result = campaign.Campaign(
        make_ledger("real.sqlite3"), replay(steps), WALMART, card, out_dir=tmp_path / "o2"
    ).run()
    assert result.stop is None and time.monotonic() - t0 >= 1.9  # the documented 2 s for HTTP 429


def test_retry_after_is_honoured_and_a_longer_wait_ends_the_step(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    steps = fb.complete()
    waits: list[float] = []
    responses = {k: [ProviderResponse(s, b) for s, b in v] for k, v in steps.items()}
    responses["walmart-search-p1"].insert(0, ProviderResponse(429, b"{}", {"Retry-After": "7"}))
    result = campaign.Campaign(
        make_ledger(), ReplayTransport(responses), WALMART, card, out_dir=tmp_path / "a", sleep=waits.append
    ).run()
    assert result.stop is None and waits == [7.0]  # more than the documented 2 s, as the provider asked
    status, body = steps["walmart-search-p1"][0]
    tr = ReplayTransport(
        {
            "walmart-search-p1": [
                ProviderResponse(429, b"{}", {"Retry-After": "600"}),
                ProviderResponse(status, body),
            ]
        }
    )
    result = campaign.Campaign(
        make_ledger("long.sqlite3"), tr, WALMART, card, out_dir=tmp_path / "b", sleep=waits.append
    ).run()
    assert result.stop == Stop.RETRIES_EXHAUSTED.value and "600 s" in result.detail
    assert len(tr.dispatched) == 1 and waits == [7.0]  # nothing waited, nothing more sent


def test_retry_after_past_the_deadline_is_not_waited_for(
    make_ledger: Any, tmp_path: Path, card: money.RateCard, clock: FakeClock
) -> None:
    class Late(ReplayTransport):
        def send(self, request: ProviderRequest, timeout_s: float) -> ProviderResponse:
            clock.advance(30 * 60 - 180 - 40)  # 40 s before the reserve when the answer comes
            return super().send(request, timeout_s)

    waits: list[float] = []
    tr = Late({"walmart-search-p1": [ProviderResponse(429, b"{}", {"Retry-After": "45"})]})
    result = campaign.Campaign(
        make_ledger(), tr, WALMART, card, out_dir=tmp_path / "out", sleep=waits.append
    ).run()
    assert result.stop == Stop.DEADLINE.value and waits == [] and len(tr.dispatched) == 1


def test_each_answer_is_kept_and_indexed_before_the_next_paid_step(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    led = make_ledger()
    out = tmp_path / "out"
    seen: list[tuple[str, list[int], list[str]]] = []

    class Watching(ReplayTransport):
        def send(self, request: ProviderRequest, timeout_s: float) -> ProviderResponse:
            files = sorted(p.name for p in out.glob("*.json.gz"))
            seen.append((request.step, [c["seq"] for c in led.captures()], files))
            return super().send(request, timeout_s)

    steps = fb.complete()
    tr = Watching({k: [ProviderResponse(s, b) for s, b in v] for k, v in steps.items()})
    result = campaign.Campaign(led, tr, WALMART, card, out_dir=out).run()
    assert result.stop is None
    assert [(step, idx) for step, idx, _ in seen] == [
        ("walmart-search-p1", []),
        ("walmart-search-p2", [1]),
        ("walmart-product", [1, 2]),
        ("walmart-category-url", [1, 2, 3]),
    ]
    assert seen[-1][2] == ["response_001.json.gz", "response_002.json.gz", "response_003.json.gz"]
    evidence = json.loads((out / "campaign_evidence.json").read_text("utf-8"))
    assert evidence["complete"] is True and [r["verified"] for r in evidence["responses"]] == [True] * 4
    assert all(len(r["original_sha256"]) == 64 and len(r["kept_sha256"]) == 64 for r in evidence["responses"])


def test_an_answer_that_cannot_be_kept_stops_the_campaign_before_another_request(
    make_ledger: Any, tmp_path: Path, card: money.RateCard, monkeypatch: pytest.MonkeyPatch
) -> None:
    from classic_probe import captures

    def full(*_a: Any, **_k: Any) -> None:
        raise OSError("disk full (test)")

    monkeypatch.setattr(captures, "atomic_write", full)
    led = make_ledger()
    tr = replay(fb.complete())
    result = campaign.Campaign(led, tr, WALMART, card, out_dir=tmp_path / "out").run()
    assert result.stop == Stop.EVIDENCE.value and len(tr.dispatched) == 1
    [row] = led.rows()
    assert row["state"] == ledger.ANSWERED and row["reserved_usd"] == "0.0040" and led.captures() == []


def test_the_export_says_when_a_capture_was_not_checked_in_time(
    make_ledger: Any, tmp_path: Path, card: money.RateCard, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    led = make_ledger()
    run_ = campaign.Campaign(led, replay(fb.complete()), WALMART, card, out_dir=tmp_path / "out")
    real_export = run_._export

    def late_export() -> None:
        clock.advance(30 * 60 - 2)  # the export starts 2 s before the session ends
        real_export()

    monkeypatch.setattr(run_, "_export", late_export)
    result = run_.run()
    evidence = json.loads((tmp_path / "out" / "campaign_evidence.json").read_text("utf-8"))
    assert result.stop is None and evidence["complete"] is False
    assert {r["verified"] for r in evidence["responses"]} == {None}  # unverified, never "good"
    assert len(evidence["dispatches"]) == 4  # the manifest is still written, from the durable index


def test_a_refused_target_is_never_marked_sent(
    make_ledger: Any, tmp_path: Path, card: money.RateCard
) -> None:
    from classic_probe.transport import TransportFailed

    class Refusing(ReplayTransport):
        def preflight(self, request: ProviderRequest) -> None:
            raise TransportFailed("refused: not the documented endpoint (test)", sent=False)

    led = make_ledger()
    tr = Refusing({k: [ProviderResponse(s, b) for s, b in v] for k, v in fb.complete().items()})
    result = campaign.Campaign(led, tr, WALMART, card, out_dir=tmp_path / "out").run()
    assert result.stop == Stop.OPERATOR.value and tr.dispatched == []
    [row] = led.rows()
    assert row["state"] == ledger.NOT_SENT and led.totals().committed_usd == Decimal(0)
