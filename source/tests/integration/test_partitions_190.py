"""Release 1.9.0: brand readings through the real run loop (M1, M2) and listings read in lanes (M8), against
the SYNTHETIC ``/pl/`` pages of ``tests/listing_site.py``.

M1: two brands whose names share their first 58 characters had one ID in 1.8.0rc5
(``f"{listing}~{name}"[:64]``), so the second brand was never planned. Each test here puts such a pair
through planning, the queue, the page rows, the export, a restart and two lanes.
M2: a brand reading's response counts only when it states that very filter.
M8: two lanes read two listings at once, never one task twice, and stop together."""

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
from sqlalchemy import Engine, func, select

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection import pagination, reconciliation
from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.collection.nodes import Node
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig
from marianos_headless.db import queue
from marianos_headless.db.models import Event, ListingPage, PageFetch, ProviderUsage, RecordRow, Run, Task
from marianos_headless.storage.local import LocalStorageAdapter
from tests.integration.helpers import CONFIG, STORE_KEY, seed
from tests.integration.test_listing_pages import _pipe, _plan
from tests.listing_site import KEY, Site, products

pytestmark = [pytest.mark.postgres]

LONG = "Blue Buffalo Life Protection Formula Natural Adult Dry Cat Food "  # 64 characters
A, B = LONG + "Chicken", LONG + "Salmon"


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
def env(
    migrated_engine: Engine, tmp_path: Path, dev_store: StoreConfig, private_label: PrivateLabelConfig
) -> dict[str, Any]:
    factory, _ = seed(migrated_engine)
    with factory() as s:
        oxylabs.set_ceiling(s, submissions=400, usd=10, actor="test", reason="test")
        s.commit()
    return {
        "engine": migrated_engine,
        "factory": factory,
        "storage": LocalStorageAdapter(tmp_path / "data"),
        "store": dev_store,
        "private_label": private_label,
        "tmp": tmp_path,
    }


class Slow:
    """The site behind an asynchronous transport: each answer is held a moment; requests in flight are
    counted."""

    def __init__(self, site: Site, hold_s: float = 0.05):
        self.site, self.hold_s = site, hold_s
        self.inflight = 0
        self.max_inflight = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(self.hold_s)
            return self.site(request)
        finally:
            self.inflight -= 1


def _run(
    env: dict[str, Any],
    settings: Settings,
    handler: Any,
    *,
    listings: tuple[str, ...] = ("03001",),
    run_id: str | None = None,
    lanes: int = 1,
) -> tuple[str, str]:
    pipe = _pipe(env, settings)
    resume = run_id is not None
    if run_id is None:
        run_id = _plan(env, pipe, listings)
    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(handler),
        sleep=_no_sleep,
        config=CollectionConfig(limits=Limits(max_concurrent_listings=lanes)),
        trigger="manual",
    )
    status = asyncio.run(pipe.execute(run_id, "test-collector", resume=resume, collector=collector))
    return run_id, status


def _alike(n: int = 30) -> Site:
    a, b = products(n, "0003803"), products(n, "0003804")
    site = Site({"03001": a[:24] + b[:24], f"03001~{A}": a, f"03001~{B}": b})
    site.totals["03001"] = 2 * n
    site.available["03001"] = 48
    site.brands["03001"] = [{"name": A, "count": n}, {"name": B, "count": n}]
    return site


def _pid(name: str) -> str:
    d = pagination.partition_descriptor(
        store_id="53100503", modality="IN_STORE", listing="03001", filter_name="brandName", value=name
    )
    return pagination.partition_id(d)


def _rows(s: Any, run_id: str, taxonomy: str) -> list[ListingPage]:
    return list(
        s.scalars(
            select(ListingPage)
            .where(ListingPage.run_id == run_id, ListingPage.taxonomy_id == taxonomy)
            .order_by(ListingPage.requested_page, ListingPage.attempt)
        )
    )


# -- M1 ----------------------------------------------------------------------------------------------------


