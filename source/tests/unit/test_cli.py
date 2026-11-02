"""Commands that need no database: configuration, the schedule, the operations entry point and the
contract check of a products file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from marianos_headless.cli import main
from marianos_headless.core.schema import OUTPUT_FIELDS
from tests.conftest import CAPTURES, CONFIG, STORE_KEY


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, list[dict[str, Any]]]:
    capsys.readouterr()
    code = main(["--config", str(CONFIG / "collector.yaml"), *args])
    out = capsys.readouterr().out
    return code, [json.loads(x) for x in out.splitlines() if x.startswith("{")]


def test_every_line_is_json_and_the_result_is_last(capsys: pytest.CaptureFixture[str]) -> None:
    code, lines = _run(capsys, "validate-config")
    assert code == 0 and lines[-1]["event"] == "RESULT"
    assert all({"ts", "level", "event", "collector"} <= set(x) for x in lines)
    assert lines[-1]["result"]["environment"]["scrapfly_key"]["configured"] is False


def test_validate_config_requires_the_configured_providers_key(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _run(capsys, "validate-config", "--require-credentials")[0] == 3
    scrapfly = tmp_path / "scrapfly.env"
    scrapfly.write_text("SCRAPFLY_API_KEY=" + "9" * 32 + "\n", encoding="utf-8")
    monkeypatch.setenv("SCRAPFLY_API_KEY_FILE", str(scrapfly))
    # The shipped configuration collects with Oxylabs: another provider's key is not its key.
    assert _run(capsys, "validate-config", "--require-credentials")[0] == 3
    oxy = tmp_path / "oxylabs.env"
    oxy.write_text("OXYLABS_API: " + "7" * 44 + "\n", encoding="utf-8")
    monkeypatch.setenv("OXYLABS_WEB_API_KEY_FILE", str(oxy))
    code, lines = _run(capsys, "validate-config", "--require-credentials")
    assert code == 0 and "9" * 32 not in json.dumps(lines) and "7" * 44 not in json.dumps(lines)
    env = lines[-1]["result"]["environment"]
    assert env["provider"] == "oxylabs" and env["oxylabs_key"]["source"] == "OXYLABS_WEB_API_KEY_FILE"


def test_the_operations_job_runs_the_command_named_in_its_variable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MARIANOS_COLLECTOR_COMMAND", f"schedule-info --store {STORE_KEY}")
    code, lines = _run(capsys, "ops")
    assert code == 0
    assert any(x["event"] == "OPS_COMMAND" for x in lines)
    assert lines[-1]["result"]["schedule"]["cron_utc"] == "0 12,13 * * 1,4"
    monkeypatch.setenv("MARIANOS_COLLECTOR_COMMAND", "ops")
    assert _run(capsys, "ops")[0] == 2


def test_a_command_that_needs_the_database_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    code, lines = _run(capsys, "status")
    assert code == 2 and "MARIANOS_COLLECTOR_DATABASE_URL" in lines[-1]["message"]


def test_validate_export_checks_the_22_field_contract(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    good = CAPTURES / "run_01M5CSS9_20261020" / "products.json"
    code, lines = _run(capsys, "validate-export", "--file", str(good))
    assert code == 0 and lines[-1]["result"]["contract"]["passed"]
    rows = json.loads(good.read_text("utf-8"))
    rows[0]["gupc"] = "123"  # always empty
    rows[1] = {k: rows[1][k] for k in reversed(OUTPUT_FIELDS)}  # fields out of order
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(rows), encoding="utf-8")
    code, lines = _run(capsys, "validate-export", "--file", str(bad))
    problems = lines[-1]["result"]["contract"]["problems"]
    assert code == 6 and problems["gupc or unit_price not empty"] == 1 and problems["field order"] == 1
