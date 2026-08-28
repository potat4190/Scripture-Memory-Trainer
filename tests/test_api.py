"""The app skeleton: it starts, `/docs` renders, and the DB dependency is overridable.

The Phase 3 exit criterion is that the whole flow works through `/docs`, so the
docs rendering is itself a test, not a manual step.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from scripture_memory_trainer.api import app
from scripture_memory_trainer.database import get_session, make_engine
from scripture_memory_trainer.seed import seed_cards


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A client backed by a throwaway database, never the developer's own."""
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    SQLModel.metadata.create_all(engine)

    def override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_health_reports_an_empty_database(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "cards": 0, "card_states": 0}


def test_health_counts_seeded_cards(client: TestClient, tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    try:
        with Session(engine) as session:
            seed_cards(session)
    finally:
        engine.dispose()

    assert client.get("/api/health").json() == {
        "status": "ok",
        "cards": 32,
        "card_states": 32,
    }


def test_the_auto_generated_docs_render(client: TestClient) -> None:
    """Phase 3's exit criterion depends on `/docs` actually being there."""
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_the_openapi_schema_is_named_and_described(client: TestClient) -> None:
    info = client.get("/openapi.json").json()["info"]
    assert info["title"] == "Scripture Memory Trainer"
    assert info["version"] == "0.1.0"


def test_the_session_dependency_is_injectable(client: TestClient) -> None:
    """If this ever stops working the tests would silently hit the real database."""
    assert get_session in app.dependency_overrides
