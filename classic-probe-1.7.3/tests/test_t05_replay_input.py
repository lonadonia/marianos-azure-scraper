"""Release 1.7.3, T05: a replay whose saved responses are missing, unreadable, malformed or invalid is refused
with one concise line and exit code 2, before anything is created; never a traceback, never a network use,
never a credential read. A valid replay behaves as before.

Up to 1.7.2 a missing ``replay.json`` ended in a ``FileNotFoundError`` traceback (exit 1) after ``--out`` and
an offline ledger had been created; a missing ``body_file`` likewise; ``{}`` raised a ``KeyError`` traceback.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from classic_probe import cli, gates
from tests import fixture_builder as fb
from tests.conftest import SYNTHETIC_RATES
from tests.test_offline import GUARD

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "config" / "targets.json"


def valid_fixtures(folder: Path) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    spec: dict[str, Any] = {"steps": {}}
    for step, answers in fb.complete().items():
        spec["steps"][step] = []
        for i, (status, body) in enumerate(answers):
            (folder / f"{step}-{i}.json").write_bytes(body)
            spec["steps"][step].append({"http_status": status, "body_file": f"{step}-{i}.json"})
    (folder / "replay.json").write_text(json.dumps(spec), "utf-8")
    return spec


def args(tmp: Path, fixtures: Path) -> list[str]:
    rates = tmp / "rates.json"
    rates.write_text(json.dumps(SYNTHETIC_RATES), "utf-8")
    return [
        "replay",
        "--targets",
        str(TARGETS),
        "--fixtures",
        str(fixtures),
        "--rates",
        str(rates),
        "--out",
        str(tmp / "out"),
    ]


def refused(capsys: pytest.CaptureFixture[str], code: int) -> str:
    out = capsys.readouterr()
    assert code == cli.EXIT_USAGE == 2
    assert out.out == "" and "Traceback" not in out.err
    lines = out.err.strip().splitlines()
    assert len(lines) == 1
    message: str = json.loads(lines[0])["refused"]
    assert message.startswith("ReplayRefused: ")
    return message


def test_a_missing_replay_file_is_refused_before_anything_is_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_credentials() -> Any:
        raise AssertionError("a replay read a credential")

    monkeypatch.setattr(gates, "load_credentials", no_credentials)
    monkeypatch.setattr(gates, "credentials_present", no_credentials)
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    message = refused(capsys, cli.main(args(tmp_path, fixtures)))
    assert message == f"ReplayRefused: replay.json is missing in {fixtures}"
    assert not (tmp_path / "out").exists()  # no output folder, no ledger


def test_a_missing_fixtures_folder_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    message = refused(capsys, cli.main(args(tmp_path, tmp_path / "nowhere")))
    assert "does not exist" in message and not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{not json", "is not valid JSON (line 1, column 2)"),
        ("", "is not valid JSON (line 1, column 1)"),
        ("[]", 'must be an object whose "steps"'),
        ("{}", 'must be an object whose "steps"'),
        ('{"steps": []}', 'must be an object whose "steps"'),
        ('{"steps": {}}', 'must be an object whose "steps"'),
        ('{"steps": {"s": []}}', "step 's': a non-empty list"),
        ('{"steps": {"s": [1]}}', "step 's', response 1: an object is required"),
        ('{"steps": {"s": [{"body": "x"}]}}', "http_status must be an integer from 100 to 599"),
        ('{"steps": {"s": [{"http_status": "200"}]}}', "http_status must be an integer"),
        ('{"steps": {"s": [{"http_status": true}]}}', "http_status must be an integer"),
        ('{"steps": {"s": [{"http_status": 99}]}}', "http_status must be an integer from 100 to 599"),
        ('{"steps": {"s": [{"http_status": 200, "body": 5}]}}', "body must be a string"),
        ('{"steps": {"s": [{"http_status": 200, "body": "", "body_file": "a"}]}}', "not both"),
        ('{"steps": {"s": [{"http_status": 200, "body_file": "gone.json"}]}}', "'gone.json' is missing"),
        (
            '{"steps": {"s": [{"http_status": 200, "body_file": "../rates.json"}]}}',
            "outside the fixtures folder",
        ),
        ('{"steps": {"s": [{"http_status": 200, "body_file": ""}]}}', "body_file must be a file name"),
    ],
)
def test_a_malformed_or_invalid_replay_file_is_refused_with_its_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, expected: str
) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "replay.json").write_text(text, "utf-8")
    message = refused(capsys, cli.main(args(tmp_path, fixtures)))
    assert expected in message, message
    assert not (tmp_path / "out").exists()


def test_a_replay_file_that_is_not_utf8_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "replay.json").write_bytes(b"\xff\xfe{")
    assert "cannot be read (UnicodeDecodeError)" in refused(capsys, cli.main(args(tmp_path, fixtures)))


def test_missing_targets_or_rates_are_refused_too(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixtures = tmp_path / "fixtures"
    valid_fixtures(fixtures)
    argv = args(tmp_path, fixtures)
    argv[argv.index("--rates") + 1] = str(tmp_path / "no-rates.json")
    assert "--rates" in refused(capsys, cli.main(argv)) and not (tmp_path / "out").exists()


def test_a_valid_replay_runs_as_before(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixtures = tmp_path / "fixtures"
    spec = valid_fixtures(fixtures)
    # A response given inline and an empty one stay valid.
    first = next(iter(spec["steps"]))
    spec["steps"][first].append({"http_status": 500})
    (fixtures / "replay.json").write_text(json.dumps(spec), "utf-8")
    code = cli.main(args(tmp_path, fixtures))
    body = json.loads(capsys.readouterr().out)
    assert code == 0 and body["OFFLINE REPLAY"] is True and body["dispatched"] == 4 and body["stop"] is None


def test_the_refusal_in_its_own_process_has_no_traceback_network_or_credential(tmp_path: Path) -> None:
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    log = tmp_path / "network.log"
    env = {k: v for k, v in os.environ.items() if not k.startswith("OXYLABS")}
    # The process runs the same source as this test (the folder that holds the imported ``classic_probe``),
    # not whatever build the environment has installed.
    source = Path(cli.__file__).resolve().parents[1]
    env.update(
        PYTHONPATH=os.pathsep.join([str(guard), str(source)]), PROBE_NETWORK_LOG=str(log), PYTHONUTF8="1"
    )
    env[gates.ENV_USERNAME] = "sentinel-username-not-a-credential"
    env[gates.ENV_PASSWORD] = "sentinel-password-not-a-credential"
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for case in ("missing", "malformed"):
        if case == "malformed":
            (fixtures / "replay.json").write_text("{", "utf-8")
        done = subprocess.run(
            [sys.executable, "-m", "classic_probe", *args(tmp_path, fixtures)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert Path(str(log) + ".loaded").is_file(), "the network guard was not loaded"
        probe = subprocess.run(
            [sys.executable, "-c", "import classic_probe; print(classic_probe.__file__)"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        assert Path(probe.stdout.strip()).resolve().parent.parent == source
        assert done.returncode == 2, (case, done.stdout, done.stderr)
        assert done.stdout == "" and "Traceback" not in done.stderr, case
        assert len(done.stderr.strip().splitlines()) == 1, done.stderr
        assert "sentinel" not in done.stdout + done.stderr
        assert not log.exists(), log.read_text("utf-8")
        assert not (tmp_path / "out").exists()
