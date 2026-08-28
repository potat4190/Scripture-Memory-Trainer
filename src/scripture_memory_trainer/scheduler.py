"""Leitner box arithmetic. Pure functions -- no I/O, no clock calls.

Verified against all 8 traces in ``tests/fixtures/check_schedule.json``.

Three subtleties, each of which a naive implementation gets wrong:

1. ``hard`` uses the interval of the box the card is **already in**, not a new box.
2. ``hard`` floors, never rounds. Box 4 hard is ``21 * 60 // 100 == 12`` days, not 13.
3. ``hard`` on box 0 still advances the due date by 1 day (the minimum) while
   leaving the box at 0.
"""

from __future__ import annotations

from datetime import date, timedelta

INTERVALS: dict[int, int] = {0: 0, 1: 1, 2: 3, 3: 7, 4: 21, 5: 60}
MAX_BOX = 5

GRADES = ("again", "hard", "good", "easy")


def apply_grade(box: int, grade: str) -> tuple[int, int]:
    """Return ``(new_box, interval_days)`` for ``grade`` applied to a card in ``box``."""
    if grade == "again":
        return 0, INTERVALS[0]
    if grade == "hard":
        # Box unchanged. 60% of the box's own interval, floored, minimum 1 day.
        return box, max(1, INTERVALS[box] * 60 // 100)
    if grade == "good":
        new_box = min(MAX_BOX, box + 1)
        return new_box, INTERVALS[new_box]
    if grade == "easy":
        new_box = min(MAX_BOX, box + 2)
        return new_box, INTERVALS[new_box]
    raise ValueError(f"unknown grade: {grade!r}")


def next_due(review_date: date, interval_days: int) -> date:
    """The next due date: the day the card was reviewed plus the interval."""
    return review_date + timedelta(days=interval_days)
