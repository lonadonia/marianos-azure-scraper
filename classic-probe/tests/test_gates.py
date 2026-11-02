"""Nothing is dispatched without approval, entitlement, confirmed rates and credentials, and this build
dispatches nothing at all (OFFLINE)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from classic_probe import cli, gates, ledger, transport
from tests.conftest import SYNTHETIC_RATES

APPROVAL = {"approved": True, "approved_by": "the account owner", "retailers": ["walmart", "marianos"]}
ENTITLEMENT = {
    "verified": True,
    "verified_by": "the account owner",
    "targets": ["walmart_search", "walmart_product"],
    "response_mode": "realtime",
}
CONFIRMED_RATES = {**SYNTHETIC_RATES, "synthetic": False, "confirmed_by": "the account owner (test)"}


def _evaluate(led: ledger.Ledger, **kw: Any) -> list[str]:
    args: dict[str, Any] = {
        "approval": {**APPROVAL, "campaign_id": led.campaign_id, "ledger_genesis_id": led.genesis_id},
        "entitlement": ENTITLEMENT,
        "rates": CONFIRMED_RATES,
        "credentials": True,
        "retailer": "walmart",
    }
    args.update(kw)
    return gates.evaluate(led, **args)


def test_each_missing_condition_prevents_dispatch_and_is_named(tmp_path: Path) -> None:
    online = ledger.Ledger.create(tmp_path / "l.sqlite3", "c", ledger.Limits(), offline=False)
    try:
        assert _evaluate(online) == []  # all conditions met: only LIVE_ENABLED still refuses (below)
        assert _evaluate(online, approval=None) == ["no explicit approval"]
        other = {**APPROVAL, "campaign_id": "c", "ledger_genesis_id": "another"}
        assert any("another ledger" in m for m in _evaluate(online, approval=other))
        assert _evaluate(online, entitlement=None) == ["the account's target entitlement is not verified"]
        partial = {**ENTITLEMENT, "targets": ["walmart_search"]}
        assert _evaluate(online, entitlement=partial) == ["no verified entitlement for walmart_product"]
        assert _evaluate(online, rates=None) == ["the account's maximum billing rates are not confirmed"]
        unknown = {**CONFIRMED_RATES, "rates": {"walmart_search": CONFIRMED_RATES["rates"]["walmart_search"]}}
        assert _evaluate(online, rates=unknown) == ["no confirmed rate for walmart_product"]
        unconfirmed = {**CONFIRMED_RATES, "confirmed_by": ""}
        assert any("not confirmed" in m for m in _evaluate(online, rates=unconfirmed))
        assert any("SYNTHETIC" in m for m in _evaluate(online, rates=SYNTHETIC_RATES))
        unstated = {k: v for k, v in CONFIRMED_RATES.items() if k != "synthetic"}
        assert any(
            "SYNTHETIC" in m for m in _evaluate(online, rates=unstated)
        )  # silence is not a confirmation
        assert _evaluate(online, credentials=False) == ["credentials are not present"]
        assert any(
            "does not include marianos" in m
            for m in _evaluate(
                online,
                retailer="marianos",
                approval={
                    **APPROVAL,
                    "retailers": ["walmart"],
                    "campaign_id": "c",
                    "ledger_genesis_id": online.genesis_id,
                },
            )
        )
    finally:
        online.close()


def test_an_offline_ledger_never_authorizes_a_request(make_ledger: Any) -> None:
    led = make_ledger()
    assert any("offline test ledger" in m for m in _evaluate(led))


def test_this_build_cannot_construct_its_http_transport() -> None:
    assert gates.LIVE_ENABLED is False
    with pytest.raises(gates.LiveDisabled):
        transport.HttpTransport(gates.Credentials("placeholder-user", "placeholder-password"))
    assert "placeholder" not in repr(gates.Credentials("placeholder-user", "placeholder-password"))


def test_the_live_command_refuses_without_reading_a_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(gates.ENV_USERNAME, "sentinel-user-value")
    monkeypatch.setenv(gates.ENV_PASSWORD, "sentinel-password-value")

    def never(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("a credential was read")

    monkeypatch.setattr(gates, "load_credentials", never)
    monkeypatch.setattr(gates, "credentials_present", never)
    manifest = tmp_path / "manifest.json"
    assert (
        cli.main(
            [
                "campaign-init",
                "--manifest",
                str(manifest),
                "--ledger",
                str(tmp_path / "l.sqlite3"),
                "--campaign-id",
                "future",
            ]
        )
        == 0
    )
    capsys.readouterr()
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({**APPROVAL, "campaign_id": "future", "ledger_genesis_id": "x"}), "utf-8")
    code = cli.main(["live", "--manifest", str(manifest), "--approval", str(approval)])
    out = capsys.readouterr().out
    assert code == cli.EXIT_LIVE_REFUSED
    body = json.loads(out)
    assert body["live"] == "refused" and body["nothing was sent"] is True
    assert any("disabled in this build" in m for m in body["missing"])
    assert "sentinel" not in out
