"""Request and response models for the API.

Separate from ``tables.py`` on purpose: the tables are the storage shape and the
schemas are the wire shape, and they are allowed to differ. ``CardOut`` joins a
``Card`` to its ``CardState`` because that is what a client actually wants; the
database keeps them apart because they sync independently (D13).

Every model here is what ``/docs`` renders, so the field descriptions are the
API documentation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final, Literal

from pydantic import BaseModel, Field

from .checker import Verdict
from .scheduler import GRADES

Grade = Literal["again", "hard", "good", "easy"]
Language = Literal["en", "zh", "ar", "hi"]

EXPORT_FORMAT: Final = "scripture-memory-trainer/export"
EXPORT_VERSION: Final = 1


class VerdictOut(BaseModel):
    """The checker's answer, positions 1-based."""

    status: Literal["correct", "partial", "incorrect"]
    matched: int
    total: int
    unit: Literal["words", "chars"]
    mismatch_positions: list[int] = Field(
        default_factory=list, description="1-based positions that differ from the card"
    )
    missing_from: int | None = Field(
        default=None, description="1-based position of the first unit the answer never reached"
    )
    missing_count: int = 0
    surplus_count: int = Field(default=0, description="Units typed beyond the end of the card (D6)")
    surplus_from: int | None = None

    @classmethod
    def of(cls, verdict: Verdict) -> VerdictOut:
        return cls(**vars(verdict))


class CardOut(BaseModel):
    """A card joined to its review state -- the shape the UI renders."""

    card_id: str
    reference: str
    language: str
    direction: str = Field(description="`ltr` or `rtl` -- set the `dir` attribute per element")
    text: str
    box: int = Field(ge=0, le=5)
    due_date: date | None
    updated_at: datetime


class QueueOut(BaseModel):
    """Today's queue, capped, plus the count before the cap."""

    app_date: date = Field(description="The travellable app date the queue was built for")
    cards: list[CardOut]
    returned: int = Field(description='Cards in this response -- the "20" of "20 of 47 due"')
    total_due: int = Field(description='Cards due before the cap -- the "47"')
    cap: int
    language_filter: list[str] | None


class ReviewIn(BaseModel):
    """Grade a card. ``answer_text`` is optional: a bare grade is a valid review."""

    card_id: str
    grade: Grade = Field(description=f"One of {', '.join(GRADES)}")
    answer_text: str | None = Field(
        default=None, description="If present, it is checked and the verdict is stored"
    )


class ReviewOut(BaseModel):
    """What the review did: the verdict (if any) and the new schedule."""

    card_id: str
    app_date: date
    grade: Grade
    box_before: int
    box_after: int
    interval_days: int
    due_date: date
    due_today_again: bool = Field(
        description="True when the card is due again today, i.e. it re-enters this session"
    )
    verdict: VerdictOut | None


class CheckIn(BaseModel):
    """Check an answer without touching any state."""

    card_id: str
    answer_text: str


class CheckOut(BaseModel):
    card_id: str
    language: str
    verdict: VerdictOut


class ClockOut(BaseModel):
    """The persisted app state: where the clock is, and the language filter."""

    offset_days: int
    app_date: date = Field(description="real_date + offset_days")
    real_date: date
    language_filter: list[str] | None


class ClockIn(BaseModel):
    """Set the clock. Exactly one of the three moves, or none plus a filter change.

    - ``offset_days`` sets the offset outright (0 resets).
    - ``advance_days`` is relative -- the +1 / +7 / +30 buttons.
    - ``target_date`` jumps to a date.
    """

    offset_days: int | None = None
    advance_days: int | None = None
    target_date: date | None = None
    language_filter: list[Language] | None = Field(
        default=None, description="Omit to leave unchanged; pass [] to clear"
    )


class ExportOut(BaseModel):
    """A complete, self-contained dump -- the always-free backup.

    Includes tombstones (``deleted`` rows) so a restore cannot resurrect
    something the user removed.
    """

    format: Literal["scripture-memory-trainer/export"] = EXPORT_FORMAT
    version: int = EXPORT_VERSION
    exported_at: datetime
    app_date: date
    app_state: dict[str, object]
    cards: list[dict[str, object]]
    card_states: list[dict[str, object]]
    review_logs: list[dict[str, object]]


class ImportIn(BaseModel):
    """A previously exported payload. Same shape as ``ExportOut``."""

    format: str = EXPORT_FORMAT
    version: int = EXPORT_VERSION
    app_state: dict[str, object] | None = None
    cards: list[dict[str, object]] = Field(default_factory=list)
    card_states: list[dict[str, object]] = Field(default_factory=list)
    review_logs: list[dict[str, object]] = Field(default_factory=list)


class ImportOut(BaseModel):
    """What the restore changed. Rows older than what is stored are skipped."""

    cards_created: int = 0
    cards_updated: int = 0
    cards_skipped: int = 0
    states_created: int = 0
    states_updated: int = 0
    states_skipped: int = 0
    review_logs_created: int = 0
    review_logs_skipped: int = 0
    app_state_updated: bool = False
