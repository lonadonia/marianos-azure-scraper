"""The headless collector through its command line, end to end: a throwaway PostgreSQL, a local storage
folder, a local Chromium over CDP standing in for Scrapfly's cloud browser, the local mock site of
test_live_collector (SYNTHETIC pages shaped like marianos.com's) and a fake answer of Scrapfly's Account
API. Chromium resolves no host except 127.0.0.1, so nothing can reach Mariano's or Scrapfly."""

from __future__ import annotations

import json
import shutil
import signal
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from marianos_headless import __version__, operations
from marianos_headless.acquisition import scrapfly
from marianos_headless.cli import Terminated, main, run_async
from marianos_headless.collection.live import LiveCollector
from marianos_headless.core.schema import OUTPUT_FIELDS
from marianos_headless.db.locks import StoreRunLock
from marianos_headless.db.models import CollectionSegment, Event, NodeCoverage, RecordRow, Run
from tests.conftest import CONFIG, STORE_KEY
from tests.integration.test_live_collector import (  # noqa: F401  (cloud_browser is a fixture)
    KEY,
    FakeAccount,
    cloud_browser,
    make_handler,
    requires_chromium,
)

pytestmark = [pytest.mark.postgres, pytest.mark.browser, requires_chromium]
CANNED = ("--categories", "7", "--subcategory", "7:01006")  # Grocery › Canned Foods on the mock site


@dataclass
class Env:
    config: Path
    engine: Engine
    data: Path
    account: FakeAccount
    capsys: pytest.CaptureFixture[str]

    def cli(self, *args: str) -> tuple[int, list[dict[str, Any]]]:
        self.capsys.readouterr()
        code = main(["--config", str(self.config), *args])
        out = self.capsys.readouterr().out
        return code, [json.loads(line) for line in out.splitlines() if line.startswith("{")]

    def result(self, *args: str) -> tuple[int, Any]:
        code, lines = self.cli(*args)
        res = [x for x in lines if x["event"] == "RESULT"]
        return code, (res[-1]["result"] if res else lines)

    def runs(self) -> list[Run]:
        with sessionmaker(self.engine, expire_on_commit=False)() as s:
            return list(s.scalars(select(Run).order_by(Run.created_at)))


