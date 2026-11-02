"""The page loop of a listing (release 1.8.0), against the SYNTHETIC ``/pl/`` pages of
``tests/listing_site.py``.

The client's finding: exported data stopped at the first page of each category. Each test states what a run
must do with a listing of more than one page, and what it must never do: count a page that failed or repeats,
continue with a wrong store, or ask again for a page it already holds."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from marianos_headless.acquisition import oxylabs
from marianos_headless.collection import pagination, reconciliation
from marianos_headless.collection.config import CollectionConfig, Limits
from marianos_headless.collection.oxylabs_live import OxylabsCollector
from marianos_headless.collection.recovery import INTERRUPTED
from marianos_headless.core.settings import (
    AcquisitionSettings,
    BrowserProvider,
    PrivateLabelConfig,
    Settings,
    StoreConfig,
)
from marianos_headless.db.models import (
    Artifact,
    CategorySource,
    CollectionSegment,
    Event,
    ListingPage,
    NodeCoverage,
    PageFetch,
    ProductObservation,
    ProviderUsage,
    RecordRow,
    Run,
    Task,
)
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests.integration.helpers import CONFIG, STORE_KEY, seed
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


def _pipe(env: dict[str, Any], settings: Settings) -> Pipeline:
    acq = AcquisitionSettings(browser_provider=BrowserProvider.OXYLABS)
    return Pipeline(
        env["engine"],
        env["storage"],
        Settings(acquisition=acq, records=settings.records, attestation=settings.attestation),
        env["store"],
        env["private_label"],
    )


def _plan(env: dict[str, Any], pipe: Pipeline, listings: tuple[str, ...]) -> str:
    with env["factory"]() as s:
        ids = {c.csv_row_index: c.id for c in s.scalars(select(CategorySource))}
    nodes = plan_nodes(ids, listings)
    with env["factory"]() as s:
        run_id = pipe.create_live_run(
            s,
            nodes,
            trigger="console",
            snapshot={
                "plan": {"nodes": [n.as_dict() for n in nodes], "skipped": []},
                "started_by": "test",
                "provider": "oxylabs",
            },
        )
        s.commit()
    return run_id


def _run(
    env: dict[str, Any],
    settings: Settings,
    site: Site,
    *,
    listings: tuple[str, ...] = ("03001",),
    run_id: str | None = None,
    limits: Limits | None = None,
) -> tuple[str, str]:
    pipe = _pipe(env, settings)
    resume = run_id is not None
    if run_id is None:
        run_id = _plan(env, pipe, listings)
    collector = OxylabsCollector(
        pipe,
        run_id,
        api_key=SecretStr(KEY),
        transport=httpx.MockTransport(site),
        sleep=_no_sleep,
        config=CollectionConfig(limits=limits or Limits()),
        trigger="manual",
    )
    status = asyncio.run(pipe.execute(run_id, "test-collector", resume=resume, collector=collector))
    return run_id, status


def _rows(s: Session, run_id: str, listing: str | None = None) -> list[ListingPage]:
    q = select(ListingPage).where(ListingPage.run_id == run_id)
    if listing is not None:
        q = q.where(ListingPage.taxonomy_id == listing)
    return list(
        s.scalars(q.order_by(ListingPage.taxonomy_id, ListingPage.requested_page, ListingPage.attempt))
    )


def _pages(s: Session, run_id: str, listing: str = "03001") -> list[tuple[int, str, str]]:
    return [(r.requested_page, r.state, r.verdict) for r in _rows(s, run_id, listing)]


def _upcs(s: Session, run_id: str) -> list[str]:
    return list(s.scalars(select(RecordRow.upc).where(RecordRow.run_id == run_id)))


def _coverage(s: Session, run_id: str, listing: str = "03001") -> NodeCoverage | None:
    return s.scalar(
        select(NodeCoverage).where(NodeCoverage.run_id == run_id, NodeCoverage.taxonomy_id == listing)
    )


def _complete(n: int = 60) -> Site:
    return Site({"03001": products(n)})


# -- a whole listing --------------------------------------------------------------------------------------


def test_a_listing_of_three_pages_is_read_to_its_end_and_exported_whole(
    env: dict[str, Any], settings: Settings
) -> None:
    site = _complete(60)
    run_id, status = _run(env, settings, site)
    assert site.asked == [("03001", 1), ("03001", 2), ("03001", 3)]
    with env["factory"]() as s:
        assert _pages(s, run_id) == [
            (1, "completed", "new"),
            (2, "completed", "new"),
            (3, "completed", "new"),
        ]
        rows = _rows(s, run_id)
        assert [r.requested_offset for r in rows] == [0, 24, 48]
        assert [r.returned_page for r in rows] == [1, 2, 3]
        assert [len(r.identities) for r in rows] == [24, 24, 12]
        assert [r.new_count for r in rows] == [24, 24, 12]
        assert all(r.response_sha256 and r.provider_request_id and r.store_check == "PASS" for r in rows)
        upcs = _upcs(s, run_id)
        assert len(upcs) == 60 and len(set(upcs)) == 60
        cov = _coverage(s, run_id)
        assert cov is not None and (cov.status, cov.total_count) == ("DONE", 60)
        run = s.get(Run, run_id)
        assert run is not None and run.counts["gates"]["G1"] == "PASS"
    assert status != "interrupted", status


def test_the_export_reconciles_the_listing_and_every_csv_row(env: dict[str, Any], settings: Settings) -> None:
    site = Site({"03001": products(60), "03002": products(30, "0003805")})
    site.on("03002", 2, "repeat")
    run_id, _ = _run(env, settings, site, listings=("03001", "03002"))
    with env["factory"]() as s:
        report = reconciliation.reconciliation(s, run_id)
        files = reconciliation.coverage_files(s, run_id)
    lines = {x["listing_id"]: x for x in report["listings"]}
    whole = lines["03001"]
    assert (
        whole["reported_total"],
        whole["pages_reachable"],
        whole["pages_attempted"],
        whole["pages_completed"],
    ) == (
        60,
        3,
        3,
        3,
    )
    assert (whole["unique_identities"], whole["unresolved_gap"], whole["status"]) == (60, 0, "DONE")
    assert whole["completion_reason"] == "60 distinct products of 60 reported, on 3 page(s)"
    assert (whole["location_id"], whole["fulfillment"], whole["route"]) == ("53100503", "IN_STORE", "listing")
    short = lines["03002"]
    assert (short["pages_attempted"], short["pages_completed"], short["responses_not_counted"]) == (2, 1, 1)
    assert (short["unique_identities"], short["unresolved_gap"], short["status"]) == (24, 6, "INCOMPLETE")
    assert pagination.GAP in short["completion_reason"]
    rows = {r["csv_row"]: r for r in report["rows"]}
    assert len(rows) == 28 and rows[12]["status"] == "INCOMPLETE"  # one listing of the row is short
    assert rows[12]["listings_complete"] == 1 and rows[12]["listings_incomplete"] == 1
    assert rows[1]["status"] == "NOT_ATTEMPTED" and report["complete_rows"] == 0
    assert files["coverage_reconciliation.csv"].startswith(b"csv_row,category,sub_category,listing_id")
    assert files["listing_pages.csv"].count(b"\r\n") == 1 + 3 + 2


def test_every_page_asks_for_the_page_under_one_ordering(env: dict[str, Any], settings: Settings) -> None:
    site = _complete(30)
    _run(env, settings, site)
    urls = [r["url"] for r in site.requests if "/pl/" in r["url"]]
    # The first page as the store check brought it, then page=2; the fake refuses pzn=relevance.
    assert urls == [
        "https://www.marianos.com/pl/listing-03001/03001",
        "https://www.marianos.com/pl/listing-03001/03001?page=2",
    ]


# -- a page that does not count ---------------------------------------------------------------------------


def test_a_failed_page_2_leaves_the_listing_unfinished_and_a_resume_continues_at_it(
    env: dict[str, Any], settings: Settings
) -> None:
    site = _complete(60)
    site.on("03001", 2, *["fail"] * 9)  # three task attempts of three submissions each
    run_id, status = _run(env, settings, site)
    assert status == "interrupted"
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "PROVIDER_ERROR"
        assert _pages(s, run_id) == [(1, "completed", "new"), *[(2, "failed", "failed")] * 3]
        assert len(_upcs(s, run_id)) == 24
        cov = _coverage(s, run_id)
        assert cov is None or cov.status != "DONE"
    site.asked.clear()
    run_id, status = _run(env, settings, site, run_id=run_id)
    assert site.asked == [("03001", 2), ("03001", 3)]  # never page 1 again
    with env["factory"]() as s:
        upcs = _upcs(s, run_id)
        assert len(upcs) == 60 and len(set(upcs)) == 60
        assert _pages(s, run_id)[-2:] == [(2, "completed", "new"), (3, "completed", "new")]
        cov = _coverage(s, run_id)
        assert cov is not None and (cov.status, cov.total_count) == ("DONE", 60)


@pytest.mark.parametrize(("what", "verdict"), [("repeat", "repeated"), ("reorder", "reordered_repeat")])
def test_a_page_that_repeats_earlier_products_stops_the_listing_as_incomplete(
    env: dict[str, Any], settings: Settings, what: str, verdict: str
) -> None:
    site = _complete(60)
    site.on("03001", 2, what)
    run_id, _ = _run(env, settings, site)
    assert site.asked == [("03001", 1), ("03001", 2)]  # no further page after a repeat
    with env["factory"]() as s:
        assert _pages(s, run_id) == [(1, "completed", "new"), (2, "stopped", verdict)]
        rows = _rows(s, run_id)
        assert rows[1].duplicates == 24 and rows[1].new_count == 0
        assert len(_upcs(s, run_id)) == 24
        cov = _coverage(s, run_id)
        assert cov is not None and cov.status == "INCOMPLETE"
        assert pagination.GAP in cov.partition["reason"]
        assert s.get(Run, run_id).counts["gates"]["G3"] == "FAIL"  # type: ignore[union-attr]


def test_a_page_that_overlaps_counts_its_new_products_and_the_listing_stays_short(
    env: dict[str, Any], settings: Settings
) -> None:
    site = _complete(60)
    site.on("03001", 2, "overlap")
    run_id, _ = _run(env, settings, site)
    with env["factory"]() as s:
        assert _pages(s, run_id)[:2] == [(1, "completed", "new"), (2, "completed", "partial_overlap")]
        assert _rows(s, run_id)[1].duplicates == 12
        cov = _coverage(s, run_id)
        assert cov is not None and cov.status == "INCOMPLETE" and "of 60 reported" in cov.partition["reason"]


@pytest.mark.parametrize("what", ["wrong_store", "wrong_fulfillment"])
def test_a_page_of_another_store_or_fulfillment_is_refused_and_stops_the_run(
    env: dict[str, Any], settings: Settings, what: str
) -> None:
    site = _complete(60)
    site.on("03001", 2, what)
    run_id, status = _run(env, settings, site)
    assert status == "rejected"
    assert site.asked == [("03001", 1), ("03001", 2)]
    with env["factory"]() as s:
        run = s.get(Run, run_id)
        assert run is not None and run.stop_code == "STORE_NOT_VERIFIED"
        assert _pages(s, run_id) == [(1, "completed", "new"), (2, "refused", "wrong_context")]
        assert len(_upcs(s, run_id)) == 24  # nothing of the wrong page


def test_a_store_mismatch_on_the_first_page_records_nothing(env: dict[str, Any], settings: Settings) -> None:
    site = _complete(30)
    site.on("03001", 1, "wrong_store")
    run_id, status = _run(env, settings, site)
    assert status == "rejected"
    with env["factory"]() as s:
        assert s.get(Run, run_id).stop_code == "STORE_NOT_VERIFIED"  # type: ignore[union-attr]
        assert _upcs(s, run_id) == []


@pytest.mark.parametrize(
    ("what", "verdict"),
    [("wrong_page", "wrong_page"), ("wrong_listing", "wrong_listing")],
)
def test_a_page_that_is_not_the_one_asked_for_never_counts(
    env: dict[str, Any], settings: Settings, what: str, verdict: str
) -> None:
    site = _complete(60)
    site.on("03001", 2, what)
    run_id, _ = _run(env, settings, site)
    with env["factory"]() as s:
        assert _pages(s, run_id) == [(1, "completed", "new"), (2, "refused", verdict)]
        assert len(_upcs(s, run_id)) == 24
        cov = _coverage(s, run_id)
        assert cov is not None and cov.status == "INCOMPLETE"


@pytest.mark.parametrize(
    ("what", "verdict"), [("empty", "empty"), ("no_metadata", "malformed"), ("no_cards", "malformed")]
)
def test_an_empty_or_malformed_page_is_asked_again_within_its_bounds(
    env: dict[str, Any], settings: Settings, what: str, verdict: str
) -> None:
    """Probe L9: a later page without rendering holds its products in the page state and shows no cards."""
    site = _complete(60)
    site.on("03001", 2, what)
    run_id, _ = _run(env, settings, site)
    assert site.asked.count(("03001", 2)) == 2
    with env["factory"]() as s:
        assert _pages(s, run_id) == [
            (1, "completed", "new"),
            (2, "refused", verdict),
            (2, "completed", "new"),
            (3, "completed", "new"),
        ]
        assert len(_upcs(s, run_id)) == 60


def test_a_blocked_page_stops_the_run_without_retrying_and_is_not_counted(
    env: dict[str, Any], settings: Settings
) -> None:
    site = _complete(60)
    site.on("03001", 2, "blocked")
    run_id, status = _run(env, settings, site)
    assert status == "rejected"
    assert site.asked == [("03001", 1), ("03001", 2)]
    with env["factory"]() as s:
        assert s.get(Run, run_id).stop_code == "SITE_REFUSAL"  # type: ignore[union-attr]
        assert _pages(s, run_id) == [(1, "completed", "new"), (2, "refused", "blocked")]


def test_a_total_that_changes_during_the_read_is_kept_and_the_listing_stays_short(
    env: dict[str, Any], settings: Settings
) -> None:
    site = _complete(60)
    site.on("03001", 2, "total_up")
    run_id, _ = _run(env, settings, site)
    with env["factory"]() as s:
        assert [r.total for r in _rows(s, run_id)] == [60, 63, 63]
        cov = _coverage(s, run_id)
        assert cov is not None and cov.status == "INCOMPLETE"
        assert "changed during the read: [60, 63]" in cov.partition["reason"]


def test_a_leaf_above_the_window_is_read_to_the_window_and_stays_incomplete(
    env: dict[str, Any], settings: Settings
) -> None:
    site = Site({"03001": products(60)})
    site.totals["03001"] = 60
    site.available["03001"] = 48
    run_id, _ = _run(env, settings, site)
    assert site.asked == [("03001", 1), ("03001", 2)]
    with env["factory"]() as s:
        cov = _coverage(s, run_id)
        assert cov is not None and cov.status == "INCOMPLETE"
        assert "accessible pages exhausted; coverage incomplete" in cov.partition["reason"]
        assert "48 of 60 results (availableCount)" in cov.partition["reason"]


def test_a_listing_above_the_window_is_read_through_the_child_listings_its_page_names(
    env: dict[str, Any], settings: Settings
) -> None:
    a, b = products(30, "0003801"), products(30, "0003802")
    site = Site({"03001": a[:24] + b[:24], "0300100001": a, "0300100002": b})
    site.totals["03001"] = 60
    site.available["03001"] = 48
    site.children["03001"] = [
        {"id": "0300100001", "name": "A", "slug": "a", "count": 30},
        {"id": "0300100002", "name": "B", "slug": "b", "count": 30},
    ]
    run_id, _ = _run(env, settings, site)
    assert ("03001", 2) not in site.asked  # the rest of the parent is its children
    assert site.asked.count(("0300100001", 2)) == 1 and site.asked.count(("0300100002", 2)) == 1
    with env["factory"]() as s:
        assert len(set(_upcs(s, run_id))) == 60
        assert _pages(s, run_id, "0300100001") == [(1, "completed", "new"), (2, "completed", "new")]
        cov = _coverage(s, run_id, "0300100001")
        assert cov is not None and (cov.status, cov.total_count) == ("DONE", 30)


def test_a_leaf_above_the_window_is_read_through_the_sites_own_brand_filter(
    env: dict[str, Any], settings: Settings
) -> None:
    a, b = products(30, "0003803"), products(30, "0003804")
    site = Site({"03001": a[:24] + b[:24], "03001~Acme Foods": a, "03001~Bravo": b})
    site.totals["03001"] = 60
    site.available["03001"] = 48
    site.brands["03001"] = [{"name": "Acme Foods", "count": 30}, {"name": "Bravo", "count": 30}]
    run_id, _ = _run(env, settings, site)
    assert ("03001~Acme Foods", 2) in site.asked and ("03001~Bravo", 2) in site.asked
    urls = {r["url"] for r in site.requests}
    assert "https://www.marianos.com/pl/listing-03001/03001?brandName=Acme%20Foods&page=2" in urls
    with env["factory"]() as s:
        assert len(set(_upcs(s, run_id))) == 60
        assert _pages(s, run_id, "03001~Acme Foods") == [(1, "completed", "new"), (2, "completed", "new")]


def test_a_product_limit_inside_a_page_leaves_the_page_unfinished(
    env: dict[str, Any], settings: Settings
) -> None:
    site = _complete(60)
    run_id, status = _run(env, settings, site, limits=Limits(max_products_per_run=30))
    assert status == "interrupted"
    with env["factory"]() as s:
        assert _pages(s, run_id)[-1][:2] == (2, "capped")
        assert not any(r.state == "completed" and r.requested_page == 2 for r in _rows(s, run_id))
    site.asked.clear()
    _run(env, settings, site, run_id=run_id, limits=Limits(max_products_per_run=100))
    assert site.asked == [("03001", 2), ("03001", 3)]
    with env["factory"]() as s:
        upcs = _upcs(s, run_id)
        assert len(upcs) == 60 and len(set(upcs)) == 60


def test_a_page_of_a_declared_limit_says_so(env: dict[str, Any], settings: Settings) -> None:
    site = _complete(60)
    run_id, _ = _run(env, settings, site, limits=Limits(max_pages_per_listing=2))
    assert site.asked == [("03001", 1), ("03001", 2)]
    with env["factory"]() as s:
        cov = _coverage(s, run_id)
        assert cov is not None and cov.status == "INCOMPLETE"
        assert "declared limit of 2 page(s)" in cov.partition["reason"]


# -- a worker that dies -----------------------------------------------------------------------------------


def _die(env: dict[str, Any], run_id: str, moment: str, listing: str, page: int, n: int) -> int:
    root = Path(__file__).resolve().parents[2]
    args = {
        "config": str(CONFIG),
        "db": env["engine"].url.render_as_string(hide_password=False),
        "store": STORE_KEY,
        "data": str(env["tmp"] / "data"),
        "run": run_id,
        "moment": moment,
        "listing": listing,
        "page": page,
        "listings_n": {listing: n},
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
    return p.returncode


def test_a_worker_killed_while_page_2_is_out_resumes_at_page_2_and_its_request_stays_counted(
    env: dict[str, Any], settings: Settings
) -> None:
    pipe = _pipe(env, settings)
    run_id = _plan(env, pipe, ("03001",))
    _die(env, run_id, "request", "03001", 2, 60)
    with env["factory"]() as s:
        assert _pages(s, run_id) == [(1, "completed", "new")]  # the page 2 request left no row and no product
        assert len(_upcs(s, run_id)) == 24
        reserved = list(s.scalars(select(ProviderUsage).where(ProviderUsage.state == "reserved")))
        assert len(reserved) == 1 and "page=2" in reserved[0].target
        seg = s.scalar(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        assert seg is not None and seg.ended_at is None and seg.end_state is None
    site = _complete(60)
    run_id, _ = _run(env, settings, site, run_id=run_id)
    assert site.asked == [("03001", 2), ("03001", 3)]
    with env["factory"]() as s:
        upcs = _upcs(s, run_id)
        assert len(upcs) == 60 and len(set(upcs)) == 60
        assert [(r.requested_page, r.attempt) for r in _rows(s, run_id)] == [(1, 1), (2, 1), (3, 1)]
        kept = list(s.scalars(select(ProviderUsage).where(ProviderUsage.outcome == INTERRUPTED)))
        assert (
            len(kept) == 1 and kept[0].cost_source == "unknown" and kept[0].cost_usd > 0
        )  # possibly billed, once
        assert (
            s.scalar(select(func.count()).select_from(ProviderUsage).where(ProviderUsage.state == "reserved"))
            == 0
        )
        segs = {
            g.end_state
            for g in s.scalars(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        }
        assert segs == {"abandoned", "ended"}
        assert s.scalar(select(Event).where(Event.run_id == run_id, Event.code == "SEGMENT_ABANDONED"))


def test_a_worker_killed_after_a_pages_commit_never_asks_for_that_page_again(
    env: dict[str, Any], settings: Settings
) -> None:
    """The page's row and its products are one transaction; the task's cursor is one page behind the table."""
    pipe = _pipe(env, settings)
    run_id = _plan(env, pipe, ("03001",))
    _die(env, run_id, "checkpoint", "03001", 2, 60)
    with env["factory"]() as s:
        assert _pages(s, run_id) == [(1, "completed", "new"), (2, "completed", "new")]
        assert len(_upcs(s, run_id)) == 48
        task = s.scalar(select(Task).where(Task.run_id == run_id, Task.kind == "listing_node"))
        assert task is not None and (task.cursor or {}).get("steps_done") == 1  # behind the table
    site = _complete(60)
    run_id, _ = _run(env, settings, site, run_id=run_id)
    assert site.asked == [("03001", 3)]
    with env["factory"]() as s:
        upcs = _upcs(s, run_id)
        assert len(upcs) == 60 and len(set(upcs)) == 60
        rows = _rows(s, run_id)
        assert [(r.requested_page, r.state) for r in rows] == [
            (1, "completed"),
            (2, "completed"),
            (3, "completed"),
        ]
        cov = _coverage(s, run_id)
        assert cov is not None and (cov.status, cov.total_count) == ("DONE", 60)


def test_a_dead_workers_reservation_at_the_ceiling_cannot_refuse_its_own_recovery(
    env: dict[str, Any], settings: Settings
) -> None:
    """The kill leaves the ledger at its ceiling: the resume closes the segment first, then stops for the
    ceiling, resumably, with the request kept once."""
    pipe = _pipe(env, settings)
    run_id = _plan(env, pipe, ("03001",))
    _die(env, run_id, "request", "03001", 2, 60)
    with env["factory"]() as s:
        used = oxylabs.usage_since(s, None)["submissions"]
        since = datetime(2026, 1, 1, tzinfo=UTC)
        oxylabs.set_ceiling(s, submissions=used, usd=10, actor="test", reason="test", since=since)
        s.commit()
    site = _complete(60)
    _, status = _run(env, settings, site, run_id=run_id)
    assert status == "interrupted" and site.asked == []
    with env["factory"]() as s:
        assert s.get(Run, run_id).stop_code == "SPENDING_CEILING"  # type: ignore[union-attr]
        seg = s.scalar(select(CollectionSegment).where(CollectionSegment.run_id == run_id))
        assert seg is not None and seg.end_state == "abandoned"
        assert (
            s.scalar(select(func.count()).select_from(ProviderUsage).where(ProviderUsage.state == "reserved"))
            == 0
        )


# -- integrity (G13) and pages the provider never brought (release 1.8.0rc5) -------------------------------


def test_a_page_the_provider_never_brought_is_no_integrity_failure(
    env: dict[str, Any], settings: Settings
) -> None:
    """Q2 of 2026-11-02 (1.8.0rc4): page 2 of a listing failed at the provider on every attempt of two task
    attempts, nothing was stored for those fetches, and G13 rejected the run for them although no record
    depends on them. The page itself is read on the resume and the listing completes: G13 passes, and every
    page the run stored is still verified."""
    site = _complete(60)
    site.on("03001", 2, *["fail"] * 9)  # three task attempts of three submissions each
    run_id, status = _run(env, settings, site)
    assert status == "interrupted"
    run_id, status = _run(env, settings, site, run_id=run_id)
    with env["factory"]() as s:
        empty = list(
            s.scalars(
                select(PageFetch).where(PageFetch.run_id == run_id, PageFetch.dom_artifact_id.is_(None))
            )
        )
        assert empty  # the fetches the provider never brought are recorded, without a document
        stored = s.scalar(
            select(func.count())
            .select_from(PageFetch)
            .where(PageFetch.run_id == run_id, PageFetch.dom_artifact_id.is_not(None))
        )
        assert stored and stored >= 3
        cov = _coverage(s, run_id)
        assert cov is not None and (cov.status, cov.total_count) == ("DONE", 60)
        run = s.get(Run, run_id)
        assert run is not None and run.counts["gates"]["G13"] == "PASS", run.counts["gates"]
        assert _pipe(env, settings).integrity(s, run_id) == (True, True, True)


def test_a_missing_or_altered_page_that_the_run_depends_on_still_fails_integrity(
    env: dict[str, Any], settings: Settings
) -> None:
    """The rule is narrow: a fetch without a document is excused only when nothing of the run names it."""
    run_id, _ = _run(env, settings, _complete(60))
    pipe = _pipe(env, settings)
    with env["factory"]() as s:
        assert pipe.integrity(s, run_id)[1] is True
        obs = s.scalars(select(ProductObservation).where(ProductObservation.run_id == run_id)).first()
        assert obs is not None
        pf = s.get(PageFetch, obs.page_fetch_id)
        assert pf is not None and pf.dom_artifact_id is not None
        kept = pf.dom_artifact_id
        pf.dom_artifact_id = None  # a product was read from this page: its document must be there
        s.flush()
        assert pipe.integrity(s, run_id)[1] is False
        pf.dom_artifact_id = kept
        art = s.get(Artifact, kept)
        assert art is not None
        art.sha256 = "0" * 64  # a stored page that no longer matches its hash
        s.flush()
        assert pipe.integrity(s, run_id)[1] is False
        s.rollback()
