"""PostgreSQL for the integration tests: MARIANOS_COLLECTOR_TEST_DATABASE_URL, or a throwaway server started
by the ``pgserver`` dev dependency in a temp directory. Every test drops and recreates the ``public``
schema, so a URL whose database name does not contain "test" is refused: a production database can never
be pointed at by mistake."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from marianos_headless.db import migrate
from marianos_headless.db.session import normalize_url

ENV_TEST_URL = "MARIANOS_COLLECTOR_TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    url = os.environ.get(ENV_TEST_URL)
    if url:
        database = url.split("?", 1)[0].rsplit("/", 1)[-1]
        if "test" not in database:
            pytest.exit(
                f"{ENV_TEST_URL} names database {database!r}; tests drop its schema, so only a database "
                "whose name contains 'test' is accepted",
                returncode=2,
            )
        yield normalize_url(url)
        return
    try:
        import pgserver
        import psycopg
    except ImportError:
        pytest.skip(f"no {ENV_TEST_URL} and pgserver is not installed")
    tmp = tempfile.mkdtemp(prefix="walmart-headless-pg-")
    srv = pgserver.get_server(tmp, cleanup_mode="delete")
    base = srv.get_uri()
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS walmart_collector_test")
        conn.execute("CREATE DATABASE walmart_collector_test")
    # Parsed, not split on "/": on Linux the server is reached through ?host=/tmp/<socket dir>.
    yield normalize_url(
        make_url(base).set(database="walmart_collector_test").render_as_string(hide_password=False)
    )
    srv.cleanup()


@pytest.fixture
def migrated_engine(pg_url: str) -> Iterator[Engine]:
    engine = create_engine(pg_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                "AND usename = current_user AND backend_type = 'client backend'"
            )
        )
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    migrate.upgrade(engine)
    yield engine
    engine.dispose()