def _serve(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _sigterm_handler() -> type[BaseHTTPRequestHandler]:
    base = make_handler("ok")

    class OnLoadMore(base):  # type: ignore[valid-type, misc]
        sent: list[str] = []  # noqa: RUF012

        def do_GET(self) -> None:
            if "page.offset=24" in self.path and not OnLoadMore.sent:  # the first "Load More"
                OnLoadMore.sent.append(self.path)
                signal.raise_signal(signal.SIGTERM)
            super().do_GET()

    return OnLoadMore


ARMED: list[bool] = []  # a SIGTERM at the next "Load More" when it holds True (mode "sigterm_armed")


def _armed_sigterm_handler() -> type[BaseHTTPRequestHandler]:
    base = make_handler("ok")

    class OnArmedLoadMore(base):  # type: ignore[valid-type, misc]
        def do_GET(self) -> None:
            if "page.offset=24" in self.path and ARMED and ARMED[-1]:
                ARMED.append(False)
                signal.raise_signal(signal.SIGTERM)
            super().do_GET()

    return OnArmedLoadMore


@pytest.fixture
def site(request: pytest.FixtureRequest) -> Iterator[str]:
    mode = getattr(request, "param", "ok")
    if mode == "sigterm":
        handler = _sigterm_handler()
    elif mode == "sigterm_armed":
        handler = _armed_sigterm_handler()
    else:
        handler = make_handler(mode)
    yield from _serve(handler)


@pytest.fixture
def env(
    migrated_engine: Engine,
    pg_url: str,
    site: str,
    cloud_browser: str,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> Env:
    cfg_dir = tmp_path / "config"
    shutil.copytree(CONFIG, cfg_dir)
    settings = yaml.safe_load((cfg_dir / "settings.yaml").read_text(encoding="utf-8"))
    acq = settings["acquisition"]
    acq["browser_provider"] = "scrapfly"  # these tests drive the Scrapfly path against the mock site
    acq["scrapfly"].update(endpoint=cloud_browser, target_url=site + "/")
    acq.update(navigation_min_interval_s=1.0, navigation_interval_jitter_s=0.0)
    (cfg_dir / "settings.yaml").write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("MARIANOS_COLLECTOR_DATABASE_URL", pg_url)
    monkeypatch.setenv("SCRAPFLY_API_KEY", KEY)
    monkeypatch.setenv("MARIANOS_COLLECTOR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(LiveCollector, "LISTING_SETTLE_MS", 300)
    monkeypatch.setattr(LiveCollector, "STEP_SETTLE_MS", 200)
    account = FakeAccount()
    real = scrapfly.read_account
    monkeypatch.setattr(scrapfly, "read_account", lambda s, k, get=None: real(s, k, get=account))
    return Env(cfg_dir / "collector.yaml", migrated_engine, tmp_path / "data", account, capsys)


def test_a_pilot_run_selects_the_store_passes_the_canary_and_is_exported_never_published(env: Env) -> None:
    code, res = env.result("provider-balance")
    assert code == 0 and res["connection"] == "ok" and res["balance"]["remaining"] == 5000
    code, lines = env.cli("run", "--store", STORE_KEY, *CANNED, "--max-products", "10")
    assert code == 0, [(x["event"], x.get("message", "")[:120]) for x in lines]
    [run] = env.runs()
    assert run.config_snapshot["pilot"] is True and run.stop_code == "RUN_PRODUCT_LIMIT"
    canary = run.counts["canary"]
    assert canary["status"] == "passed" and canary["source_check"]["mismatch"] == 0
    assert canary["source_check"]["verified"] == canary["valid"]
    exports = env.data / "runs" / STORE_KEY / run.id / "exports"
    manifest = json.loads((exports / "manifest.json").read_text("utf-8"))
    products = json.loads((exports / "products.json").read_text("utf-8"))
    assert manifest["dataset"] == "pilot" and len(products) == 10
    assert all(list(p) == list(OUTPUT_FIELDS) for p in products)
    assert {p["store_name"] for p in products} == {"Marianos Lakeshore East"}
    code, res = env.result("validate-export", "--run", run.id)
    assert res["manifest"]["problems"] == [] and res["source_check"]["summary"]["verified"] == 10
    # The synthetic site's product and picture URLs are on 127.0.0.1, not marianos.com and kroger.com:
    # the only contract problems, and the reason this export is rejected (exit 6).
    assert code == 6 and set(res["contract"]["problems"]) == {"url host", "image host"}
    assert not (env.data / "published").exists()
    with sessionmaker(env.engine)() as s:
        segs = list(s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run.id)))
        assert segs and all(seg.browsers_closed == seg.browser_sessions >= 1 for seg in segs)
    dumped = json.dumps(lines) + "".join(
        p.read_text("utf-8", errors="replace") for p in env.data.rglob("*.json")
    )
    assert KEY not in dumped


@pytest.mark.parametrize("site", ["store_not_listed"], indirect=True)
def test_a_store_the_picker_cannot_select_holds_the_store(env: Env) -> None:
    code, _ = env.result("run", "--store", STORE_KEY, *CANNED, "--max-products", "10")
    assert code == 7
    [run] = env.runs()
    assert run.stop_code == "STORE_NOT_VERIFIED" and run.status == "rejected"
    code, _ = env.result("run", "--store", STORE_KEY, *CANNED)
    assert code == 8 and len(env.runs()) == 1
    code, status = env.result("status", "--store", STORE_KEY)
    assert status["stores"][0]["hold"]["stop_code"] == "STORE_NOT_VERIFIED"


@pytest.mark.parametrize("site", ["sigterm"], indirect=True)
def test_a_termination_signal_closes_the_browser_and_resume_finishes_the_run(env: Env) -> None:
    code, lines = env.cli("run", "--store", STORE_KEY, *CANNED)
    assert code == 75, [(x["event"], x.get("message", "")[:120]) for x in lines]
    assert any(x["event"] == "SIGNAL_RECEIVED" for x in lines)
    [run] = env.runs()
    assert run.status == "interrupted" and run.stop_code == "TERMINATED"
    with sessionmaker(env.engine)() as s:
        segs = list(s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run.id)))
        assert segs and all(
            seg.ended_at is not None and seg.browsers_closed == seg.browser_sessions for seg in segs
        )
    with StoreRunLock(env.engine, run.store_id, run.id, "probe"):
        pass
    code, _ = env.result("resume", "--store", STORE_KEY)
    assert code == 0
    [done] = env.runs()
    assert done.status in ("validated", "rejected") and done.counts["records_by_status"]["valid"] > 24


