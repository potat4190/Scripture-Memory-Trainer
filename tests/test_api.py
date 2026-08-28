"""Every Phase 3 endpoint, against a throwaway database.

The Phase 3 exit criterion is that the whole flow works through `/docs` with no
frontend, so the docs rendering is itself a test and
``test_the_whole_flow_runs_end_to_end`` walks the exact sequence a reviewer
would click through: seed, queue, check, review, travel, export, restore.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from scripture_memory_trainer.api import app
from scripture_memory_trainer.database import get_session, make_engine
from scripture_memory_trainer.queue import DAILY_CAP
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


@pytest.fixture
def seeded(client: TestClient, tmp_path: Path) -> TestClient:
    """The same client with the seed loaded -- and nothing else done to it.

    Deliberately no fixing-up of due dates: a seeded install has to be
    reviewable as it comes out of `seed_cards`, and an earlier version of this
    fixture set the dates itself, which hid the fact that it did not.
    """
    engine = make_engine(f"sqlite:///{tmp_path / 'api.db'}")
    try:
        with Session(engine) as session:
            seed_cards(session)
    finally:
        engine.dispose()
    return client


@contextmanager
def second_device(tmp_path: Path) -> Iterator[TestClient]:
    """A client on a *different* database -- a second device, not a second view.

    `app.dependency_overrides` is global, so two clients cannot be live at once.
    This swaps the override for the duration of the block and puts the previous
    one back, which is why it is a context manager and not a fixture.
    """
    engine = make_engine(f"sqlite:///{tmp_path / 'other.db'}")
    SQLModel.metadata.create_all(engine)

    def override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_session, None)
        else:
            app.dependency_overrides[get_session] = previous
        engine.dispose()


def a_card(client: TestClient, language: str = "en") -> dict[str, Any]:
    card: dict[str, Any] = client.get("/api/cards", params={"language": language}).json()[0]
    return card


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


# ---------------------------------------------------------------------------
# GET /api/cards
# ---------------------------------------------------------------------------


def test_a_freshly_seeded_install_is_reviewable_immediately(seeded: TestClient) -> None:
    """Regression: seeded cards used to get a null due date and never appear."""
    body = seeded.get("/api/queue").json()
    assert body["total_due"] == 32
    assert all(c["due_date"] is not None for c in seeded.get("/api/cards").json())


def test_cards_lists_everything_with_its_state(seeded: TestClient) -> None:
    cards = seeded.get("/api/cards").json()
    assert len(cards) == 32
    assert set(cards[0]) == {
        "card_id",
        "reference",
        "language",
        "direction",
        "text",
        "box",
        "due_date",
        "updated_at",
    }
    assert all(c["box"] == 0 for c in cards), "a freshly seeded card starts in box 0"


def test_cards_are_ordered_by_reference(seeded: TestClient) -> None:
    references = [c["reference"] for c in seeded.get("/api/cards").json()]
    assert references == sorted(references)


def test_cards_filter_by_language(seeded: TestClient) -> None:
    arabic = seeded.get("/api/cards", params={"language": "ar"}).json()
    assert len(arabic) == 8
    assert {c["language"] for c in arabic} == {"ar"}
    assert {c["direction"] for c in arabic} == {"rtl"}


def test_cards_filter_by_several_languages_at_once(seeded: TestClient) -> None:
    rows = seeded.get("/api/cards", params=[("language", "ar"), ("language", "hi")]).json()
    assert {c["language"] for c in rows} == {"ar", "hi"}
    assert len(rows) == 16


def test_cards_filter_by_box(seeded: TestClient) -> None:
    card = a_card(seeded)
    seeded.post("/api/review", json={"card_id": card["card_id"], "grade": "good"})
    assert [c["card_id"] for c in seeded.get("/api/cards", params={"box": 1}).json()] == [
        card["card_id"]
    ]
    assert len(seeded.get("/api/cards", params={"box": 0}).json()) == 31


def test_cards_rejects_an_unknown_language(seeded: TestClient) -> None:
    assert seeded.get("/api/cards", params={"language": "fr"}).status_code == 422


def test_cards_rejects_a_box_outside_the_leitner_range(seeded: TestClient) -> None:
    assert seeded.get("/api/cards", params={"box": 6}).status_code == 422


# ---------------------------------------------------------------------------
# GET /api/queue
# ---------------------------------------------------------------------------


def test_queue_caps_at_twenty_and_reports_the_pre_cap_total(seeded: TestClient) -> None:
    body = seeded.get("/api/queue").json()
    assert body["returned"] == DAILY_CAP == 20
    assert body["total_due"] == 32, 'the UI needs both halves of "20 of 32 due"'
    assert len(body["cards"]) == 20


def test_queue_is_empty_when_nothing_is_due(client: TestClient) -> None:
    body = client.get("/api/queue").json()
    assert body["cards"] == []
    assert body["total_due"] == 0


def test_queue_orders_by_due_date_then_box_then_reference(seeded: TestClient) -> None:
    cards = seeded.get("/api/queue").json()["cards"]
    keys = [(c["due_date"], c["box"], c["reference"]) for c in cards]
    assert keys == sorted(keys)


def test_queue_filters_by_language(seeded: TestClient) -> None:
    body = seeded.get("/api/queue", params={"language": "zh"}).json()
    assert body["total_due"] == 8
    assert {c["language"] for c in body["cards"]} == {"zh"}
    assert body["language_filter"] == ["zh"]


def test_queue_uses_the_stored_language_filter_when_none_is_passed(seeded: TestClient) -> None:
    seeded.post("/api/clock", json={"language_filter": ["hi"]})
    body = seeded.get("/api/queue").json()
    assert body["language_filter"] == ["hi"]
    assert {c["language"] for c in body["cards"]} == {"hi"}


def test_a_query_parameter_overrides_the_stored_filter(seeded: TestClient) -> None:
    seeded.post("/api/clock", json={"language_filter": ["hi"]})
    body = seeded.get("/api/queue", params={"language": "en"}).json()
    assert {c["language"] for c in body["cards"]} == {"en"}


# ---------------------------------------------------------------------------
# POST /api/check
# ---------------------------------------------------------------------------


def test_check_accepts_a_perfect_answer(seeded: TestClient) -> None:
    card = a_card(seeded)
    body = seeded.post(
        "/api/check", json={"card_id": card["card_id"], "answer_text": card["text"]}
    ).json()
    assert body["verdict"]["status"] == "correct"
    assert body["verdict"]["matched"] == body["verdict"]["total"]


def test_check_reports_the_wrong_position(seeded: TestClient) -> None:
    card = a_card(seeded)
    words = card["text"].split()
    words[1] = "zzz"
    body = seeded.post(
        "/api/check", json={"card_id": card["card_id"], "answer_text": " ".join(words)}
    ).json()
    assert body["verdict"]["status"] == "partial"
    assert body["verdict"]["mismatch_positions"] == [2], "positions are 1-based"


def test_check_changes_no_state(seeded: TestClient) -> None:
    card = a_card(seeded)
    before = seeded.get("/api/cards").json()
    seeded.post("/api/check", json={"card_id": card["card_id"], "answer_text": "nonsense"})
    assert seeded.get("/api/cards").json() == before


def test_check_404s_on_an_unknown_card(seeded: TestClient) -> None:
    response = seeded.post("/api/check", json={"card_id": "nope", "answer_text": "x"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/review
# ---------------------------------------------------------------------------


def test_review_moves_the_box_and_sets_the_due_date(seeded: TestClient) -> None:
    card = a_card(seeded)
    today = date.fromisoformat(seeded.get("/api/clock").json()["app_date"])

    body = seeded.post("/api/review", json={"card_id": card["card_id"], "grade": "good"}).json()

    assert (body["box_before"], body["box_after"]) == (0, 1)
    assert body["interval_days"] == 1
    assert body["due_date"] == (today + timedelta(days=1)).isoformat()
    assert body["due_today_again"] is False
    assert body["verdict"] is None, "a bare grade carries no verdict"


def test_review_with_an_answer_returns_and_stores_the_verdict(seeded: TestClient) -> None:
    card = a_card(seeded)
    body = seeded.post(
        "/api/review",
        json={"card_id": card["card_id"], "grade": "easy", "answer_text": card["text"]},
    ).json()
    assert body["verdict"]["status"] == "correct"
    assert body["box_after"] == 2, "easy advances two boxes"
    assert body["interval_days"] == 3


def test_again_puts_the_card_back_in_todays_queue(seeded: TestClient) -> None:
    """The Phase 4 requirement that `again` re-enters the session starts here."""
    card = a_card(seeded)
    body = seeded.post("/api/review", json={"card_id": card["card_id"], "grade": "again"}).json()
    assert (body["box_after"], body["interval_days"]) == (0, 0)
    assert body["due_date"] == body["app_date"]
    assert body["due_today_again"] is True
    assert card["card_id"] in {c["card_id"] for c in seeded.get("/api/queue").json()["cards"]}


def test_review_rejects_an_unknown_grade(seeded: TestClient) -> None:
    card = a_card(seeded)
    response = seeded.post("/api/review", json={"card_id": card["card_id"], "grade": "brilliant"})
    assert response.status_code == 422


def test_review_404s_on_an_unknown_card(seeded: TestClient) -> None:
    assert seeded.post("/api/review", json={"card_id": "nope", "grade": "good"}).status_code == 404


def test_reviews_accumulate_in_the_history(seeded: TestClient) -> None:
    card = a_card(seeded)
    for grade in ("good", "good", "hard"):
        seeded.post("/api/review", json={"card_id": card["card_id"], "grade": grade})
    logs = seeded.get("/api/export").json()["review_logs"]
    assert [log["grade"] for log in logs] == ["good", "good", "hard"]
    assert [log["box_after"] for log in logs] == [1, 2, 2], "hard keeps the box"


# ---------------------------------------------------------------------------
# GET/POST /api/clock
# ---------------------------------------------------------------------------


def test_clock_starts_at_the_real_date(client: TestClient) -> None:
    body = client.get("/api/clock").json()
    assert body["offset_days"] == 0
    assert body["app_date"] == body["real_date"] == date.today().isoformat()


def test_clock_advances_by_days(client: TestClient) -> None:
    for step, expected in ((1, 1), (7, 8), (30, 38)):
        body = client.post("/api/clock", json={"advance_days": step}).json()
        assert body["offset_days"] == expected
        assert body["app_date"] == (date.today() + timedelta(days=expected)).isoformat()


def test_clock_jumps_to_a_date(client: TestClient) -> None:
    target = date.today() + timedelta(days=60)
    body = client.post("/api/clock", json={"target_date": target.isoformat()}).json()
    assert body["app_date"] == target.isoformat()
    assert body["offset_days"] == 60


def test_clock_resets_with_a_zero_offset(client: TestClient) -> None:
    client.post("/api/clock", json={"advance_days": 45})
    body = client.post("/api/clock", json={"offset_days": 0}).json()
    assert body["offset_days"] == 0
    assert body["app_date"] == date.today().isoformat()


def test_clock_survives_the_request(client: TestClient) -> None:
    client.post("/api/clock", json={"advance_days": 5})
    assert client.get("/api/clock").json()["offset_days"] == 5


def test_clock_rejects_two_moves_at_once(client: TestClient) -> None:
    response = client.post("/api/clock", json={"advance_days": 1, "offset_days": 9})
    assert response.status_code == 422


def test_clock_sets_and_clears_the_language_filter(client: TestClient) -> None:
    assert client.post("/api/clock", json={"language_filter": ["ar", "hi"]}).json()[
        "language_filter"
    ] == ["ar", "hi"]
    assert client.post("/api/clock", json={"language_filter": []}).json()["language_filter"] is None


def test_advancing_the_clock_changes_the_queue(seeded: TestClient) -> None:
    """The single most demonstrable thing in the app, tested end to end."""
    card = a_card(seeded)
    seeded.post("/api/review", json={"card_id": card["card_id"], "grade": "easy"})

    due_today = {c["card_id"] for c in seeded.get("/api/queue").json()["cards"]}
    assert card["card_id"] not in due_today, "it is scheduled 3 days out"

    seeded.post("/api/clock", json={"advance_days": 3})
    assert seeded.get("/api/queue").json()["total_due"] == 32, "everything is due again"


# ---------------------------------------------------------------------------
# GET /api/export and POST /api/import
# ---------------------------------------------------------------------------


def test_export_is_self_contained(seeded: TestClient) -> None:
    card = a_card(seeded)
    seeded.post(
        "/api/review",
        json={"card_id": card["card_id"], "grade": "good", "answer_text": card["text"]},
    )
    body = seeded.get("/api/export").json()

    assert body["format"] == "scripture-memory-trainer/export"
    assert body["version"] == 1
    assert len(body["cards"]) == 32
    assert len(body["card_states"]) == 32
    assert len(body["review_logs"]) == 1
    assert body["cards"][0]["text"], "the dump carries the verses, not just ids"
    assert body["app_state"]["offset_days"] == 0


def test_export_keeps_non_latin_text_intact(seeded: TestClient) -> None:
    arabic = [c for c in seeded.get("/api/export").json()["cards"] if c["language"] == "ar"]
    assert arabic and all(any(ch > "؀" for ch in c["text"]) for c in arabic)


def test_import_restores_onto_a_second_device(seeded: TestClient, tmp_path: Path) -> None:
    """The real restore path: an export from one database, into an empty other one."""
    card = a_card(seeded)
    seeded.post("/api/review", json={"card_id": card["card_id"], "grade": "good"})
    seeded.post("/api/clock", json={"advance_days": 12})
    dump = seeded.get("/api/export").json()

    with second_device(tmp_path) as other:
        assert other.get("/api/cards").json() == [], "the second device starts empty"
        result = other.post("/api/import", json=dump).json()

        assert result["cards_created"] == 32
        assert result["states_created"] == 32
        assert result["review_logs_created"] == 1
        assert result["app_state_updated"] is True

        restored = {c["card_id"]: c for c in other.get("/api/cards").json()}
        assert restored[card["card_id"]]["box"] == 1, "the review came across"
        assert other.get("/api/clock").json()["offset_days"] == 12, "so did the clock"


def test_import_is_idempotent(seeded: TestClient) -> None:
    dump = seeded.get("/api/export").json()
    first = seeded.post("/api/import", json=dump).json()
    second = seeded.post("/api/import", json=dump).json()
    assert first == second
    assert first["cards_updated"] == 0, "re-importing the same file changes nothing"
    assert first["cards_skipped"] == 32


def test_import_does_not_undo_newer_work(seeded: TestClient) -> None:
    """Restoring an old backup must not roll back study done since."""
    dump = seeded.get("/api/export").json()
    card = a_card(seeded)
    seeded.post("/api/review", json={"card_id": card["card_id"], "grade": "good"})

    seeded.post("/api/import", json=dump)

    after = {c["card_id"]: c for c in seeded.get("/api/cards").json()}
    assert after[card["card_id"]]["box"] == 1, "the newer review survived the restore"


def test_import_rejects_a_foreign_document(seeded: TestClient) -> None:
    response = seeded.post("/api/import", json={"format": "something-else", "cards": []})
    assert response.status_code == 422


def test_import_carries_the_review_history(seeded: TestClient) -> None:
    card = a_card(seeded)
    seeded.post("/api/review", json={"card_id": card["card_id"], "grade": "good"})
    dump = seeded.get("/api/export").json()

    assert len(dump["review_logs"]) == 1
    result = seeded.post("/api/import", json=dump).json()
    assert result["review_logs_created"] == 0, "the review is already there"
    assert result["review_logs_skipped"] == 1
    assert len(seeded.get("/api/export").json()["review_logs"]) == 1, "no duplicate rows"


# ---------------------------------------------------------------------------
# The exit criterion
# ---------------------------------------------------------------------------


def test_the_whole_flow_runs_end_to_end(seeded: TestClient) -> None:
    """Exactly the sequence a reviewer would click through in `/docs`."""
    queue = seeded.get("/api/queue").json()
    assert queue["returned"] == 20 and queue["total_due"] == 32

    card = queue["cards"][0]
    verdict = seeded.post(
        "/api/check", json={"card_id": card["card_id"], "answer_text": card["text"]}
    ).json()["verdict"]
    assert verdict["status"] == "correct"

    review = seeded.post(
        "/api/review",
        json={"card_id": card["card_id"], "grade": "good", "answer_text": card["text"]},
    ).json()
    assert review["box_after"] == 1

    seeded.post("/api/clock", json={"advance_days": 60})
    travelled = seeded.get("/api/queue").json()
    assert travelled["total_due"] == 32, "60 days on, everything is due again"

    dump = seeded.get("/api/export").json()
    assert len(dump["review_logs"]) == 1
    assert seeded.post("/api/import", json=dump).json()["cards_skipped"] == 32

    seeded.post("/api/clock", json={"offset_days": 0})
    assert seeded.get("/api/clock").json()["app_date"] == date.today().isoformat()


def test_import_skips_a_state_whose_card_is_missing(seeded: TestClient) -> None:
    """An orphan row would violate the foreign key -- Postgres enforces it, SQLite does not."""
    result = seeded.post(
        "/api/import",
        json={
            "format": "scripture-memory-trainer/export",
            "version": 1,
            "card_states": [{"card_id": "ghost", "box": 3, "due_date": "2026-09-01"}],
            "review_logs": [
                {
                    "card_id": "ghost",
                    "reviewed_on": "2026-09-01",
                    "grade": "good",
                    "box_before": 0,
                    "box_after": 1,
                    "interval_days": 1,
                    "due_date": "2026-09-02",
                }
            ],
        },
    ).json()
    assert result["states_skipped"] == 1
    assert result["review_logs_skipped"] == 1
    assert seeded.get("/api/health").json()["card_states"] == 32


def test_import_refuses_a_newer_export_version(seeded: TestClient) -> None:
    response = seeded.post(
        "/api/import", json={"format": "scripture-memory-trainer/export", "version": 99}
    )
    assert response.status_code == 422
    assert "newer than this build" in response.json()["detail"]
