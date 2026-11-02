"""Shared helpers for DB-backed tests. All data created here lives in a throwaway database."""

from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from marianos_headless.core.settings import Settings, load_stores
from marianos_headless.db.models import Run, Store
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