def test_two_brands_alike_in_their_first_64_characters_are_two_readings_through_the_run(
    env: dict[str, Any], settings: Settings
) -> None:
    site = _alike()
    run_id, status = _run(env, settings, site)
    assert status != "interrupted", status
    # Planning and the queue: two tasks, two keys (1.8.0rc5 planned one and dropped the other).
    for name in (A, B):
        assert site.asked.count((f"03001~{name}", 1)) == 1 and site.asked.count((f"03001~{name}", 2)) == 1
    with env["factory"]() as s:
        tasks = [
            t
            for t in s.scalars(select(Task).where(Task.run_id == run_id, Task.kind == "listing_node"))
            if "~" in ((t.cursor or {}).get("node") or {}).get("taxonomy_id", "")
        ]
        assert len(tasks) == 2 and len({t.idem_key for t in tasks}) == 2
        assert {t.state for t in tasks} == {"succeeded"}
        nodes = {
            Node.from_dict(t.cursor["node"]).partition_name: Node.from_dict(t.cursor["node"]) for t in tasks
        }
        assert set(nodes) == {A, B} and nodes[A].taxonomy_id == _pid(A) and nodes[B].taxonomy_id == _pid(B)
        # The page rows: each reading its own, keyed by the full digest, with its full identity.
        for name in (A, B):
            rows = _rows(s, run_id, _pid(name))
            assert [(r.requested_page, r.state, r.verdict) for r in rows] == [
                (1, "completed", "new"),
                (2, "completed", "new"),
            ]
            assert {r.requested_filter["value"] for r in rows} == {name}
            assert {len(r.partition_key) for r in rows} == {64}
            assert {tuple(r.binding["stated"]["brandName"]) for r in rows} == {(name,)}
        upcs = list(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))
        assert len(upcs) == 60 and len(set(upcs)) == 60
        # The export: both readings, by their exact names and identities; the listing is complete.
        report = reconciliation.reconciliation(s, run_id)
        lines = {x["listing_id"]: x for x in report["listings"]}
        for name in (A, B):
            line = lines[_pid(name)]
            assert line["sub_category"] == name and json.loads(line["partition_identity"])["value"] == name
            assert line["status"] == "DONE" and line["unique_identities"] == 30
        assert lines["03001"]["status"] == "DONE"


def _die(env: dict[str, Any], run_id: str, listing: str, page: int) -> None:
    root = Path(__file__).resolve().parents[2]
    args = {
        "config": str(CONFIG),
        "db": env["engine"].url.render_as_string(hide_password=False),
        "store": STORE_KEY,
        "data": str(env["tmp"] / "data"),
        "run": run_id,
        "moment": "request",
        "listing": listing,
        "page": page,
        "listings_n": {
            "03001": [30, "0003803"],
            f"03001~{A}": [30, "0003803"],
            f"03001~{B}": [30, "0003804"],
        },
        "totals": {"03001": 60},
        "available": {"03001": 48},
        "brands": {"03001": [{"name": A, "count": 30}, {"name": B, "count": 30}]},
    }
    p = subprocess.run(
        [sys.executable, "-m", "tests.listing_site", json.dumps(args)],
        cwd=root,
        env=dict(os.environ),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    assert p.returncode == 137, (p.returncode, p.stdout[-2000:], p.stderr[-2000:])


def test_a_worker_killed_inside_one_of_two_alike_brands_resumes_that_brand_alone(
    env: dict[str, Any], settings: Settings
) -> None:
    pipe = _pipe(env, settings)
    run_id = _plan(env, pipe, ("03001",))
    _die(env, run_id, f"03001~{B}", 2)  # dies with B's page 2 out
    with env["factory"]() as s:
        done = {
            (r.taxonomy_id, r.requested_page)
            for r in s.scalars(select(ListingPage))
            if r.state == "completed"
        }
    # Serial order: the listing's page 1, A's two pages, B's page 1; B's page 2 was out.
    assert done == {("03001", 1), (_pid(A), 1), (_pid(A), 2), (_pid(B), 1)}
    site = _alike()
    run_id, status = _run(env, settings, site, run_id=run_id)
    assert status != "interrupted", status
    assert site.asked == [(f"03001~{B}", 2)]  # that page alone, once
    with env["factory"]() as s:
        for name in (A, B):
            assert [
                (r.requested_page, r.state) for r in _rows(s, run_id, _pid(name)) if r.state == "completed"
            ] == [
                (1, "completed"),
                (2, "completed"),
            ]
        upcs = list(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))
        assert len(upcs) == 60 and len(set(upcs)) == 60


