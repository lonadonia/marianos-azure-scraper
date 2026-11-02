"""Shared pieces of the OFFLINE tests. Every test runs with the network closed (a connection attempt fails the
test) and without any Classic credential in its environment."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from classic_probe import ledger, money

SYNTHETIC_RATES: dict[str, Any] = {
    "synthetic": True,
    "confirmed_by": "SYNTHETIC test rate card",
    "confirmed_at": "2026-10-31",
    "basis": "SYNTHETIC: invented for the offline tests; not this or any account's rates",
    "rates": {
        "walmart_search": {"unit": "usd_per_result", "plain": "0.0015", "rendered": "0.0020"},
        "walmart_product": {"unit": "usd_per_result", "plain": "0.0015", "rendered": "0.0020"},
        "url_only": {"unit": "usd_per_result", "plain": "0.0010", "rendered": "0.0015"},
    },
}


class NetworkUsed(AssertionError):
    pass


@pytest.fixture(autouse=True)
def closed_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    attempts: list[str] = []

    def refuse(*args: Any, **kwargs: Any) -> Any:
        attempts.append(repr(args)[:200])
        raise NetworkUsed(f"an offline test tried to use the network: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    for name in ("OXYLABS_CLASSIC_USERNAME", "OXYLABS_CLASSIC_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    yield attempts
    assert attempts == [], attempts


class FakeClock:
    def __init__(self, start: datetime = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def card() -> money.RateCard:
    return money.RateCard.load(SYNTHETIC_RATES)


@pytest.fixture
def make_ledger(tmp_path: Path, clock: FakeClock) -> Iterator[Any]:
    made: list[ledger.Ledger] = []

    def make(name: str = "ledger.sqlite3", limits: ledger.Limits | None = None) -> ledger.Ledger:
        led = ledger.Ledger.create(
            tmp_path / name, "test-campaign", limits or ledger.Limits(), offline=True, clock=clock
        )
        made.append(led)
        return led

    yield make
    for led in made:
        led.close()


def reserve(
    led: ledger.Ledger, retailer: str = "walmart", amount: str = "0.003", step: str = "s", **kw: Any
) -> int:
    return led.reserve(
        retailer=retailer,
        step=step,
        purpose=kw.get("purpose", "test"),
        request_class="walmart_search",
        attempt=kw.get("attempt", 1),
        payload_sha256="0" * 64,
        amount_usd=money.usd(amount),
        request_timeout_s=kw.get("timeout", 60.0),
    )