def test_no_key_exits_3_before_anything_is_opened(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCRAPFLY_API_KEY")
    code, _ = env.result("run", "--store", STORE_KEY, *CANNED)
    assert code == 3 and env.runs() == [] and env.account.calls == 0


def test_products_a_later_partial_run_does_not_observe_are_carried_forward(env: Env) -> None:
    """SYNTHETIC pages: a run of 10 products, then a run stopped after 5: the other verified products are
    carried forward unchanged, each with its own crawl date, its run and the reason."""
    assert env.result("run", "--store", STORE_KEY, *CANNED, "--max-products", "10")[0] == 0
    first = env.runs()[0]
    assert env.result("run", "--store", STORE_KEY, *CANNED, "--max-products", "5")[0] == 0
    second = env.runs()[-1]
    with sessionmaker(env.engine)() as s:
        before = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == first.id))}
        rows = {r.upc: r for r in s.scalars(select(RecordRow).where(RecordRow.run_id == second.id))}
    verified = {k for k, r in before.items() if r.status in ("valid", "exported_not_valid")}
    fresh = {k for k, r in rows.items() if r.status in ("valid", "exported_not_valid")}
    carried = {k for k, r in rows.items() if r.status == "historical"}
    assert len(fresh) == 5 and carried == verified - fresh and len(carried) == 5
    for k in carried:
        row = rows[k]
        assert row.record == before[k].record and "CARRIED_FORWARD" in row.flags
        hist = row.provenance["historical"]
        assert hist["run_id"] == first.id and hist["why_not_observed"]
    exports = env.data / "runs" / STORE_KEY / second.id / "exports"
    products = json.loads((exports / "products.json").read_text("utf-8"))
    log = json.loads((exports / "provenance.json").read_text("utf-8"))
    assert len(products) == 10 and all(list(p) == list(OUTPUT_FIELDS) for p in products)
    assert log["counts"]["observed"]["carried_forward"] == 5
    assert {log["records"][k]["observation_kind"] for k in carried} == {"carried_forward"}

    # Release 1.2.0: the run's own observations in a separate file, the same 22 fields; the retained file
    # adds the carried-forward products. Each record names the stored page copy it was read from.
    fresh_file = json.loads((exports / "products_fresh.json").read_text("utf-8"))
    assert {p["upc"] for p in fresh_file} == fresh and all(list(p) == list(OUTPUT_FIELDS) for p in fresh_file)
    assert (exports / "products_fresh.csv").read_bytes().startswith(b"\xef\xbb\xbfzipcode,")
    manifest = json.loads((exports / "manifest.json").read_text("utf-8"))
    assert manifest["record_count"] == 10 and manifest["fresh_record_count"] == 5
    assert {"products_fresh.json", "products_fresh.csv"} <= set(manifest["files"])
    assert log["collector"]["run_code"]["version"] == log["collector"]["export_code"]["version"]
    for k, rec in log["records"].items():
        cap = rec["capture"]
        assert cap["dom_sha256"] and len(cap["dom_sha256"]) == 64
        assert cap["run_id"] == (first.id if k in carried else second.id)
    code, report = env.result("validate-export", "--run", second.id)
    # The mock site is not www.marianos.com, so the contract's host rule flags every product and image URL
    # (exit 6); everything else holds: carried-forward records are checked against their own run's pages.
    assert code == 6 and not report["manifest"]["problems"]
    for checked in (report["contract"], report["fresh_file"]["contract"]):
        assert set(checked["problems"]) == {"url host", "image host"}
    fresh_check = report["fresh_file"]
    assert fresh_check["records"] == 5 and fresh_check["subset_of_products"]
    assert fresh_check["carried_in_products"] == 5 and fresh_check["carried_match_supporting_log"]
    assert report["source_check"]["by_run"] == {
        rid: {
            "records": 5,
            "verified": 5,
            "mismatch": 0,
            "unverified": 0,
            "recorded_conflict": 0,
            "recorded_store_not_stated": 0,
        }
        for rid in (first.id, second.id)
    }
    with sessionmaker(env.engine)() as s:
        started = list(
            s.scalars(select(Event).where(Event.run_id == second.id, Event.code == "SEGMENT_STARTED"))
        )
    # Each execution records the code that ran it (version and source revision).
    assert started and all(
        e.data["code"]["version"] == __version__ and e.data["code"]["commit"] for e in started
    )
    out = env.data.parent / "export_copy"
    code, copied = env.result("export", "--run", second.id, "--out", str(out))
    assert code == 0 and "products_fresh.json" in copied["files"]
    assert (out / "products_fresh.json").read_bytes() == (exports / "products_fresh.json").read_bytes()


