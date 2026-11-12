"""Alembic environment. Reads DATABASE_URL from the environment; never from a file."""

import os

from alembic import context
from sqlalchemy import create_engine, pool

from dealdesk.adapters.db.models import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(os.environ["DATABASE_URL"], poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
