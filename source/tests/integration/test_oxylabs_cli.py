"""The Oxylabs spending ceiling through the real CLI (release 1.3.0): nothing is sent to Oxylabs here."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from marianos_headless.cli import main
from marianos_headless.db.models import AuditLog
from tests.conftest import CONFIG

pytestmark = [pytest.mark.postgres]

KEY = "oxy-cli-key-0123456789abcdef-never-printed"


@pytest.fixture
def cli(
    migrated_engine: Engine,
    pg_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Any:
    cfg_dir = tmp_path / "config"
    shutil.copytree(CONFIG, cfg_dir)
    settings = yaml.safe_load((cfg_dir / "settings.yaml").read_text(encoding="utf-8"))
    settings["acquisition"]["browser_provider"] = "oxylabs"
    (cfg_dir / "settings.yaml").write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    key_file = tmp_path / "oxylabs.env"
    key_file.write_text(f"OXYLABS_API={KEY}\n", encoding="utf-8")
    monkeypatch.setenv("MARIANOS_COLLECTOR_DATABASE_URL", pg_url)
    monkeypatch.setenv("MARIANOS_COLLECTOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OXYLABS_WEB_API_KEY_FILE", str(key_file))

    def run(*args: str) -> tuple[int, Any, str]:
        capsys.readouterr()
        code = main(["--config", str(cfg_dir / "collector.yaml"), *args])
        out = capsys.readouterr()
        lines = [json.loads(x) for x in out.out.splitlines() if x.startswith("{")]
        res = [x["result"] for x in lines if x["event"] == "RESULT"]
        return code, (res[-1] if res else lines), out.out + out.err

    return run


def test_the_oxylabs_balance_is_the_operators_ceiling_and_the_ledger(
    cli: Any, migrated_engine: Engine
) -> None:
    code, res, text = cli("provider-balance")
    assert code == 4 and res["provider"] == "oxylabs" and res["room_submissions"] is None  # no ceiling yet
    assert res["key"]["configured"] and res["key"]["source"] == "OXYLABS_WEB_API_KEY_FILE"
    code, res, text = cli(
        "set-ceiling", "--provider", "oxylabs", "--submissions", "300", "--usd", "0.45", "--reason", "P5"
    )
    assert code == 0 and res["room_submissions"] == 300 and res["ceiling"]["usd"] == 0.45
    code, res, text = cli("provider-balance")
    assert code == 0 and res["room_submissions"] == 300 and res["all_time"]["submissions"] == 0
    assert KEY not in text
    code, _, _ = cli(
        "set-ceiling", "--provider", "oxylabs", "--submissions", "-1", "--usd", "0", "--reason", "x"
    )
    assert code == 2
    with sessionmaker(migrated_engine)() as s:
        (audit,) = s.scalars(select(AuditLog).where(AuditLog.action == "set_ceiling"))
        assert not audit.data["before"] and audit.data["after"]["submissions"] == 300


def test_validate_config_requires_the_configured_providers_key(
    cli: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, _, _ = cli("validate-config", "--require-credentials")
    assert code == 0
    monkeypatch.delenv("OXYLABS_WEB_API_KEY_FILE")
    code, res, _ = cli("validate-config", "--require-credentials")
    env = res["environment"]
    assert code == 3 and env["provider"] == "oxylabs" and not env["oxylabs_key"]["configured"]
