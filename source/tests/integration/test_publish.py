"""Publication protocol and crash-safety. Records are SYNTHETIC; runs are created directly in the test DB."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.core.schema import build_record
from marianos_headless.core.settings import Settings
from marianos_headless.db.models import AuditLog, PublicationPointer, Run, Store, ValidationFinding
from marianos_headless.publishing.exports import write_exports
from marianos_headless.publishing.publish import PublicationRefused, latest_key, publish_run, sync_latest_json
from marianos_headless.storage.local import LocalStorageAdapter
from marianos_headless.worker.runs import register_exports
from tests.integration.helpers import new_run, seed

pytestmark = pytest.mark.postgres


class Crash(Exception):
    pass


def prepared_run(
    factory: sessionmaker[Session], store: Store, storage: LocalStorageAdapter, n: int = 3
) -> str:
    run = new_run(factory, store, status="validated")
    records = [
        build_record(
            {
                "upc": f"{i:012d}",
                "product_title": f"P{i}",
                "category": "Food",
                "url": f"https://www.walmart.com/ip/p/{1000 + i}",
                "regular_price": "1.00",
                "crawl_date": "2026-10-17",
            }
        )
        for i in range(n)
    ]
    ex = write_exports(
        storage,
        store_key=store.key,
        run_id=run.id,
        mode=run.mode,
        products=records,
        memberships=[],
        offers=[],
        provenance={},
        validation_report={"gates": []},
        config_snapshot=Settings().snapshot(),
        versions={"parser": "test"},
        site_version=None,
    )
    with factory() as s:
        register_exports(s, run.id, run.mode, ex)
        s.commit()
    return run.id


def pointer(factory: sessionmaker[Session], store_id: str) -> PublicationPointer | None:
    with factory() as s:
        return s.get(PublicationPointer, store_id)


def test_publish_and_republish(migrated_engine: Engine, tmp_path: Path) -> None:
    factory, store = seed(migrated_engine)
    storage = LocalStorageAdapter(tmp_path)
    r1 = prepared_run(factory, store, storage)
    res1 = publish_run(factory, storage, r1, "tester")
    assert res1.version == 1 and res1.previous_publication_id is None
    latest = json.loads(storage.get_bytes(latest_key(store.key)))
    assert latest["run_id"] == r1 and latest["version"] == 1 and latest["mode"] == "LIVE"
    r2 = prepared_run(factory, store, storage, n=4)
    res2 = publish_run(factory, storage, r2, "tester")
    assert res2.version == 2 and res2.previous_publication_id == res1.publication_id
    with factory() as s:
        assert s.get(Run, r1).status == "published"  # type: ignore[union-attr]
        assert len(list(s.scalars(select(AuditLog).where(AuditLog.action == "publish")))) == 2


def test_refusals_leave_pointer_untouched(migrated_engine: Engine, tmp_path: Path) -> None:
    factory, store = seed(migrated_engine)
    storage = LocalStorageAdapter(tmp_path)
    good = prepared_run(factory, store, storage)
    publish_run(factory, storage, good, "tester")
    before = pointer(factory, store.id)

    failing = prepared_run(factory, store, storage)
    with factory() as s:
        s.add(
            ValidationFinding(
                run_id=failing, scope="run", gate="G1", severity="FAIL", code="LOCATION_MISMATCH", message="x"
            )
        )
        s.commit()
    with pytest.raises(PublicationRefused, match="FAIL"):
        publish_run(factory, storage, failing, "tester", warn_override_reason="please")

    warned = prepared_run(factory, store, storage)
    with factory() as s:
        s.add(
            ValidationFinding(
                run_id=warned,
                scope="node",
                gate="G3",
                severity="WARN",
                code="NODE_INCOMPLETE",
                message="0.95",
            )
        )
        s.commit()
    with pytest.raises(PublicationRefused, match="WARN"):
        publish_run(factory, storage, warned, "tester")

    tampered = prepared_run(factory, store, storage)
    key = f"runs/{store.key}/{tampered}/exports/products.json"
    (tmp_path / key).write_bytes(b"[]\n")  # bypass the adapter, as a corrupted disk would
    with pytest.raises(PublicationRefused, match="integrity"):
        publish_run(factory, storage, tampered, "tester")

    not_validated = new_run(factory, store, status="rejected").id
    with pytest.raises(PublicationRefused, match="validated"):
        publish_run(factory, storage, not_validated, "tester")

    after = pointer(factory, store.id)
    assert before is not None and after is not None
    assert (after.publication_id, after.version) == (before.publication_id, before.version)

    res = publish_run(factory, storage, warned, "tester", warn_override_reason="0.95 accepted")
    assert res.version == 2
    with factory() as s:
        audit = s.scalars(select(AuditLog).where(AuditLog.target == warned)).one()
        assert audit.reason == "0.95 accepted"


@pytest.mark.parametrize("stage", ["before_commit", "inside_commit"])
def test_crash_before_or_during_commit_keeps_last_good(
    migrated_engine: Engine, tmp_path: Path, stage: str
) -> None:
    factory, store = seed(migrated_engine)
    storage = LocalStorageAdapter(tmp_path)
    good = prepared_run(factory, store, storage)
    publish_run(factory, storage, good, "tester")
    latest_before = storage.get_bytes(latest_key(store.key))
    nxt = prepared_run(factory, store, storage)

    def fault(s: str) -> None:
        if s == stage:
            raise Crash(s)

    with pytest.raises(Crash):
        publish_run(factory, storage, nxt, "tester", fault=fault)
    p = pointer(factory, store.id)
    assert p is not None and p.version == 1
    assert storage.get_bytes(latest_key(store.key)) == latest_before
    with factory() as s:
        assert s.get(Run, nxt).status == "validated"  # type: ignore[union-attr]
    assert publish_run(factory, storage, nxt, "tester").version == 2  # retry works


def test_crash_after_commit_is_repaired_from_db(migrated_engine: Engine, tmp_path: Path) -> None:
    factory, store = seed(migrated_engine)
    storage = LocalStorageAdapter(tmp_path)
    publish_run(factory, storage, prepared_run(factory, store, storage), "tester")
    nxt = prepared_run(factory, store, storage)

    def fault(s: str) -> None:
        if s == "after_commit":
            raise Crash(s)

    with pytest.raises(Crash):
        publish_run(factory, storage, nxt, "tester", fault=fault)
    p = pointer(factory, store.id)
    assert p is not None and p.version == 2  # the DB pointer is authoritative
    assert json.loads(storage.get_bytes(latest_key(store.key)))["run_id"] != nxt  # file is stale
    assert sync_latest_json(factory, storage, store.id)
    assert json.loads(storage.get_bytes(latest_key(store.key)))["run_id"] == nxt
