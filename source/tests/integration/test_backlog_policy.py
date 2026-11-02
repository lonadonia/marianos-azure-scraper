"""The continuation/backlog policy of scheduled runs (release 1.5.0), on a throwaway PostgreSQL: a run the
next occurrence closes unfinished (``SUPERSEDED``) hands the listings it did not read to its end to the next
scheduled run, which reads them first. SYNTHETIC history (coverage rows written by the test); no provider."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from marianos_headless.collection import control
from marianos_headless.collection.config import CollectionConfig, Schedule
from marianos_headless.collection.limits import StopCode, stop_text
from marianos_headless.collection.nodes import Node
from marianos_headless.core.settings import PrivateLabelConfig, Settings, StoreConfig
from marianos_headless.db.models import Event, NodeCoverage, Run, Task
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.pipeline import Pipeline
from tests.integration.helpers import new_run, seed

pytestmark = pytest.mark.postgres

MON = datetime(2026, 11, 2, 13, tzinfo=UTC)
THU = datetime(2026, 11, 5, 13, tzinfo=UTC)


def _finished_run(factory, store, started: datetime, read: list[Node], status: str = "DONE") -> str:  # type: ignore[no-untyped-def]
    run = new_run(factory, store, status="rejected")
    with factory() as s:
        row = s.get(Run, run.id)
        assert row is not None
        row.started_at = started
        for n in read:
            s.add(
                NodeCoverage(
                    run_id=run.id,
                    category_source_id=n.category_source_id,
                    taxonomy_id=n.taxonomy_id,
                    status=status,
                )
            )
        s.commit()
    return run.id


def test_the_next_scheduled_run_reads_first_what_the_superseded_run_did_not_finish(
    migrated_engine: Engine,
    settings: Settings,
    dev_store: StoreConfig,
    private_label: PrivateLabelConfig,
    tmp_path: Path,
) -> None:
    factory, store = seed(migrated_engine)
    pipe = Pipeline(migrated_engine, LocalStorageAdapter(tmp_path), settings, dev_store, private_label)
    cfg = CollectionConfig(categories=[7], schedule=Schedule(backlog_first=True))
    with factory() as s:
        nodes, _ = control.plan(s, cfg)
    assert len(nodes) >= 6
    # Monday's run read every listing of the row to its end; Thursday's run was closed unfinished
    # (SUPERSEDED) after the first half; one listing was only ever read in part.
    half = len(nodes) // 2
    _finished_run(factory, store, MON, nodes[:-1])
    _finished_run(factory, store, MON, nodes[-1:], status="INCOMPLETE")
    _finished_run(factory, store, THU, nodes[:half])
    with factory() as s:
        last = control.last_complete_reads(s, store.id)
        assert last[(nodes[0].category_source_id, nodes[0].taxonomy_id)] == THU
        assert last[(nodes[half].category_source_id, nodes[half].taxonomy_id)] == MON
        assert (nodes[-1].category_source_id, nodes[-1].taxonomy_id) not in last
        run_id = control.create_run(
            s, pipe=pipe, store=dev_store, cfg=cfg, trigger="schedule", started_by="schedule", pilot=False
        )
        s.commit()
    with factory() as s:
        run = s.get(Run, run_id)
        assert run is not None
        plan = run.config_snapshot["plan"]
        order = [n["taxonomy_id"] for n in plan["nodes"]]
        expected = [nodes[-1], *nodes[half:-1], *nodes[:half]]
        assert order == [n.taxonomy_id for n in expected]
        assert plan["order"] == {"policy": "backlog_first", "backlog": [nodes[-1].taxonomy_id]}
        ev = s.scalars(select(Event).where(Event.run_id == run_id, Event.code == "BACKLOG_FIRST")).one()
        assert ev.data == {"backlog": [nodes[-1].taxonomy_id], "order": [n.taxonomy_id for n in expected]}
        # The listing tasks are queued in that order (the collector reads them by ``idem_key``).
        keys = list(
            s.scalars(
                select(Task.idem_key)
                .where(Task.run_id == run_id, Task.kind == "listing_node")
                .order_by(Task.idem_key)
            )
        )
        assert [k.split("/node/", 1)[1].split("-", 1)[1] for k in keys] == [n.taxonomy_id for n in expected]


def test_a_manual_run_keeps_the_csv_order_and_the_stop_text_names_the_backlog(
    migrated_engine: Engine,
    settings: Settings,
    dev_store: StoreConfig,
    private_label: PrivateLabelConfig,
    tmp_path: Path,
) -> None:
    factory, store = seed(migrated_engine)
    pipe = Pipeline(migrated_engine, LocalStorageAdapter(tmp_path), settings, dev_store, private_label)
    cfg = CollectionConfig(categories=[7])
    with factory() as s:
        nodes, _ = control.plan(s, cfg)
    _finished_run(factory, store, THU, nodes[:2])
    with factory() as s:
        run_id = control.create_run(
            s, pipe=pipe, store=dev_store, cfg=cfg, trigger="manual", started_by="test", pilot=True
        )
        s.commit()
        run = s.get(Run, run_id)
        assert run is not None
        assert [n["taxonomy_id"] for n in run.config_snapshot["plan"]["nodes"]] == [
            n.taxonomy_id for n in nodes
        ]
        assert run.config_snapshot["plan"]["order"] == {"policy": "csv"}
    text = stop_text(StopCode.SUPERSEDED.value) or ""
    assert "never published" in text and "read first" in text
