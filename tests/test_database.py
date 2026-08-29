"""Engine construction and the request-scoped session dependency.

Small, but this is the wiring every endpoint depends on: a `get_session` that
failed to close, or a SQLite engine built without `check_same_thread=False`,
breaks the app in ways no logic test would show.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest import mock

import pytest
from sqlalchemy.pool import NullPool, QueuePool
from sqlmodel import Session, SQLModel, select

from scripture_memory_trainer.database import (
    DEFAULT_SQLITE_URL,
    database_url,
    get_engine,
    get_session,
    make_engine,
)
from scripture_memory_trainer.tables import Card


def test_database_url_falls_back_to_local_sqlite() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        assert database_url() == DEFAULT_SQLITE_URL
    with mock.patch.dict(os.environ, {"DATABASE_URL": ""}, clear=True):
        assert database_url() == DEFAULT_SQLITE_URL, "an empty value is not a configured URL"


def test_database_url_honours_the_environment() -> None:
    with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql+psycopg://h/db"}, clear=True):
        assert database_url() == "postgresql+psycopg://h/db"


def test_a_sqlite_engine_is_usable_from_another_thread(tmp_path: Path) -> None:
    """FastAPI serves requests off a threadpool; without `check_same_thread=False`
    SQLite raises as soon as a connection crosses threads."""
    engine = make_engine(f"sqlite:///{tmp_path / 'x.db'}")
    SQLModel.metadata.create_all(engine)
    failures: list[BaseException] = []

    def query() -> None:
        try:
            with Session(engine) as session:
                session.exec(select(Card)).all()
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=query)
    thread.start()
    thread.join()
    engine.dispose()

    assert failures == []


def test_a_non_sqlite_url_gets_no_sqlite_only_connect_args() -> None:
    """`check_same_thread` is a SQLite argument; Postgres would reject it."""
    engine = make_engine("postgresql+psycopg://user:pw@localhost:5432/db")
    try:
        assert engine.dialect.name == "postgresql"
    finally:
        engine.dispose()


def test_make_engine_accepts_a_pool_class(tmp_path: Path) -> None:
    """`alembic/env.py` passes NullPool so a migration leaves nothing checked out."""
    engine = make_engine(f"sqlite:///{tmp_path / 'x.db'}", poolclass=NullPool)
    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()


def test_the_engine_is_built_lazily_not_at_import(tmp_path: Path) -> None:
    """Import must not open a pool, and must not need DATABASE_URL.

    Vercel imports the app at build time to discover its routes and static
    mounts. An engine built at import would turn a missing environment variable
    into a failed *build* -- no frontend deployed at all -- rather than a
    request that fails with a message naming the variable.
    """
    url = f"sqlite:///{tmp_path / 'lazy.db'}"
    with (
        mock.patch("scripture_memory_trainer.database._engine", None),
        mock.patch.dict(os.environ, {"DATABASE_URL": url}),
    ):
        first = get_engine()
        assert get_engine() is first, "the engine is built once and reused"
        first.dispose()


def test_a_missing_database_url_on_vercel_fails_loudly() -> None:
    """The read-only filesystem there makes the SQLite default a trap, not a default."""
    with (
        mock.patch.dict(os.environ, {"VERCEL": "1"}, clear=True),
        pytest.raises(RuntimeError, match="DATABASE_URL is not set"),
    ):
        database_url()


def test_a_missing_database_url_anywhere_else_is_just_sqlite() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        assert database_url() == DEFAULT_SQLITE_URL


def test_get_session_yields_a_session_and_closes_it(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'x.db'}")
    SQLModel.metadata.create_all(engine)
    try:
        with mock.patch("scripture_memory_trainer.database._engine", engine):
            generator = get_session()
            session = next(generator)
            assert isinstance(session, Session)

            session.exec(select(Card))  # force a real connection checkout
            pool = engine.pool
            assert isinstance(pool, QueuePool)
            assert pool.checkedout() == 1

            list(generator)  # exhaust it, running the context manager's exit
            # `is_active` means "not in a failed transaction", not "open" -- the
            # thing that matters is that the connection went back to the pool.
            assert pool.checkedout() == 0, "the dependency leaked a connection"
    finally:
        engine.dispose()


def test_the_seed_command_fills_a_fresh_database(tmp_path: Path, capsys: object) -> None:
    """`python -m scripture_memory_trainer` is the one command a deploy runs after
    migrating, so it gets a test rather than only a mention in the README."""
    from unittest import mock as _mock

    from scripture_memory_trainer.__main__ import main
    from scripture_memory_trainer.tables import Card as CardTable

    url = f"sqlite:///{tmp_path / 'seeded.db'}"
    engine = make_engine(url)
    SQLModel.metadata.create_all(engine)
    engine.dispose()

    with _mock.patch.dict(os.environ, {"DATABASE_URL": url}, clear=False):
        main()

    verify = make_engine(url)
    try:
        with Session(verify) as session:
            assert len(session.exec(select(CardTable)).all()) == 32
    finally:
        verify.dispose()