def test_a_brand_reading_planned_before_1_9_is_never_resumed(env: dict[str, Any], settings: Settings) -> None:
    pipe = _pipe(env, settings)
    run_id = _plan(env, pipe, ("03001",))
    with env["factory"]() as s:
        parent = s.scalar(select(Task).where(Task.run_id == run_id, Task.kind == "listing_node"))
        assert parent is not None
        legacy = Node.from_dict(parent.cursor["node"])
        legacy = Node(
            legacy.row_index,
            legacy.category,
            legacy.category_source_id,
            legacy.sub_category,
            f"03001~{A}"[:64],  # the identity of 1.8.0rc5
            f"{legacy.url}?brandName=x",
            kind="partition",
            parent="03001",
            partition_name=A,
            partition_count=30,
        )
        queue.enqueue(
            s,
            run_id,
            "listing_node",
            f"{parent.idem_key}/{legacy.taxonomy_id}",
            priority=parent.priority,
            category_source_id=legacy.category_source_id,
            taxonomy_id=legacy.taxonomy_id,
            cursor={"node": legacy.as_dict(), "steps_done": 0, "seen": [], "status": "IN_PROGRESS"},
        )
        parent.state = "succeeded"  # as if the parent had partitioned in 1.8.0rc5
        s.commit()
    site = _alike()
    run_id, status = _run(env, settings, site, run_id=run_id)
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "ABNORMAL_RESULT", (status, run and run.stop_detail)
        assert "before 1.9.0" in (run.stop_detail or "")
    assert not any("~" in k for k, _ in site.asked)  # nothing of the legacy reading was asked for


# -- M2 ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("fault", ["unfiltered", "other_brand", "no_filter_state"])
def test_a_brand_reading_answered_with_another_filter_never_counts_and_stays_incomplete(
    env: dict[str, Any], settings: Settings, fault: str
) -> None:
    site = _alike()
    site.on(f"03001~{B}", 1, fault)
    run_id, _ = _run(env, settings, site)
    with env["factory"]() as s:
        rows = _rows(s, run_id, _pid(B))
        verdict = "unbound" if fault == "no_filter_state" else "wrong_filter"
        assert [(r.requested_page, r.state, r.verdict) for r in rows] == [(1, "refused", verdict)]
        assert site.asked.count((f"03001~{B}", 1)) == 1  # not asked again: it would not prove more
        report = reconciliation.reconciliation(s, run_id)
        lines = {x["listing_id"]: x for x in report["listings"]}
        assert lines[_pid(B)]["status"] == "INCOMPLETE" and lines[_pid(B)]["pages_filter_refused"] == 1
        assert lines["03001"]["status"] != "DONE"  # the brands no longer cover the listing's total
        assert lines[_pid(A)]["status"] == "DONE"


@pytest.mark.parametrize("fault", ["loading", "stale_search"])
def test_a_brand_page_whose_search_was_not_finished_is_asked_again(
    env: dict[str, Any], settings: Settings, fault: str
) -> None:
    site = _alike()
    site.on(f"03001~{B}", 2, fault)
    run_id, status = _run(env, settings, site)
    assert status != "interrupted", status
    with env["factory"]() as s:
        rows = _rows(s, run_id, _pid(B))
        assert [(r.requested_page, r.state, r.verdict) for r in rows] == [
            (1, "completed", "new"),
            (2, "refused", "unbound"),
            (2, "completed", "new"),
        ]
        report = reconciliation.reconciliation(s, run_id)
        lines = {x["listing_id"]: x for x in report["listings"]}
        assert lines["03001"]["status"] == "DONE"


# -- M8: lanes ---------------------------------------------------------------------------------------------


def test_two_lanes_read_two_brands_at_once_and_never_one_task_twice(
    env: dict[str, Any], settings: Settings
) -> None:
    slow = Slow(_alike())
    run_id, status = _run(env, settings, slow, lanes=2)
    assert status != "interrupted", status
    assert slow.max_inflight == 2  # both lanes had a request out at the same moment, never more
    asked = slow.site.asked
    assert sorted(asked) == sorted(set(asked))  # no page asked twice
    with env["factory"]() as s:
        upcs = list(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))
        assert len(upcs) == 60 and len(set(upcs)) == 60
        for name in (A, B):
            assert [r.state for r in _rows(s, run_id, _pid(name))] == ["completed", "completed"]


