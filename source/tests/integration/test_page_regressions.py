"""The client's pagination finding, as behaviour only (release 1.8.0).

Finding: ``pagination_check()`` asked for page 2, compared identities and stopped: page 2 never reached the
Finding: ``pagination_check()`` asked for page 2, compared identities and stopped: page 2 never reached the
data. These five regressions name what a run must do and read only what every release has (the exported
records, the requests, the listing's coverage), so the same file runs against the defective release 1.7.0rc2
and against the correction: ``scripts/`` of the evidence package holds both results. SYNTHETIC pages
(``tests/listing_site.py``)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, select

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection.config import CollectionConfig
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    PrivateLabelConfig,
    Settings,
    StoreConfig,
)
from marianos_headless.db.models import CategorySource, NodeCoverage, RecordRow, Run
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests.conftest import CONFIG, STORE_KEY
from tests.integration.helpers import seed
from tests.listing_site import KEY, Site, plan_nodes, products

pytestmark = [pytest.mark.postgres]


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
def env(
    migrated_engine: Engine, tmp_path: Path, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    with factory() as s:
        oxylabs.set_ceiling(s, submissions=100, usd=10, actor="test", reason="test")
        s.commit()
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": dev_store,
        "private_label": private_label,
        "tmp": tmp_path,
    }


def _pipe(env: dict[str, Any], settings: Settings) -> Pipeline:
    acq = AcquisitionSettings(browser_provider=BrowserProvider.OXYLABS)
    return Pipeline(
        env["engine"],
        env["storage"],
        Settings(acquisition=acq, records=settings.records, attestation=settings.attestation),
        env["store"],
        env["private_label"],
    )


def _new_run(env: dict[str, Any], pipe: Pipeline) -> str:
    with env["factory"]() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
    nodes = plan_nodes(ids, ("03001",))
    with env["factory"]() as s:
        run_id = pipe.create_live_run(
            s,
            nodes,
            trigger="console",
            snapshot={"plan": {"nodes": [n.as_dict() for n in nodes], "skipped": []}, "provider": "oxylabs"},
        )
        s.commit()
    return run_id


def _execute(pipe: Pipeline, run_id: str, site: Site, *, resume: bool = False) -> str:
    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(site),
        sleep=_no_sleep,
        config=CollectionConfig(),
        trigger="manual",
    )
    return asyncio.run(pipe.execute(run_id, "test-collector", resume=resume, collector=collector))


def _records(env: dict[str, Any], run_id: str) -> list[str]:
    with env["factory"]() as s:
        return list(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))


def _status(env: dict[str, Any], run_id: str) -> str | None:
    with env["factory"]() as s:
        return s.scalar(
            select(NodeCoverage.status).where(
                NodeCoverage.run_id == run_id, NodeCoverage.taxonomy_id == "03001"
            )
        )


def test_regression_1_a_three_page_listing_exports_products_from_all_three_pages(
    env: dict[str, Any], settings: Settings
) -> None:
    pipe = _pipe(env, settings)
    run_id = _new_run(env, pipe)
    site = Site({"03001": products(60)})
    _execute(pipe, run_id, site)
    upcs = _records(env, run_id)
    assert sorted(upcs) == sorted(p.upc for p in products(60))
    assert _status(env, run_id) == "DONE"


def test_regression_2_a_page_2_failure_remains_unfinished_and_resumes_correctly(
    env: dict[str, Any], settings: Settings
) -> None:
    pipe = _pipe(env, settings)
    run_id = _new_run(env, pipe)
    site = Site({"03001": products(60)})
    site.on("03001", 2, *["fail"] * 9)
    status = _execute(pipe, run_id, site)
    assert status == "interrupted"
    assert len(_records(env, run_id)) == 24 and _status(env, run_id) != "DONE"
    site.asked.clear()
    _execute(pipe, run_id, site, resume=True)
    assert site.asked == [("03001", 2), ("03001", 3)]
    assert sorted(_records(env, run_id)) == sorted(p.upc for p in products(60))
    assert _status(env, run_id) == "DONE"


def test_regression_3_a_repeated_page_stops_safely_without_false_completeness(
    env: dict[str, Any], settings: Settings
) -> None:
    pipe = _pipe(env, settings)
    run_id = _new_run(env, pipe)
    site = Site({"03001": products(72)})
    site.on("03001", 3, "repeat")  # pages 1 and 2 are real and belong in the data
    _execute(pipe, run_id, site)
    assert ("03001", 4) not in site.asked
    assert len(_records(env, run_id)) == 48
    assert _status(env, run_id) == "INCOMPLETE"


@pytest.mark.parametrize("what", ["wrong_store", "wrong_fulfillment"])
def test_regression_4_a_wrong_store_or_fulfillment_page_cannot_enter_the_dataset(
    env: dict[str, Any], settings: Settings, what: str
) -> None:
    pipe = _pipe(env, settings)
    run_id = _new_run(env, pipe)
    site = Site({"03001": products(60)})
    site.on("03001", 2, what)
    _execute(pipe, run_id, site)
    assert ("03001", 2) in site.asked  # the page was read and refused, not simply never asked for
    assert len(_records(env, run_id)) == 24
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "STORE_NOT_VERIFIED"


def test_regression_5_a_restart_neither_duplicates_products_nor_refetches_completed_pages(
    env: dict[str, Any], settings: Settings
) -> None:
    pipe = _pipe(env, settings)
    run_id = _new_run(env, pipe)
    args = {
        "config": str(CONFIG),
        "db": env["engine"].url.render_as_string(hide_password=False),
        "store": STORE_KEY,
        "data": str(env["tmp"] / "data"),
        "run": run_id,
        "moment": "request",
        "listing": "03001",
        "page": 3,
        "listings_n": {"03001": 60},
    }
    p = subprocess.run(
        [sys.executable, "-m", "tests.listing_site", json.dumps(args)],
        cwd=Path(__file__).resolve().parents[2],
        env=dict(os.environ),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    assert p.returncode == 137, (p.returncode, p.stderr[-1500:])
    assert len(_records(env, run_id)) == 48
    site = Site({"03001": products(60)})
    _execute(pipe, run_id, site, resume=True)
    assert site.asked == [("03001", 3)]
    upcs = _records(env, run_id)
    assert len(upcs) == 60 and len(set(upcs)) == 60
    assert _status(env, run_id) == "DONE"
