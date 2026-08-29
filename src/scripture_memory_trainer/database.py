"""Engine and session wiring.

``DATABASE_URL`` selects the backend. It defaults to a local SQLite file so the
repo runs with no server and no configuration -- clone, ``uv sync``, migrate,
go. Phase 5 points the same variable at Supabase Postgres; nothing else in the
codebase changes, because every query goes through SQLModel. See
``docs/DECISIONS.md`` D14.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine
from sqlalchemy.pool import Pool
from sqlmodel import Session, create_engine

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SQLITE_URL = f"sqlite:///{ROOT / 'scripture.db'}"

load_dotenv(ROOT / ".env")


def normalise_url(url: str) -> str:
    """Point a bare Postgres URL at psycopg 3, the driver this project installs.

    Supabase (and Render, and Heroku, and every other dashboard) hands out
    `postgresql://...`. SQLAlchemy reads a URL with no driver as psycopg **2**,
    which is not a dependency here, so the app deploys fine and then fails on
    the first query with `ModuleNotFoundError: No module named 'psycopg2'` --
    an error that says nothing about the URL that caused it.

    Rewriting it here means the value copied straight from the dashboard works.
    An explicit driver is always left alone, so `postgresql+psycopg2://` still
    means what it says.
    """
    if url.startswith("postgres://"):  # the old Heroku form; SQLAlchemy rejects it outright
        url = f"postgresql://{url.removeprefix('postgres://')}"
    if url.startswith("postgresql://"):
        return f"postgresql+psycopg://{url.removeprefix('postgresql://')}"
    return url


def database_url() -> str:
    """The configured database URL, or the local SQLite default.

    On Vercel there is no local SQLite default to fall back to: the filesystem
    is read-only apart from ``/tmp``, which is discarded between invocations.
    Falling through would give a confusing "unable to open database file" on the
    first query, or -- worse -- a database that silently empties itself. Fail at
    import instead, with the fix in the message.
    """
    configured = os.environ.get("DATABASE_URL")
    if configured:
        return normalise_url(configured)
    if os.environ.get("VERCEL"):
        raise RuntimeError(
            "DATABASE_URL is not set. This deployment has no usable local "
            "database -- Vercel's filesystem is read-only apart from /tmp, and "
            "/tmp does not survive between requests. Set DATABASE_URL to your "
            "Postgres connection string under Project Settings -> Environment "
            "Variables, for Production and Preview."
        )
    return DEFAULT_SQLITE_URL


def make_engine(url: str | None = None, poolclass: type[Pool] | None = None) -> Engine:
    """Build an engine. SQLite needs one extra flag; Postgres needs none.

    ``poolclass`` exists for Alembic, which wants ``NullPool`` so a migration
    run does not leave a connection checked out.
    """
    # Normalised here as well as in `database_url()`, because this is the one
    # place the URL is actually used -- an explicitly passed URL (Alembic, the
    # tests, a script) has to get the same treatment. `normalise_url` is
    # idempotent, so applying it twice costs nothing.
    resolved = normalise_url(url or database_url())
    if resolved.startswith("sqlite"):
        connect_args: dict[str, object] = {"check_same_thread": False}
        pool_options: dict[str, object] = {}
    else:
        connect_args = {}
        # Serverless pointed at a connection pooler needs a small, sceptical
        # pool. Each function instance gets its own, so the default of five
        # multiplies by however many instances are warm; and a pooler will drop
        # an idle connection without telling the client, which surfaces as a
        # random "server closed the connection unexpectedly" on the next
        # request unless it is checked first.
        pool_options = {
            "pool_size": 1,
            "max_overflow": 2,
            "pool_pre_ping": True,
            "pool_recycle": 300,
        }

    if poolclass is not None:
        return create_engine(resolved, connect_args=connect_args, poolclass=poolclass)
    return create_engine(resolved, connect_args=connect_args, **pool_options)


_engine: Engine | None = None


def get_engine() -> Engine:
    """The process-wide engine, built on first use.

    Lazy on purpose. Building it at import time would mean two things on a
    serverless platform, both bad: a connection pool opened during every cold
    start whether or not the request touches the database, and -- because
    ``database_url()`` raises when ``DATABASE_URL`` is missing on Vercel -- a
    *build* failure rather than a runtime one, since the platform imports the
    app at build time to discover its routes and static mounts. A missing
    environment variable should break requests with a clear message, not stop
    the frontend from being deployed at all.
    """
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    with Session(get_engine()) as session:
        yield session
