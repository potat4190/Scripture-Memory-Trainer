"""Alembic environment.

Two edits to the generated template:

1. The URL comes from ``database.database_url()`` (i.e. ``DATABASE_URL``, or the
   local SQLite default), never from ``alembic.ini``. One source of truth, and
   no credentials in a tracked file.
2. ``render_as_batch=True``, because SQLite cannot ``ALTER`` a column in place.
   Batch mode rebuilds the table instead, so the same migration scripts run on
   both SQLite and Postgres.

``target_metadata`` is SQLModel's, and importing ``tables`` is what registers
the four tables on it -- without that import autogenerate sees an empty schema
and cheerfully writes a migration that drops everything.
"""

from logging.config import fileConfig

from sqlalchemy import pool
from sqlmodel import SQLModel

from alembic import context
from scripture_memory_trainer import tables  # noqa: F401  (registers the tables)
from scripture_memory_trainer.database import database_url, make_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run migrations against the configured database."""
    connectable = make_engine(database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
