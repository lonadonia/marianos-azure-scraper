"""Release 1.9.0: the account-wide spending gate around every Oxylabs submission (the design the Walmart
collector's 1.6.0 ran against the operator's shared trial ledger). SYNTHETIC: the Web API is the in-process
fake of ``test_oxylabs_collector.py`` and the gate a recording fake; nothing reaches Oxylabs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.acquisition import oxylabs
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig
from marianos_headless.db.models import ProviderUsage, Run
from marianos_headless.storage.local import LocalStorageAdapter
from tests.integration.helpers import seed
from tests.integration.test_oxylabs_collector import KEY, FakeOxylabs, _ceiling, _run

pytestmark = [pytest.mark.postgres]


class FakeGate:
    """Refuses once ``cap`` submissions are held or spent; records every call in order."""

    def __init__(
        self, fake: FakeOxylabs, cap: int, *, fail_settle: bool = False, fail_dispatch: bool = False
    ):
        self.fake = fake
        self.cap = cap
        self.fail_settle = fail_settle
        self.fail_dispatch = fail_dispatch
        self.calls: list[tuple[str, str]] = []
        self.state: dict[str, str] = {}
        self.keys: set[str] = set()
        self.sent_before_dispatch: list[int] = []
        self.request_ids: dict[str, str] = {}
        self.reasons: dict[str, str] = {}

    def reserve(
        self, *, purpose: str, endpoint: str, target_url: str, attempt: int, usd: float, key: str
    ) -> str:
        held = sum(1 for v in self.state.values() if v != "unsent")
        if held >= self.cap:
            raise oxylabs.GateRefused(f"account allowance: {held} of {self.cap} submissions held (test)")
        assert usd == 0.0015 and key not in self.keys  # one reservation per row of the collector's ledger
        assert endpoint.startswith("/v1/scrape/marianos") and target_url and attempt >= 1
        self.keys.add(key)
        ref = f"g{len(self.state) + 1}"
        self.state[ref] = "reserved"
        self.calls.append(("reserve", ref))
        return ref

    def dispatched(self, ref: str) -> None:
        assert self.state[ref] == "reserved"
        if self.fail_dispatch:
            raise OSError("the gate cannot record the dispatch (test)")
        self.state[ref] = "dispatched"
        self.calls.append(("dispatched", ref))
        self.sent_before_dispatch.append(len(self.fake.requests))

    def unsent(self, ref: str, reason: str) -> None:
        self.state[ref] = "unsent"
        self.reasons[ref] = reason
        self.calls.append(("unsent", ref))

    def settled(
        self, ref: str, *, status: int, kind: str | None, charged: bool | None, usd: float, request_id: str
    ) -> None:
        assert self.state[ref] == "dispatched"
        if self.fail_settle:
            raise OSError("the gate's disk is full (test)")
        self.state[ref] = "settled" if charged is not None else "unknown"
        self.request_ids[ref] = request_id
        self.calls.append(("settled", ref))

    def unknown(self, ref: str, reason: str) -> None:
        assert self.state[ref] == "dispatched"
        self.state[ref] = "unknown"
        self.reasons[ref] = reason
        self.calls.append(("unknown", ref))


class CutOnce(FakeOxylabs):
    """The fake Web API whose first submission gets no answer (``error`` raised by the transport)."""

    def __init__(self, error: httpx.HTTPError):
        super().__init__()
        self.error = error
        self.cut = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if not self.cut:
            self.cut = True
            raise self.error
        return super().__call__(request)


@pytest.fixture
def env(
    migrated_engine: Engine, tmp_path: Path, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": dev_store,
        "private_label": private_label,
        "tmp": tmp_path,
    }


def _use(monkeypatch: pytest.MonkeyPatch, gate: FakeGate) -> None:
    monkeypatch.setattr(oxylabs.OxylabsClient, "account_gate_factory", lambda: gate)


def _usage(factory: sessionmaker[Session]) -> list[ProviderUsage]:
    with factory() as s:
        return list(s.scalars(select(ProviderUsage).order_by(ProviderUsage.reserved_at)))


def test_every_submission_is_reserved_and_marked_dispatched_at_the_gate_before_it_is_sent(
    env: dict[str, Any], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOxylabs()
    gate = FakeGate(fake, cap=10_000)
    _use(monkeypatch, gate)
    _ceiling(env["factory"], 10)
    _run(env, settings, fake)
    sent = len(fake.requests)
    assert sent == 4 and len(gate.state) == sent == len(_usage(env["factory"]))
    # Each request left after its own reservation and dispatch mark, and before the next one's.
    assert gate.sent_before_dispatch == list(range(sent))
    assert [c for c, _ in gate.calls] == ["reserve", "dispatched", "settled"] * sent
    assert set(gate.state.values()) == {"settled"}
    # The provider's own job IDs reach the gate (its settlement is traceable to the provider).
    assert sorted(gate.request_ids.values()) == [f"req-{n}" for n in range(1, sent + 1)]


def test_a_refusal_of_the_gate_sends_nothing_more_and_stops_the_run_as_a_ceiling(
    env: dict[str, Any], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOxylabs()
    gate = FakeGate(fake, cap=2)
    _use(monkeypatch, gate)
    _ceiling(env["factory"], 10)
    run_id, status = _run(env, settings, fake)
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "SPENDING_CEILING"
        assert "account-wide spending gate" in (run.stop_detail or "")
        assert KEY not in (run.stop_detail or "")
    assert len(fake.requests) == 2 == len(gate.state)  # the third was refused before anything was sent
    rows = _usage(env["factory"])
    refused = [r for r in rows if r.outcome == "gate_refused"]
    assert len(refused) == 1 and refused[0].cost_usd == 0.0 and refused[0].state == "released"


def test_a_gate_that_cannot_mark_the_dispatch_sends_nothing(
    env: dict[str, Any], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOxylabs()
    gate = FakeGate(fake, cap=10_000, fail_dispatch=True)
    _use(monkeypatch, gate)
    _ceiling(env["factory"], 10)
    run_id, status = _run(env, settings, fake)
    assert status == "interrupted" and fake.requests == []
    assert gate.state == {"g1": "unsent"} and "refused at dispatch" in gate.reasons["g1"]
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "SPENDING_CEILING"


def test_a_failure_to_record_an_outcome_keeps_the_answer_and_the_gate_holds_its_reservation(
    env: dict[str, Any], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOxylabs()
    gate = FakeGate(fake, cap=10_000, fail_settle=True)
    _use(monkeypatch, gate)
    _ceiling(env["factory"], 10)
    _, status = _run(env, settings, fake)
    assert status == "rejected"  # the run finished on its answers (incomplete as every search listing is)
    assert len(fake.requests) == 4
    assert set(gate.state.values()) == {"dispatched"}  # held at the gate: never released as free


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("no answer (test)"), httpx.ConnectError("no connection (test)")]
)
def test_a_submission_without_an_answer_is_held_at_the_gate_as_unknown(
    env: dict[str, Any], settings: Settings, monkeypatch: pytest.MonkeyPatch, error: httpx.HTTPError
) -> None:
    fake = CutOnce(error)
    gate = FakeGate(fake, cap=10_000)
    _use(monkeypatch, gate)
    _ceiling(env["factory"], 10)
    _run(env, settings, fake)
    assert fake.cut
    # Sent (or at least marked dispatched) and unanswered: held, never assumed free at the gate. The
    # collector's own ledger keeps the timed-out one as possibly charged and the unconnected one as unsent.
    assert gate.state["g1"] == "unknown" and type(error).__name__ in gate.reasons["g1"]
    assert ("unknown", "g1") in gate.calls
    first = _usage(env["factory"])[0]
    assert first.cost_source == ("rule" if isinstance(error, httpx.ConnectError) else "unknown")
    assert gate.state["g2"] == "settled"  # the retry was reserved and settled on its own
