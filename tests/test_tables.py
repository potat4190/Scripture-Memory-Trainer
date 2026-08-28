"""The Phase 3 schema, the seed loader, and the app skeleton.

Everything here runs against a throwaway SQLite database in ``tmp_path`` --
never the developer's ``scripture.db``, and never a network.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlmodel import Session, SQLModel, select

from scripture_memory_trainer.clock import real_now
from scripture_memory_trainer.database import make_engine
from scripture_memory_trainer.seed import load_seed_rows, seed_cards
from scripture_memory_trainer.tables import (
    APP_STATE_ID,
    AppState,
    Card,
    CardState,
    ReviewLog,
    UTCDateTime,
)

SQLITE_DIALECT = sqlite_dialect()

SYNCABLE_TABLES = [Card, CardState, ReviewLog, AppState]


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()  # otherwise the SQLite connection leaks a ResourceWarning


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# Schema shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", SYNCABLE_TABLES, ids=lambda t: t.__name__)
def test_every_table_carries_the_sync_columns(table: type[SQLModel]) -> None:
    """The checklist requires `updated_at` and `deleted` on every table."""
    columns = set(table.model_fields)
    assert {"updated_at", "deleted"} <= columns, table.__name__


@pytest.mark.parametrize("table", SYNCABLE_TABLES, ids=lambda t: t.__name__)
def test_sync_columns_are_indexed(table: type[SQLModel]) -> None:
    """Sync selects on `updated_at > last_sync_at`; unindexed that is a table scan."""
    # `__tablename__` is typed as str-or-callable on the base; every table here
    # is a real table, so the name is a plain string.
    name = table.__tablename__
    assert isinstance(name, str)
    indexed = {c.name for c in SQLModel.metadata.tables[name].columns if c.index}
    assert {"updated_at", "deleted"} <= indexed, table.__name__


def test_updated_at_defaults_to_real_utc_not_the_app_clock(session: Session) -> None:
    """Sync timestamps must ignore the travellable offset. See DECISIONS D15."""
    before = real_now()
    card = Card(card_id="x", reference="R", language="en", direction="ltr", text="t")
    session.add(card)
    session.commit()
    session.refresh(card)

    assert before <= card.updated_at <= real_now()
    assert card.deleted is False


def test_timestamps_round_trip_as_aware_utc(session: Session) -> None:
    """SQLite has no timezone type, so an aware value would come back naive.

    Phase 5's last-write-wins merge compares stored timestamps against
    `real_now()`; a naive/aware mix raises TypeError there. `UTCDateTime`
    normalizes both directions so SQLite and Postgres behave the same.
    """
    card = Card(card_id="tz", reference="R", language="en", direction="ltr", text="t")
    session.add(card)
    session.commit()
    session.expire_all()  # force a real read back out of the database

    stored = session.get(Card, "tz")
    assert stored is not None
    assert stored.updated_at.tzinfo is not None, "a naive timestamp breaks sync comparison"
    assert stored.updated_at.utcoffset() == UTC.utcoffset(None)
    assert stored.updated_at <= real_now()  # must not raise


def test_card_state_is_separate_from_card_content(session: Session) -> None:
    """D8: content and review state are different tables with different lifetimes."""
    assert "box" not in Card.model_fields
    assert "due_date" not in Card.model_fields
    assert "text" not in CardState.model_fields


def test_app_state_is_a_single_pinned_row(session: Session) -> None:
    session.add(AppState(id=APP_STATE_ID, offset_days=17))
    session.commit()
    rows = session.exec(select(AppState)).all()
    assert [(r.id, r.offset_days) for r in rows] == [(APP_STATE_ID, 17)]


def test_review_log_records_both_clocks(session: Session) -> None:
    """`reviewed_on` is the app date; `updated_at` is real time."""
    session.add(Card(card_id="c1", reference="R", language="en", direction="ltr", text="t"))
    session.commit()

    travelled = date(2026, 11, 1)
    session.add(
        ReviewLog(
            card_id="c1",
            reviewed_on=travelled,
            grade="good",
            box_before=0,
            box_after=1,
            interval_days=1,
            due_date=travelled + timedelta(days=1),
        )
    )
    session.commit()

    (log,) = session.exec(select(ReviewLog)).all()
    assert log.reviewed_on == travelled
    assert log.updated_at.date() != travelled, "sync time must not follow the app clock"
    assert log.answer_text is None, "a bare grade carries no verdict"


# ---------------------------------------------------------------------------
# Seed loader
# ---------------------------------------------------------------------------


def test_seeding_imports_every_card_and_gives_each_a_state(session: Session) -> None:
    result = seed_cards(session)
    assert (result.created, result.updated, result.unchanged) == (32, 0, 0)
    assert result.states_created == 32
    assert len(session.exec(select(Card)).all()) == 32
    assert len(session.exec(select(CardState)).all()) == 32


def test_seeding_twice_changes_nothing(session: Session) -> None:
    """The checklist's word is "idempotently"."""
    seed_cards(session)
    again = seed_cards(session)
    assert (again.created, again.updated, again.unchanged) == (0, 0, 32)
    assert again.states_created == 0
    assert len(session.exec(select(Card)).all()) == 32


