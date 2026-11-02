"""Every command runs without a network and without reading a credential (OFFLINE).

In this process the network is closed by tests/conftest.py. The commands also run here as separate processes,
started with a ``sitecustomize`` that refuses every connection and name lookup and records any attempt, and
with sentinel values in the two credential variables, which no output may contain.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from classic_probe import gates
from tests import fixture_builder as fb
from tests.conftest import SYNTHETIC_RATES, NetworkUsed

ROOT = Path(__file__).resolve().parents[1]

GUARD = """
import os, socket
_log = os.environ["PROBE_NETWORK_LOG"]
open(_log + ".loaded", "a").close()
def _refuse(*args, **kwargs):
    with open(_log, "a", encoding="utf-8") as f:
        f.write(repr(args)[:200] + "\\n")
    raise OSError("the network is closed for this offline check")
socket.socket.connect = _refuse
socket.socket.connect_ex = _refuse
socket.create_connection = _refuse
socket.getaddrinfo = _refuse
"""


def test_the_offline_tests_cannot_reach_a_network(closed_network: list[str]) -> None:
    with pytest.raises(NetworkUsed):
        socket.getaddrinfo("realtime.oxylabs.io", 443)
    with pytest.raises(NetworkUsed):
        socket.create_connection(("realtime.oxylabs.io", 443), timeout=1)
    with pytest.raises(NetworkUsed):
        urllib.request.urlopen("https://realtime.oxylabs.io/v1/queries", timeout=1)
    assert len(closed_network) == 3
    closed_network.clear()  # the three attempts above were this test's own


def test_every_command_runs_in_its_own_process_without_a_network_or_a_credential(tmp_path: Path) -> None:
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    log = tmp_path / "network.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith("OXYLABS")}
    env.update(PYTHONPATH=str(guard), PROBE_NETWORK_LOG=str(log), PYTHONUTF8="1")
    env[gates.ENV_USERNAME] = "sentinel-username-not-a-credential"
    env[gates.ENV_PASSWORD] = "sentinel-password-not-a-credential"

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    spec: dict[str, dict[str, list[dict[str, object]]]] = {"steps": {}}
    for step, answers in fb.complete().items():
        spec["steps"][step] = []
        for i, (status, body) in enumerate(answers):
            (fixtures / f"{step}-{i}.json").write_bytes(body)
            spec["steps"][step].append({"http_status": status, "body_file": f"{step}-{i}.json"})
    (fixtures / "replay.json").write_text(json.dumps(spec), "utf-8")
    rates = tmp_path / "synthetic_rates.json"
    rates.write_text(json.dumps(SYNTHETIC_RATES), "utf-8")
    cfg = ROOT / "config"
    manifest, ledger_file = tmp_path / "manifest.json", tmp_path / "ledger.sqlite3"

    commands: list[tuple[list[str], int]] = [
        (["--help"], 0),
        (["--version"], 0),
        (["plan", "--targets", str(cfg / "targets.json")], 0),
        (["plan", "--targets", str(cfg / "targets.json"), "--rates", str(cfg / "rates.example.json")], 0),
        (["validate", "--targets", str(cfg / "targets.json"), "--rates", str(cfg / "rates.example.json")], 0),
        (
            [
                "campaign-init",
                "--manifest",
                str(manifest),
                "--ledger",
                str(ledger_file),
                "--campaign-id",
                "offline-check",
                "--offline",
            ],
            0,
        ),
        (["status", "--manifest", str(manifest)], 0),
        (
            [
                "confirm-charge",
                "--manifest",
                str(manifest),
                "--seq",
                "1",
                "--value",
                "0",
                "--unit",
                "usd",
                "--basis",
                "offline check",
            ],
            2,
        ),  # no dispatch 1: refused, nothing written
        (["export", "--manifest", str(manifest), "--out", str(tmp_path / "export")], 0),
        (
            [
                "replay",
                "--targets",
                str(cfg / "targets.json"),
                "--fixtures",
                str(fixtures),
                "--rates",
                str(rates),
                "--out",
                str(tmp_path / "replay"),
            ],
            0,
        ),
        (
            [
                "live",
                "--manifest",
                str(manifest),
                "--approval",
                str(cfg / "approval.example.json"),
                "--entitlement",
                str(cfg / "entitlement.example.json"),
                "--rates",
                str(cfg / "rates.example.json"),
            ],
            3,
        ),
    ]
    for args, expected in commands:
        Path(str(log) + ".loaded").unlink(missing_ok=True)
        done = subprocess.run(
            [sys.executable, "-m", "classic_probe", *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert Path(str(log) + ".loaded").is_file(), "the network guard was not loaded"
        assert done.returncode == expected, (args, done.stdout[-2000:], done.stderr[-2000:])
        assert "sentinel" not in done.stdout + done.stderr, args
        assert not log.exists(), (args, log.read_text("utf-8"))
    live = json.loads(done.stdout)
    assert live["live"] == "refused" and live["nothing was sent"] is True
    replay = json.loads((tmp_path / "replay" / "campaign_evidence.json").read_text("utf-8"))
    assert replay["offline"] is True and len(replay["dispatches"]) == 4
