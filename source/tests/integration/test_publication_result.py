"""What an execution reports when a complete, validated run is not published (release 1.10.0rc2).

Found in review of 1.9.0rc4 (``operations.after_run``): the automatic publication of a complete validated run
can be refused (an export that no longer matches its manifest, a WARN finding without a recorded reason, a
lineage problem). The refusal was logged at WARN and the execution still ended with exit code 0 and
``RUN_FINISHED`` at INFO, as a success, although nothing was published; a later firing of the same occurrence
said so again. The last published dataset was never at risk: that part is a control here.

SYNTHETIC: pages from ``tests/listing_site.py`` through a mock transport, at the client's store (53100502,
Pickup); the publication target is each test's own throwaway database and folder. The file loads on
1.9.0rc4 and 1.10.0rc1 too: ``test_control_...`` pass there, ``test_fix_...`` fail there. With
``PUBLICATION_EVIDENCE_DIR`` set, each test writes what it observed there before judging it."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import yaml
from sqlalchemy import Engine, select

from marianos_headless import __version__, operations
from marianos_headless.collection.schedule import occurrence_on
from marianos_headless.core import logs
from marianos_headless.core.settings import PrivateLabelConfig, Settings
from marianos_headless.core.version import source_version
from marianos_headless.db.models import Event, ExportRow, PublicationPointer, Run, Store
from marianos_headless.publishing.publish import latest_key
from tests import c1_site as c1
from tests.c1_site import TARGET, C1Site, Clock
from tests.listing_site import KEY, products

pytestmark = [pytest.mark.postgres]


@pytest.fixture
def env(
    migrated_engine: Engine,
    tmp_path: Path,
    private_label: PrivateLabelConfig,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    e = c1.make_env(migrated_engine, tmp_path, private_label)
    monkeypatch.setenv(
        "MARIANOS_COLLECTOR_DATABASE_URL", migrated_engine.url.render_as_string(hide_password=False)
    )
    monkeypatch.setenv("MARIANOS_COLLECTOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OXYLABS_WEB_API_KEY", KEY)  # named by a check; no request is made with it
    e["capsys"] = capsys
    return e


def _context(env: dict[str, Any], *, schedule: bool = False) -> operations.Context:
    """The shipped configuration (automatic publication on, no reason recorded for WARN findings); with
    ``schedule``, a copy whose Monday/Thursday schedule is on for the client's store."""
    config = c1.CONFIG
    if schedule:
        config = env["tmp"] / "config"
        if not config.exists():
            shutil.copytree(c1.CONFIG, config)
            path = config / "collector.yaml"
            body = yaml.safe_load(path.read_text(encoding="utf-8"))
            body["collections"][TARGET]["schedule"]["enabled"] = True
            path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    ctx = operations.Context(config / "collector.yaml")
    env.setdefault("contexts", []).append(ctx)
    return ctx


def _complete_run(env: dict[str, Any], settings: Settings, n: int = 60, **plan: Any) -> str:
    clock = Clock()
    site = C1Site({"03001": products(n)}, clock)
    pipe = c1.pipe_of(env, settings)
    run_id = c1.plan(env, pipe, c1.nodes_of(env, ("03001",)), **plan)
    collector = c1.collector_of(pipe, run_id, site, clock, max_reasks=None)
    status = asyncio.run(pipe.execute(run_id, "test-collector", collector=collector))
    assert status == "validated", status
    return run_id


def _published(env: dict[str, Any]) -> dict[str, Any] | None:
    with env["factory"]() as s:
        store = s.scalar(select(Store).where(Store.key == TARGET))
        ptr = s.get(PublicationPointer, store.id) if store is not None else None
        if ptr is None:
            return None
        state = {"publication_id": ptr.publication_id, "version": ptr.version}
    latest = env["storage"].get_bytes(latest_key(TARGET))
    return {
        **state,
        "published_run": json.loads(latest)["run_id"],
        "latest_json_sha256": hashlib.sha256(latest).hexdigest(),
    }


