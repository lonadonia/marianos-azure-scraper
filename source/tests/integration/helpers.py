"""Shared helpers for DB-backed tests. All data created here lives in a throwaway database."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.core.settings import Settings, load_stores
from marianos_headless.db.models import (
    CategorySource,
    ListingPage,
    MembershipRow,
    PageFetch,
    ProductObservation,
    RecordRow,
    Run,
    Store,
    Task,
)
from marianos_headless.db.repo import import_category_sources, sync_stores
from marianos_headless.sites.marianos.csv_sources import load_category_csv
from marianos_headless.worker.runs import create_run
from tests.conftest import CONFIG, STORE_KEY


def seed(engine: Engine) -> tuple[sessionmaker[Session], Store]:
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        rows, sha = load_category_csv(CONFIG / "Marianos_Category_URLs.csv")
        import_category_sources(s, rows, sha, actor="test")
        sync_stores(s, load_stores(CONFIG / "stores.yaml"), actor="test")
        s.commit()
        store = s.query(Store).filter(Store.key == STORE_KEY).one()
    return factory, store


def new_run(
    factory: sessionmaker[Session], store: Store, *, mode: str = "LIVE", status: str | None = None
) -> Run:
    with factory() as s:
        run = create_run(s, s.get(Store, store.id) or store, Settings(), mode=mode, trigger="test")
        if status:
            run.status = status
        s.commit()
        return run


def reconciled_plan(
    factory: sessionmaker[Session],
    run_id: str,
    records: Sequence[dict[str, Any]],
    *,
    unrecorded: Sequence[str] = (),
) -> None:
    """A minimal plan whose coverage reconciles, for the publication protocol's tests on SYNTHETIC runs.

    Since 1.10.0rc7 the publication reads the run's coverage again (``coverage_problems``) and refuses a run
    whose plan has no listing. This writes one listing read to its last page: a page of the run's store
    (store check PASS) listing every record's UPC, each with an observation of this run on that page, an
    organic placement under the listing and a fresh record. ``unrecorded`` adds UPCs the page lists with no
    record, which must make the publication refuse the run."""
    now = datetime.now(UTC)
    upcs = [str(r["upc"]) for r in records]
    listed = [*upcs, *unrecorded]
    with factory() as s:
        run = s.get(Run, run_id)
        assert run is not None
        store = s.get(Store, run.store_id)
        assert store is not None
        source = s.scalars(select(CategorySource).order_by(CategorySource.csv_row_index)).first()
        assert source is not None
        tax = "synthetic-1"
        fetch = PageFetch(
            run_id=run_id, url="https://www.marianos.com/pl/synthetic", purpose="listing", started_at=now
        )
        s.add(fetch)
        s.flush()
        node = {"category_source_id": source.id, "taxonomy_id": tax, "kind": "listing"}
        s.add(
            Task(
                run_id=run_id,
                kind="listing_node",
                idem_key=f"listing:{run_id}:{tax}",
                category_source_id=source.id,
                taxonomy_id=tax,
                state="succeeded",
                cursor={"node": node, "status": "DONE", "total": len(listed)},
            )
        )
        s.add(
            ListingPage(
                run_id=run_id,
                category_source_id=source.id,
                csv_row_index=source.csv_row_index,
                taxonomy_id=tax,
                requested_filter={},
                url=fetch.url,
                route="listing",
                requested_page=1,
                requested_offset=0,
                page_fetch_id=fetch.id,
                location_id=store.location_id,
                modality=store.modality,
                store_check="PASS",
                total=len(listed),
                identities=listed,
                state="completed",
                verdict="new",
                observed_at=now,
            )
        )
        for i, (upc, record) in enumerate(zip(upcs, records, strict=True)):
            s.add(
                ProductObservation(
                    run_id=run_id,
                    upc=upc,
                    page_fetch_id=fetch.id,
                    source="card",
                    provenance={"node": tax},
                    parser_version="test",
                    observed_at=now,
                    mode=run.mode,
                )
            )
            s.add(
                MembershipRow(
                    run_id=run_id,
                    upc=upc,
                    category_source_id=source.id,
                    taxonomy_id=tax,
                    page_offset=0,
                    position=i,
                    via="organic",
                    placement="organic",
                    page_fetch_id=fetch.id,
                    observed_at=now,
                    mode=run.mode,
                )
            )
            body = json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
            s.add(
                RecordRow(
                    run_id=run_id,
                    upc=upc,
                    record=dict(record),
                    record_sha256=hashlib.sha256(body).hexdigest(),
                    status="valid",
                    mode=run.mode,
                )
            )
        s.commit()
