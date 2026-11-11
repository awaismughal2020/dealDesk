"""Integration tests run against a real Postgres (the Compose `db` service).

A fresh `dealdesk_test` database is created per session and migrated with Alembic, so the tests
exercise the real schema, constraints and triggers.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

from dealdesk.adapters.db.checkpointer import open_checkpointer
from dealdesk.adapters.db.session import SessionFactory, make_engine, make_session_factory
from dealdesk.adapters.embeddings.fake import FakeEmbedder
from scripts.seed import seed_reference_data

TRANSACTIONAL_TABLES = (
    "invoice_milestones",
    "pipeline_records",
    "approvals",
    "run_steps",
    "runs",
    "documents",
    "refresh_tokens",
    "users",
    "audit_events",
)


def _test_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is not set; run integration tests with `make test`")
    return url


def _recreate_database(url: str) -> None:
    parsed = make_url(url)
    admin = parsed.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    name = parsed.database
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')  # type: ignore[arg-type]
        connection.execute(f'CREATE DATABASE "{name}"')  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_url()
    _recreate_database(url)
    config = Config("alembic.ini")
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(config, "head")
        saver, pool = open_checkpointer(url, max_size=1)
        try:
            saver.setup()
        finally:
            pool.close()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = make_engine(database_url, pool_size=5)
    seed_reference_data(engine, FakeEmbedder())
    yield engine
    engine.dispose()


@pytest.fixture
def sessions(engine: Engine) -> SessionFactory:
    """A session factory over a database whose transactional tables start empty."""
    with engine.begin() as connection:
        # Bypass the append-only trigger for test cleanup only (superuser in the test container).
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(text(f"TRUNCATE {', '.join(TRANSACTIONAL_TABLES)} CASCADE"))
    return make_session_factory(engine)
