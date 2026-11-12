"""Engine and session factory."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = sessionmaker[Session]


def make_engine(url: str, pool_size: int = 10) -> Engine:
    """Create a pooled engine. `pool_pre_ping` survives database restarts."""
    return create_engine(url, pool_size=pool_size, pool_pre_ping=True, future=True)


def make_session_factory(engine: Engine) -> SessionFactory:
    """Sessions do not expire objects on commit, so returned records stay readable."""
    return sessionmaker(bind=engine, expire_on_commit=False)
