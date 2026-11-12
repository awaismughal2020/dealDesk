"""LangGraph's Postgres checkpointer over a psycopg connection pool."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy.engine import make_url


def libpq_url(sqlalchemy_url: str) -> str:
    """Convert `postgresql+psycopg://...` into a plain libpq URL."""
    return (
        make_url(sqlalchemy_url).set(drivername="postgresql").render_as_string(hide_password=False)
    )


def open_checkpointer(
    sqlalchemy_url: str, max_size: int = 10
) -> tuple[PostgresSaver, ConnectionPool[Any]]:
    """Return a saver and the pool it uses (close the pool on shutdown)."""
    pool: ConnectionPool[Any] = ConnectionPool(
        conninfo=libpq_url(sqlalchemy_url),
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    return PostgresSaver(pool), pool
