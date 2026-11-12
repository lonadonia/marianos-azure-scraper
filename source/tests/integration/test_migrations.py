"""The shipped migrations build exactly the schema the models describe, and the 1.3.0 migration (the provider
spending ledger) and the 1.4.0 migration (record dispositions, membership context, abandoned segments) can be
taken back and applied again on a database holding earlier data."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from marianos_headless.core.timeutil import utcnow
from marianos_headless.db import migrate
from marianos_headless.db.models import Base, CollectionSegment, RecordRow
from tests.integration.helpers import new_run, seed

pytestmark = [pytest.mark.postgres]


def _diff(engine: Engine) -> list[object]:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": True})
        return list(compare_metadata(ctx, Base.metadata))


def test_the_migrations_build_the_models_schema(migrated_engine: Engine) -> None:
    assert migrate.state(migrated_engine) == ("0006", "0006")
    assert _diff(migrated_engine) == []


def test_the_provider_ledger_migration_goes_back_and_forth(migrated_engine: Engine) -> None:
    cfg = migrate.alembic_config()
    with migrated_engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0001")
    assert migrate.current(migrated_engine) == "0001"
    assert "provider_usage" not in inspect(migrated_engine).get_table_names()
    with migrated_engine.begin() as conn:
        conn.execute(text("SELECT count(*) FROM runs"))  # the 1.2.x tables stay
    assert migrate.upgrade(migrated_engine) == ("0001", "0006")
    assert "provider_usage" in inspect(migrated_engine).get_table_names()
    assert _diff(migrated_engine) == []


def test_the_deferred_requests_migration_goes_back_and_forth_and_its_ceiling_is_in_the_table(
    migrated_engine: Engine,
) -> None:
    """0006 (release 1.10.0, C1): the table of requests set aside, whose own constraints refuse more than two
    re-asks; ``listing_pages`` accepts the state of a first page asked again for its filters. Taken back, the
    1.9 schema is as it was, and applied again it matches the models."""
    factory, store = seed(migrated_engine)
    run = new_run(factory, store, status="running")
    insert = (
        "INSERT INTO deferred_requests (id, run_id, category_source_id, csv_row_index, taxonomy_id, "
        "partition_key, requested_page, kind, url, requested_filter, store_context, original_verdict, "
        "original_reason, max_reasks, min_wait_s, reasks_dispatched, not_before, state, outcome, attempts) "
        "SELECT :id, :run, id, 12, '03001', '', :page, 'repeated_page', 'u', '{}', '{}', 'repeated', '', "
        ":cap, 300, :sent, now(), 'waiting', '', '[]' FROM category_sources LIMIT 1"
    )
    with migrated_engine.begin() as conn:
        conn.execute(text(insert), {"id": "d1", "run": run.id, "page": 2, "cap": 2, "sent": 2})
    for bad in ({"cap": 3, "sent": 0}, {"cap": 2, "sent": 3}):
        with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
            conn.execute(text(insert), {"id": "d2", "run": run.id, "page": 3, **bad})
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:  # one record per logical request
        conn.execute(text(insert), {"id": "d3", "run": run.id, "page": 2, "cap": 2, "sent": 0})
    cfg = migrate.alembic_config()
    with migrated_engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0005")
    assert migrate.current(migrated_engine) == "0005"
    assert "deferred_requests" not in inspect(migrated_engine).get_table_names()
    assert migrate.upgrade(migrated_engine) == ("0005", "0006")
    assert _diff(migrated_engine) == []


def test_the_dispositions_migration_keeps_existing_rows(migrated_engine: Engine) -> None:
    """0003 on a 1.3.x database: closed segments become ``ended``, open ones stay open (a later worker
    decides they were abandoned); going back maps the new statuses to ``exported_not_valid``."""
    factory, store = seed(migrated_engine)
    run = new_run(factory, store, status="running")
    cfg = migrate.alembic_config()
    with migrated_engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0002")
    now = utcnow()
    with migrated_engine.begin() as conn:
        for sid, ended in (("g1", now), ("g2", None)):
            conn.execute(
                text(
                    "INSERT INTO collection_segments (id, run_id, store_id, trigger, day, started_at, "
                    "heartbeat_at, ended_at, active_s, credits_estimated, browser_sessions, browsers_closed, "
                    "steps, products_verified) VALUES (:id, :run, :store, 'test', '2026-10-29', :now, :now, "
                    ":ended, 0, 0, 0, 0, 0, 0)"
                ),
                {"id": sid, "run": run.id, "store": store.id, "now": now, "ended": ended},
            )
    assert migrate.upgrade(migrated_engine) == ("0002", "0006")
    with factory() as s:
        states = {g.id: g.end_state for g in s.scalars(select(CollectionSegment))}
        assert states == {"g1": "ended", "g2": None}
        s.add(
            RecordRow(
                id="x1",
                run_id=run.id,
                mode="LIVE",
                upc="0004119211060",
                record={},
                record_sha256="0" * 64,
                status="price_conflict",
                reasons=[],
                flags=[],
            )
        )
        s.commit()
    with migrated_engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0002")
    with migrated_engine.begin() as conn:
        assert (
            conn.execute(text("SELECT status FROM records WHERE id = 'x1'")).scalar() == "exported_not_valid"
        )
    assert migrate.upgrade(migrated_engine) == ("0002", "0006")  # 0004 since release 1.8.0
    assert _diff(migrated_engine) == []
