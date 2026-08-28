"""The merge rules, at the level the API cannot reach.

`tests/test_api.py` drives import through HTTP, which exercises the *skip*
half of last-write-wins because an export is always older than the database it
came from. This file covers the other half: an incoming row that really is
newer, which is the case the whole rule exists for, plus the parsing and
guard branches around it.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, select

from scripture_memory_trainer.database import make_engine
from scripture_memory_trainer.service import (
    _as_date,
    _as_datetime,
    _state_for,
    _wins,
    app_clock,
    export_payload,
    import_payload,
    set_clock,
)
from scripture_memory_trainer.tables import APP_STATE_ID, AppState, Card, CardState

LATER = datetime(2099, 1, 1, tzinfo=UTC)
EARLIER = datetime(2000, 1, 1, tzinfo=UTC)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'service.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def a_card(session: Session, card_id: str = "c1") -> Card:
    card = Card(
        card_id=card_id, reference="John 3:16", language="en", direction="ltr", text="original"
    )
    session.add(card)
    session.add(CardState(card_id=card_id, box=1, due_date=date(2026, 9, 1)))
    session.commit()
    return card


# ---------------------------------------------------------------------------
# _wins: the comparison the whole merge rests on
# ---------------------------------------------------------------------------


def test_a_newer_row_wins() -> None:
    assert _wins({"updated_at": LATER.isoformat()}, EARLIER) is True


def test_an_older_row_loses() -> None:
    assert _wins({"updated_at": EARLIER.isoformat()}, LATER) is False


def test_a_tie_loses_which_is_what_makes_import_idempotent() -> None:
    assert _wins({"updated_at": LATER.isoformat()}, LATER) is False


def test_a_row_with_no_timestamp_loses() -> None:
    """Unknown age must not overwrite known age."""
    assert _wins({}, LATER) is False
    assert _wins({"updated_at": None}, LATER) is False


def test_a_naive_timestamp_is_read_in_the_stored_rows_zone() -> None:
    """Hand-edited exports lose their offset; compare rather than crash."""
    assert _wins({"updated_at": "2099-01-02T00:00:00"}, LATER) is True
    assert _wins({"updated_at": "1999-01-02T00:00:00"}, LATER) is False


def test_a_datetime_object_passes_through_unparsed() -> None:
    assert _wins({"updated_at": LATER}, EARLIER) is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-09-01", date(2026, 9, 1)),
        (date(2026, 9, 1), date(2026, 9, 1)),
        (None, None),
        (7, None),
    ],
)
def test_as_date_parses_what_an_export_can_contain(value: object, expected: date | None) -> None:
    assert _as_date(value) == expected


def test_as_datetime_ignores_a_value_it_cannot_read() -> None:
    assert _as_datetime(42) is None


# ---------------------------------------------------------------------------
# The update branches
# ---------------------------------------------------------------------------


def test_a_newer_card_overwrites_the_stored_text(session: Session) -> None:
    a_card(session)
    result = import_payload(
        session,
        {
            "cards": [
                {
                    "card_id": "c1",
                    "reference": "John 3:16",
                    "language": "en",
                    "direction": "ltr",
                    "text": "corrected",
                    "updated_at": LATER.isoformat(),
                }
            ]
        },
    )
    assert result["cards_updated"] == 1
    stored = session.get(Card, "c1")
    assert stored is not None and stored.text == "corrected"


def test_a_newer_state_overwrites_the_box_and_due_date(session: Session) -> None:
    a_card(session)
    result = import_payload(
        session,
        {
            "card_states": [
                {
                    "card_id": "c1",
                    "box": 4,
                    "due_date": "2026-12-25",
                    "updated_at": LATER.isoformat(),
                }
            ]
        },
    )
    assert result["states_updated"] == 1
    state = session.get(CardState, "c1")
    assert state is not None
    assert (state.box, state.due_date) == (4, date(2026, 12, 25))


def test_a_newer_app_state_moves_the_clock(session: Session) -> None:
    set_clock(session, offset_days=3)
    result = import_payload(
        session,
        {
            "app_state": {
                "id": APP_STATE_ID,
                "offset_days": 45,
                "language_filter": "ar,hi",
                "updated_at": LATER.isoformat(),
            }
        },
    )
    assert result["app_state_updated"] is True
    assert app_clock(session).offset_days == 45


def test_an_older_app_state_leaves_the_clock_alone(session: Session) -> None:
    set_clock(session, offset_days=3)
    result = import_payload(
        session,
        {"app_state": {"id": APP_STATE_ID, "offset_days": 45, "updated_at": EARLIER.isoformat()}},
    )
    assert result["app_state_updated"] is False
    assert app_clock(session).offset_days == 3


def test_a_tombstoned_card_arrives_as_deleted(session: Session) -> None:
    """Deletions travel as tombstones; a restore must not resurrect them."""
    a_card(session)
    import_payload(
        session,
        {
            "cards": [
                {
                    "card_id": "c1",
                    "reference": "John 3:16",
                    "language": "en",
                    "direction": "ltr",
                    "text": "original",
                    "deleted": True,
                    "updated_at": LATER.isoformat(),
                }
            ]
        },
    )
    stored = session.get(Card, "c1")
    assert stored is not None and stored.deleted is True


def test_a_review_log_without_dates_is_skipped_not_stored(session: Session) -> None:
    a_card(session)
    result = import_payload(
        session,
        {"review_logs": [{"card_id": "c1", "grade": "good", "box_before": 0, "box_after": 1}]},
    )
    assert result["review_logs_skipped"] == 1
    assert export_payload(session)["review_logs"] == []


# ---------------------------------------------------------------------------
# State created on demand
# ---------------------------------------------------------------------------


def test_state_is_created_on_demand_for_a_card_that_has_none(session: Session) -> None:
    session.add(
        Card(card_id="c2", reference="Psalm 23:1", language="en", direction="ltr", text="x")
    )
    session.commit()
    assert session.get(CardState, "c2") is None

    state = _state_for(session, "c2")
    assert state.box == 0
    assert state.due_date == app_clock(session).today(), "a card with no state is due now"


def test_state_created_on_demand_follows_the_app_clock(session: Session) -> None:
    session.add(
        Card(card_id="c3", reference="Psalm 23:1", language="en", direction="ltr", text="x")
    )
    session.commit()
    set_clock(session, advance_days=10)

    state = _state_for(session, "c3")
    assert state.due_date == app_clock(session).today()


def test_app_state_is_created_once_and_reused(session: Session) -> None:
    first = app_clock(session).offset_days
    set_clock(session, advance_days=2)
    assert app_clock(session).offset_days == first + 2
    assert len(session.exec(select(AppState)).all()) == 1


def test_set_clock_target_date_wins_over_the_other_moves(session: Session) -> None:
    """The API rejects two moves at once; the service still has to be deterministic."""
    target = app_clock(session).today() + timedelta(days=9)
    state = set_clock(session, offset_days=100, advance_days=5, target_date=target)
    assert state.offset_days == 9
