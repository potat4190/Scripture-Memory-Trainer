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
    """The configured database URL, or the local SQLite default."""
    return os.environ.get("DATABASE_URL") or DEFAULT_SQLITE_URL


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


engine = make_engine()


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    with Session(engine) as session:
        yield session
