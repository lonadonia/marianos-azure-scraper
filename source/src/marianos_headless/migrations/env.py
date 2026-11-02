"""Alembic environment. The connection comes from ``marianos-collector db-upgrade`` (the collector's own
engine, with Microsoft Entra tokens when configured), or from MARIANOS_COLLECTOR_DATABASE_URL or
``alembic -x url=...`` for a developer."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from marianos_headless.db.models import Base
from marianos_headless.db.session import database_url, normalize_url

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    x = context.get_x_argument(as_dictionary=True)
    return normalize_url(x["url"]) if "url" in x else database_url()


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is None:
        engine = engine_from_config({"sqlalchemy.url": _url()}, prefix="sqlalchemy.", poolclass=pool.NullPool)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
        return
    context.configure(connection=connectable, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