def _alter_an_export(env: dict[str, Any], run_id: str) -> str:
    """One export file changed on disk after the run was validated: it no longer matches its manifest."""
    with env["factory"]() as s:
        manifest = s.scalar(select(ExportRow).where(ExportRow.run_id == run_id, ExportRow.kind == "manifest"))
        assert manifest is not None
    files = json.loads(env["storage"].get_bytes(_key_of(env, manifest.artifact_id)))["files"]
    key = str(files["products.csv"]["key"])
    path = env["tmp"] / "data" / key
    assert path.is_file()
    path.write_bytes(path.read_bytes() + b"altered after validation\r\n")
    return key


def _key_of(env: dict[str, Any], artifact_id: str) -> str:
    from marianos_headless.db.models import Artifact

    with env["factory"]() as s:
        art = s.get(Artifact, artifact_id)
        assert art is not None
        return str(art.key)


def _finish(env: dict[str, Any], ctx: operations.Context, run_id: str) -> dict[str, Any]:
    """``after_run`` as an execution ends with it: its exit code, its log lines, the run and its events."""
    logs.configure()  # this test's own captured standard output (the stream is replaced for each test phase)
    env["capsys"].readouterr()
    code = operations.after_run(ctx, TARGET, run_id)
    raw = env["capsys"].readouterr()
    lines = [json.loads(x) for x in raw.out.splitlines() if x.startswith("{")]
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None
        events = [
            {"level": ev.level, "code": ev.code, "message": ev.message}
            for ev in s.scalars(select(Event).where(Event.run_id == run_id, Event.code.like("%PUBLI%")))
        ]
        status = run.status
    finished = [x for x in lines if x.get("event") == "RUN_FINISHED"]
    return {
        "exit_code": int(code),
        "run_status": status,
        "log": [
            {k: x.get(k) for k in ("level", "event", "exit_code", "message", "publication", "version")}
            for x in lines
            if x.get("event") in ("RUN_FINISHED", "RUN_PUBLISHED", "PUBLICATION_REFUSED")
        ],
        "run_finished": finished[-1] if finished else None,
        "events": events,
    }


def _evidence(name: str, data: dict[str, Any]) -> None:
    out = os.environ.get("PUBLICATION_EVIDENCE_DIR")
    if not out:
        return
    Path(out).mkdir(parents=True, exist_ok=True)
    body = {
        "case": name,
        "evidence_type": c1.SYNTHETIC + "; the refusal is injected",
        "live_request_sent": False,
        "collector_version": __version__,
        "source_revision": source_version(),
        **data,
    }
    (Path(out) / f"{name}.json").write_bytes(
        (json.dumps(body, indent=1, default=str, ensure_ascii=False) + "\n").encode("utf-8")
    )


def _warn_finding(env: dict[str, Any], run_id: str) -> str:
    """A WARN finding on the validated run (the shipped configuration records no reason to accept one)."""
    from marianos_headless.db.models import ValidationFinding

    with env["factory"]() as s:
        s.add(
            ValidationFinding(
                run_id=run_id,
                scope="run",
                ref=run_id,
                gate="G4",
                severity="WARN",
                code="YIELD_DROP",
                message="synthetic: fewer valid products than the last good run (test)",
            )
        )
        s.commit()
    return "a WARN finding without a recorded reason"


REFUSALS = {"altered_export": _alter_an_export, "warn_without_reason": _warn_finding}


def test_control_an_ordinary_complete_run_is_published_and_the_execution_ends_ok(
    env: dict[str, Any], settings: Settings
) -> None:
    ctx = _context(env)
    run_id = _complete_run(env, settings)
    out = _finish(env, ctx, run_id)
    published = _published(env)
    _evidence("control_ordinary_publication", {"result": out, "published": published})
    assert out["exit_code"] == 0 and out["run_status"] == "published"
    assert published is not None and (published["version"], published["published_run"]) == (1, run_id)
    assert out["run_finished"]["level"] == "INFO"
    assert [x["event"] for x in out["log"]] == ["RUN_PUBLISHED", "RUN_FINISHED"]


