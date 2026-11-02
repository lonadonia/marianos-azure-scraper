"""The database schema: the migrations shipped inside the package (``marianos_headless/migrations``)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    return cfg


def head() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def state(engine: Engine) -> tuple[str | None, str | None]:
    """(the database's revision, the package's head revision)."""
    return current(engine), head()


def upgrade(engine: Engine) -> tuple[str | None, str | None]:
    """Apply every migration up to the head, in one transaction. Returns (before, after)."""
    before = current(engine)
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    return before, current(engine)
