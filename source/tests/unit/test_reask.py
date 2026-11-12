"""C1 (release 1.10.0): the bounds of a request asked again, without a database (``collection.reask``).

The ceiling of two re-asks and the five-minute wait are not only defaults: a configuration cannot set more
re-asks or a shorter wait, and a record cannot be made to say otherwise."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from marianos_headless.collection import reask
from marianos_headless.collection.config import Limits
from marianos_headless.collection.pagination import Judgement, PageFacts, PageVerdict
from marianos_headless.config_file import LoadedConfig
from marianos_headless.db.models import DeferredRequest

NOW = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)
CONFIG = Path(__file__).resolve().parents[2] / "config" / "collector.yaml"


def _row(**values: object) -> DeferredRequest:
    base: dict[str, object] = {
        "state": reask.WAITING,
        "reasks_dispatched": 0,
        "max_reasks": 2,
        "min_wait_s": 300,
        "not_before": NOW + timedelta(seconds=300),
        "original_reason": "accessible pages exhausted; coverage incomplete: page 2: page 2 repeats an "
        "earlier page exactly",
        "attempts": [],
    }
    return DeferredRequest(**{**base, **values})


def test_no_request_is_asked_again_unless_configured_and_never_more_than_twice() -> None:
    assert Limits().max_reasks_per_request is None and not reask.Policy().enabled
    assert reask.Policy(2, 300).enabled
    for bad in (
        {"max_reasks_per_request": 3},
        {"reask_min_wait_seconds": 299},
        {"max_reasks_per_request": -1},
    ):
        with pytest.raises(ValidationError):
            Limits(**bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="at most twice"):
        reask.Policy(3, 300)
    with pytest.raises(ValueError, match="at least 300"):
        reask.Policy(2, 120)


def test_the_shipped_configuration_asks_again_at_the_clients_pickup_store_only() -> None:
    cfg = LoadedConfig(CONFIG)
    pickup = cfg.collection("marianos-53100502-pickup").limits
    assert (pickup.max_reasks_per_request, pickup.reask_min_wait_seconds) == (2, 300)
    assert cfg.collection("marianos-53100503-instore").limits.max_reasks_per_request is None
    assert not pickup.bounded()  # not a scope limit: the run is not a pilot for it
    assert all(not c.schedule.enabled for c in cfg.collector.collections.values())  # schedules stay off


def test_a_request_waits_its_five_minutes_then_may_be_asked_and_stops_at_its_ceiling() -> None:
    row = _row()
    assert reask.gate(row, NOW) == "wait"
    assert reask.gate(row, NOW + timedelta(seconds=299)) == "wait"
    assert reask.gate(row, NOW + timedelta(seconds=300)) == "ask"
    spent = _row(reasks_dispatched=2, not_before=NOW)
    assert reask.gate(spent, NOW + timedelta(days=1)) == reask.EXHAUSTED  # whatever the time
    assert reask.gate(_row(state=reask.RECOVERED), NOW + timedelta(days=1)) == reask.RECOVERED


def test_a_reask_sent_and_never_answered_stays_counted_and_its_evidence_is_marked_unavailable() -> None:
    lost = {
        "ordinal": 1,
        "role": reask.REASK,
        "requested": {"page": 2},
        "dispatched_at": "x",
        "answered": None,
    }
    row = _row(reasks_dispatched=1, attempts=[{"ordinal": 0, "role": reask.FIRST_ANSWER}, lost])
    assert reask.close_unanswered(row, NOW) is True
    closed = row.attempts[1]
    assert closed["answered"] is False and closed["verdict"] == "unanswered" and closed["counted"] is False
    assert closed["returned"].startswith("unavailable:") and closed["capture"]["sha256"].startswith(
        "unavailable:"
    )
    assert row.reasks_dispatched == 1 and row.state == reask.WAITING  # one re-ask is left
    assert reask.close_unanswered(row, NOW) is False  # closed once
    last = _row(
        reasks_dispatched=2, attempts=[{"ordinal": 0, "role": reask.FIRST_ANSWER}, dict(lost, ordinal=2)]
    )
    assert reask.close_unanswered(last, NOW) is True and last.state == reask.EXHAUSTED


def test_the_final_reason_keeps_the_original_one_and_never_says_the_listing_ended() -> None:
    row = _row(
        reasks_dispatched=2,
        attempts=[
            {"ordinal": 0, "role": reask.FIRST_ANSWER, "verdict": "repeated"},
            {
                "ordinal": 1,
                "role": reask.REASK,
                "verdict": "repeated",
                "detail": "page 2 repeats an earlier page",
            },
            {"ordinal": 2, "role": reask.REASK, "verdict": "failed", "detail": "no page"},
        ],
    )
    text = reask.final_reason(row)
    assert text.startswith(str(row.original_reason))
    assert "asked again 2 time(s)" in text and "re-ask 1: repeated" in text and "re-ask 2: failed" in text
    assert text.endswith(reask.NOT_EXHAUSTED) and "says nothing about where the listing ends" in text


def test_an_answers_record_counts_on_identities_and_says_what_is_unavailable() -> None:
    asked = {"url": "https://www.marianos.com/pl/x/03001?page=2", "page": 2}
    facts = PageFacts(
        2, 2, (2,), "03001", "53100502", "PICKUP", 60, 60, ("a", "b"), (), 2, {"brandName": []}, "s2"
    )
    repeat = Judgement(PageVerdict.REPEATED, "page 2 repeats an earlier page exactly", (), ("a", "b"))
    entry = reask.answer_entry(
        ordinal=1,
        asked=asked,
        facts=facts,
        judgement=repeat,
        verdict="repeated",
        detail=repeat.detail,
        store_check="PASS",
        unique_before=2,
        new=0,
        counted=False,
        observed_at=NOW,
        response_sha256="0" * 64,
        page_fetch_id="f",
        listing_page_id="p",
        listing_page_attempt=2,
        provider_request_id=None,
    )
    # the answer states page 2 and its own search ID: recorded, and nothing is counted from it
    assert entry["returned"]["page"] == 2 and entry["returned"]["search_id"] == "s2"
    assert (entry["new"], entry["overlap"], entry["unique_before"], entry["unique_after"]) == (0, 2, 2, 2)
    assert entry["provider_request_id"].startswith("unavailable:") and entry["role"] == reask.REASK
    nothing = reask.answer_entry(
        ordinal=2,
        asked=asked,
        facts=None,
        judgement=None,
        verdict="failed",
        detail="no page",
        store_check="N/A",
        unique_before=2,
        new=0,
        counted=False,
        observed_at=None,
        response_sha256=None,
        page_fetch_id=None,
        listing_page_id=None,
        listing_page_attempt=None,
        provider_request_id=None,
    )
    assert nothing["returned"] == "unavailable: no page was brought" and nothing["answered"] is False
    assert all(str(v).startswith("unavailable:") for v in nothing["capture"].values())