class Uneven(Slow):
    """Brand A's pages answer slowly, everything else at once: the fast lane finishes pages, and saves the
    session's page rows, while the slow lane's request is still out (stage S5b, 2026-11-09: 6 of 17 page rows
    of the two-lane run 01M70CD8PJQS3QDMWR5AXPS39P were written while in flight, without their stored page,
    and G13 rejected the run)."""

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        slow = "Chicken" in json.loads(request.content).get("url", "")
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(0.4 if slow else 0.01)
            return self.site(request)
        finally:
            self.inflight -= 1


def test_two_lanes_never_save_a_page_whose_answer_has_not_arrived(
    env: dict[str, Any], settings: Settings
) -> None:
    uneven = Uneven(_alike())
    run_id, status = _run(env, settings, uneven, lanes=2)
    assert status != "interrupted", status
    assert uneven.max_inflight == 2
    with env["factory"]() as s:
        rows = list(s.scalars(select(PageFetch).where(PageFetch.run_id == run_id)))
        unsaved = [(r.url, r.http_status, r.duration_ms) for r in rows if r.dom_artifact_id is None]
        assert not unsaved, unsaved  # every page row has its stored page, status and duration
        run = s.get(Run, run_id)
        assert run is not None and run.counts["gates"]["G13"] == "PASS", run.counts["gates"]
        upcs = list(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))
        assert len(upcs) == 60 and len(set(upcs)) == 60


def test_one_listing_at_a_time_is_the_default_and_keeps_one_request_in_flight(
    env: dict[str, Any], settings: Settings
) -> None:
    slow = Slow(_alike())
    _run(env, settings, slow)
    assert slow.max_inflight == 1


def test_a_lane_that_meets_the_ceiling_halts_the_other_and_a_resume_asks_no_page_twice(
    env: dict[str, Any], settings: Settings
) -> None:
    with env["factory"]() as s:
        oxylabs.set_ceiling(s, submissions=4, usd=10, actor="test", reason="test")  # robots + 3 pages
        s.commit()
    slow = Slow(_alike())
    run_id, status = _run(env, settings, slow, lanes=2)
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "SPENDING_CEILING"
        assert s.scalar(select(func.count()).select_from(ProviderUsage)) <= 4
        assert s.scalar(select(Event).where(Event.run_id == run_id, Event.code == "RUN_LIMIT_REACHED"))
        leased = s.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.run_id == run_id, Task.state.in_(("leased", "running")))
        )
        assert leased == 0  # every lane handed its task back
        oxylabs.set_ceiling(s, submissions=400, usd=10, actor="test", reason="test")
        s.commit()
    with env["factory"]() as s:
        held = {
            (
                "03001~" + r.requested_filter["value"] if r.requested_filter else r.taxonomy_id,
                r.requested_page,
            )
            for r in s.scalars(select(ListingPage).where(ListingPage.run_id == run_id))
            if r.state == "completed"
        }
    assert held  # some pages were completed before the stop
    first = len(slow.site.asked)
    _, status = _run(env, settings, slow, run_id=run_id, lanes=2)
    assert status != "interrupted", status
    with env["factory"]() as s:
        upcs = list(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))
        assert len(upcs) == 60 and len(set(upcs)) == 60
        completed = [
            (r.taxonomy_id, r.requested_page)
            for r in s.scalars(select(ListingPage).where(ListingPage.run_id == run_id))
            if r.state == "completed"
        ]
        assert len(completed) == len(set(completed)) == 5  # 03001 p1 + two pages of each brand
    again = slow.site.asked[first:]
    assert not set(again) & held  # a completed page is never asked for again
    assert len(again) == len(set(again))


def test_a_provider_failure_that_pauses_the_run_is_not_reported_as_a_limit(
    env: dict[str, Any], settings: Settings
) -> None:
    """T07 (review of 1.8.0rc5): the pause after pages kept failing at the provider was recorded as
    RUN_LIMIT_REACHED."""
    site = Site({"03001": products(60)})
    site.on("03001", 2, *(["fail"] * 12))
    run_id, status = _run(env, settings, site)
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "PROVIDER_ERROR"
        codes = set(s.scalars(select(Event.code).where(Event.run_id == run_id)))
        assert "RUN_PAUSED_ON_FAILURE" in codes and "RUN_LIMIT_REACHED" not in codes
