"""SQLModel tables -- the Phase 3 persistence layer.

Deliberately **not** in ``models.py``. ``queue.py`` imports ``models``, and
``queue.py`` is one of the five pure Phase 1 modules whose exit criterion is
"no imports of FastAPI or any DB driver". Putting the tables in ``models.py``
would drag SQLAlchemy into the pure logic through that import. So the pure
dataclass ``models.Card`` stays the logic-layer type and the tables live here.
See ``docs/DECISIONS.md`` D13.

Every table carries ``updated_at`` and ``deleted`` for the Phase 5 sync:
last-write-wins needs a comparable timestamp, and deletions have to travel as
tombstones rather than as absences. ``updated_at`` comes from
``clock.real_now()`` -- real UTC, never the travellable app clock (D15).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import DateTime, Dialect, TypeDecorator
from sqlmodel import Field, SQLModel

from .clock import real_now

# ``AppState`` is a single-row table; this is the row.
APP_STATE_ID = 1


class UTCDateTime(TypeDecorator[datetime]):
    """Store UTC, return an aware UTC datetime -- on every backend.

    SQLite has no timezone type: an aware datetime goes in and a **naive** one
    comes back, so ``stored > real_now()`` raises ``TypeError``. That is exactly
    the comparison Phase 5's last-write-wins merge is built on, and a
    naive/aware mix is the classic way it silently goes wrong. Normalising in
    both directions here makes SQLite and Postgres behave identically, so no
    caller has to remember which one it is talking to.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        # A naive value can arrive from imported JSON; document it as UTC rather
        # than crashing a restore.
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        assert isinstance(value, datetime)
        return value.replace(tzinfo=UTC)


class Syncable(SQLModel):
    """The two columns every table needs to take part in sync.

    A plain (non-table) SQLModel used as a mixin, so the pair is declared once
    and cannot drift apart between tables.
    """

    updated_at: datetime = Field(default_factory=real_now, index=True, sa_type=UTCDateTime)
    deleted: bool = Field(default=False, index=True)


class Card(Syncable, table=True):
    """The verse itself. Content only -- never the review state (D8)."""

    card_id: str = Field(primary_key=True)
    reference: str = Field(index=True)
    language: str = Field(index=True)
    direction: str
    text: str


class CardState(Syncable, table=True):
    """Where a card sits in the Leitner boxes, and when it is next due.

    Split from ``Card`` because the two change on completely different clocks:
    card text is seeded once and effectively immutable, while state changes on
    every review. Sync merges them independently.
    """

    card_id: str = Field(primary_key=True, foreign_key="card.card_id")
    box: int = Field(default=0, index=True)
    due_date: date | None = Field(default=None, index=True)


class ReviewLog(Syncable, table=True):
    """One row per graded review -- the audit trail behind every box change.

    ``reviewed_on`` is the **app** date the review happened, so time travel is
    visible in the history; ``updated_at`` is real time, for sync.
    """

    id: int | None = Field(default=None, primary_key=True)
    card_id: str = Field(foreign_key="card.card_id", index=True)

    reviewed_on: date = Field(index=True)
    grade: str
    box_before: int
    box_after: int
    interval_days: int
    due_date: date

    # Present only when the review carried a typed answer (POST /api/review
    # with answer_text); a bare grade leaves these null.
    answer_text: str | None = Field(default=None)
    verdict_status: str | None = Field(default=None)
    matched: int | None = Field(default=None)
    total: int | None = Field(default=None)


class AppState(Syncable, table=True):
    """Single-row table holding the clock offset and the language filter.

    A table rather than a config file because the offset has to sync with
    everything else -- a reviewer who travels forward on one device should see
    the same app date on another.
    """

    id: int = Field(default=APP_STATE_ID, primary_key=True)
    offset_days: int = Field(default=0)
    # Comma-separated language codes, or null for "no filter". Kept as a scalar
    # so the row stays trivially syncable; the API exposes it as a list.
    language_filter: str | None = Field(default=None)