MONDAY = datetime(2026, 11, 2, 13, 5, tzinfo=UTC)  # 07:05 in Chicago (CST)
THURSDAY = datetime(2026, 11, 5, 13, 5, tzinfo=UTC)


@pytest.mark.parametrize("site", ["sigterm_armed"], indirect=True)
def test_the_next_occurrence_closes_an_unfinished_scheduled_run_and_reads_its_backlog_first(env: Env) -> None:
    """Release 1.5.0, the continuation/backlog policy (SYNTHETIC pages). A manual run reads Canned Foods
    to its end. Monday's scheduled run reads first Soda & Pop, which no run has read to its end, then Canned
    Foods, and is stopped by a termination signal at Canned Foods' first Load More: it stays unfinished.
    Thursday's occurrence closes it (SUPERSEDED: finalized, never published), and its own run reads first
    Canned Foods, the listing the closed run did not finish (its last complete read is the older one), then
    Soda & Pop."""
    collector = yaml.safe_load(env.config.read_text(encoding="utf-8"))
    collector["collections"][STORE_KEY].update(
        categories=[7, 11],
        subcategories={"7": ["01006"], "11": ["04001"]},
        max_auto_resumes=0,
        schedule={
            "enabled": True,
            "weekdays": [0, 3],
            "start_time": "07:00",
            "window_end": "19:00",
            "continue_unfinished": True,
            "backlog_first": True,
        },
    )
    env.config.write_text(yaml.safe_dump(collector, sort_keys=False), encoding="utf-8")
    assert env.result("run", "--store", STORE_KEY, *CANNED)[0] == 0
    manual = env.runs()[-1]
    assert manual.config_snapshot["plan"]["order"] == {"policy": "csv"}  # a manual run keeps the CSV order

    def scheduled(now: datetime) -> int:
        """``run --scheduled`` at ``now``, through the command line's own signal guard."""
        ctx = operations.Context(env.config)
        try:
            return int(run_async(operations.scheduled_run(ctx, STORE_KEY, now=now)))
        except Terminated:
            return int(operations.Exit.INTERRUPTED)
        finally:
            ctx.close()

    def coverage(run_id: str) -> dict[str, str]:
        with sessionmaker(env.engine)() as s:
            rows = s.scalars(select(NodeCoverage).where(NodeCoverage.run_id == run_id))
            return {c.taxonomy_id: c.status for c in rows}

    ARMED.append(True)
    assert scheduled(MONDAY) == 75
    monday = env.runs()[-1]
    assert (
        monday.trigger == "schedule" and monday.status == "interrupted" and monday.stop_code == "TERMINATED"
    )
    assert [n["taxonomy_id"] for n in monday.config_snapshot["plan"]["nodes"]] == ["04001", "01006"]
    assert monday.config_snapshot["plan"]["order"] == {"policy": "backlog_first", "backlog": ["04001"]}
    assert coverage(monday.id) == {"04001": "DONE", "01006": "IN_PROGRESS"}

    assert scheduled(THURSDAY) in (0, 6)
    closed, thursday = next(r for r in env.runs() if r.id == monday.id), env.runs()[-1]
    assert closed.stop_code == "SUPERSEDED" and closed.status in ("validated", "rejected")
    assert closed.status != "published"  # a closed run is never published
    assert "reads first the listings this run did not finish" in (closed.stop_detail or "")
    assert thursday.id not in (manual.id, monday.id) and thursday.trigger == "schedule"
    plan = thursday.config_snapshot["plan"]
    assert [n["taxonomy_id"] for n in plan["nodes"]] == ["01006", "04001"]
    assert plan["order"] == {"policy": "backlog_first", "backlog": []}
    with sessionmaker(env.engine)() as s:
        ev = s.scalars(select(Event).where(Event.run_id == thursday.id, Event.code == "BACKLOG_FIRST")).one()
    assert ev.data == {"backlog": [], "order": ["01006", "04001"]}
    assert coverage(thursday.id) == {"01006": "DONE", "04001": "DONE"}
