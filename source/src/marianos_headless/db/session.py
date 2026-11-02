"""Engine and session factory.

``MARIANOS_COLLECTOR_DATABASE_URL`` names the PostgreSQL database (``postgresql://user@host:5432/db``; a
password in it, or ``PGPASSWORD``, for password authentication). With
``MARIANOS_COLLECTOR_DATABASE_AUTH=entra`` (Azure Database for PostgreSQL with Microsoft Entra
authentication) the password of every new connection is an access token of the job's managed identity
(``azure-identity``), so no database password is stored anywhere.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

ENV_URL = "MARIANOS_COLLECTOR_DATABASE_URL"
ENV_AUTH = "MARIANOS_COLLECTOR_DATABASE_AUTH"
ENTRA_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def database_url() -> str:
    url = os.environ.get(ENV_URL)
    if not url:
        raise RuntimeError(f"{ENV_URL} is not set")
    return normalize_url(url)


def normalize_url(url: str) -> str:
    """Use the psycopg 3 driver for plain ``postgresql://`` URLs."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def make_engine(url: str | None = None) -> Engine:
    engine = create_engine(normalize_url(url) if url else database_url(), pool_pre_ping=True, future=True)
    if (os.environ.get(ENV_AUTH) or "").strip().lower() == "entra":
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()

        @event.listens_for(engine, "do_connect")
        def _token(dialect: Any, conn_rec: Any, cargs: Any, cparams: dict[str, Any]) -> None:
            cparams["password"] = credential.get_token(ENTRA_SCOPE).token
            cparams.setdefault("sslmode", "require")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