@pytest.mark.parametrize("why", sorted(REFUSALS))
def test_control_a_refused_publication_leaves_the_last_good_dataset_published(
    env: dict[str, Any], settings: Settings, why: str
) -> None:
    ctx = _context(env)
    first = _complete_run(env, settings)
    assert _finish(env, ctx, first)["exit_code"] == 0
    before = _published(env)
    second = _complete_run(env, settings, n=61)
    injected = REFUSALS[why](env, second)
    out = _finish(env, ctx, second)
    after = _published(env)
    _evidence(
        f"control_last_good_{why}", {"injected": injected, "result": out, "before": before, "after": after}
    )
    assert after == before and after is not None and after["published_run"] == first
    assert out["run_status"] == "validated"  # checked and complete, and not what is published


@pytest.mark.parametrize("why", sorted(REFUSALS))
def test_fix_a_refused_automatic_publication_is_reported_as_unsuccessful(
    env: dict[str, Any], settings: Settings, why: str
) -> None:
    ctx = _context(env)
    first = _complete_run(env, settings)
    assert _finish(env, ctx, first)["exit_code"] == 0
    second = _complete_run(env, settings, n=61)
    injected = REFUSALS[why](env, second)
    out = _finish(env, ctx, second)
    _evidence(f"fix_refused_{why}", {"injected": injected, "result": out, "published": _published(env)})
    assert out["exit_code"] == 6, out  # rejected: nothing was published (it was 0)
    done = out["run_finished"]
    assert done["level"] == "WARN" and done["exit_code"] == 6
    assert done["publication"]["published"] is False and done["publication"]["refused"]
    refused = [x for x in out["log"] if x["event"] == "PUBLICATION_REFUSED"]
    assert len(refused) == 1 and refused[0]["level"] == "ERROR"
    assert [(e["level"], e["code"]) for e in out["events"]] == [("ERROR", "PUBLICATION_REFUSED")]
    assert "the last published dataset stays" in out["events"][0]["message"]


def test_fix_a_later_firing_of_the_same_occurrence_says_again_that_nothing_was_published(
    env: dict[str, Any], settings: Settings
) -> None:
    """A scheduled occurrence whose run was validated and not published: Azure's retry of the firing (or the
    second UTC firing) finds the occurrence done. It must not report it as a success either."""
    ctx = _context(env, schedule=True)
    tz = ZoneInfo("America/Chicago")
    coll = ctx.config.collection(TARGET)
    occ = occurrence_on(coll.schedule, datetime(2026, 11, 9, tzinfo=tz).date(), tz)  # a Monday
    assert occ is not None
    ctx.clock = lambda: occ.start.astimezone(UTC)
    run_id = _complete_run(env, settings, trigger="schedule", occurrence=occ.as_dict())
    _alter_an_export(env, run_id)
    first = _finish(env, ctx, run_id)
    logs.configure()
    env["capsys"].readouterr()
    code = asyncio.run(operations.scheduled_run(ctx, TARGET))
    lines = [json.loads(x) for x in env["capsys"].readouterr().out.splitlines() if x.startswith("{")]
    done = [x for x in lines if x.get("event") == "OCCURRENCE_DONE"]
    _evidence(
        "fix_later_firing",
        {"first_execution": first, "later_firing_exit_code": int(code), "later_firing_log": done},
    )
    assert len(done) == 1  # the occurrence already has its run: nothing is collected again
    assert int(code) == 6 and done[0]["level"] == "WARN"
    assert done[0]["publication"]["published"] is False and done[0]["publication"]["refused"]