def test_reseeding_does_not_reset_study_progress(session: Session) -> None:
    """The bug this guards: a re-seed knocking every card back to box 0."""
    seed_cards(session)
    state = session.exec(select(CardState)).first()
    assert state is not None
    state.box, state.due_date = 4, date(2026, 12, 25)
    session.add(state)
    session.commit()

    seed_cards(session)

    session.refresh(state)
    assert (state.box, state.due_date) == (4, date(2026, 12, 25))


def test_reseeding_does_not_touch_updated_at_of_unchanged_cards(session: Session) -> None:
    """A no-op re-seed must not manufacture rows for the next sync to push."""
    seed_cards(session)
    card = session.exec(select(Card)).first()
    assert card is not None
    stamp = card.updated_at

    seed_cards(session)

    session.refresh(card)
    assert card.updated_at == stamp


def test_seeding_updates_changed_card_text(session: Session, tmp_path: Path) -> None:
    import json

    seed_cards(session)
    card = session.exec(select(Card)).first()
    assert card is not None
    stamp = card.updated_at

    rows = load_seed_rows()
    edited = [dict(r) for r in rows]
    edited[0] = {**edited[0], "card_id": card.card_id, "text": "corrected text"}
    patched = tmp_path / "cards.json"
    patched.write_text(json.dumps(edited, ensure_ascii=False), encoding="utf-8")

    result = seed_cards(session, patched)

    session.refresh(card)
    assert result.updated == 1
    assert card.text == "corrected text"
    assert card.updated_at > stamp, "a real content change must be pushed on the next sync"


def test_the_seed_file_matches_the_card_table_columns() -> None:
    rows = load_seed_rows()
    assert len(rows) == 32
    for row in rows:
        assert set(row) <= set(Card.model_fields)


# ---------------------------------------------------------------------------
# UTCDateTime edge cases
# ---------------------------------------------------------------------------


def test_a_naive_timestamp_is_accepted_and_read_back_as_utc(session: Session) -> None:
    """Imported JSON can carry a naive timestamp; a restore must not crash on it.

    It is documented as UTC rather than rejected -- see the note in
    `UTCDateTime.process_bind_param`.
    """
    naive = datetime(2026, 6, 1, 12, 0, 0)
    assert naive.tzinfo is None

    card = Card(
        card_id="naive", reference="R", language="en", direction="ltr", text="t", updated_at=naive
    )
    session.add(card)
    session.commit()
    session.expire_all()

    stored = session.get(Card, "naive")
    assert stored is not None
    assert stored.updated_at == naive.replace(tzinfo=UTC)


def test_utc_datetime_passes_none_through_unchanged() -> None:
    """A nullable timestamp column must not blow up on NULL in either direction."""
    column = UTCDateTime()
    assert column.process_bind_param(None, SQLITE_DIALECT) is None
    assert column.process_result_value(None, SQLITE_DIALECT) is None


def test_a_non_utc_offset_is_converted_not_truncated() -> None:
    """An aware value in another zone must be *converted* to UTC before storing."""
    kathmandu = timezone(timedelta(hours=5, minutes=45))
    aware = datetime(2026, 6, 1, 12, 0, 0, tzinfo=kathmandu)

    bound = UTCDateTime().process_bind_param(aware, SQLITE_DIALECT)
    assert bound is not None
    assert bound.tzinfo is None, "stored form is naive UTC"
    assert bound == aware.astimezone(UTC).replace(tzinfo=None)
