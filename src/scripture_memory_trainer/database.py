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
        return configured
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
    resolved = url or database_url()
    connect_args = {"check_same_thread": False} if resolved.startswith("sqlite") else {}
    if poolclass is not None:
        return create_engine(resolved, connect_args=connect_args, poolclass=poolclass)
    return create_engine(resolved, connect_args=connect_args)


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
