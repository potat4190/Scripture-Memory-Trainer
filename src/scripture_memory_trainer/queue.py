"""Daily review queue construction. Pure function of ``(cards, today, lang_filter)``."""

from __future__ import annotations

from datetime import date

from .models import Card

DAILY_CAP = 20


def build_queue(
    cards: list[Card], today: date, lang_filter: list[str] | None = None
) -> tuple[list[Card], int]:
    """Return ``(queue, pre_cap_total)`` for the cards due on or before ``today``.

    ``queue`` is capped at ``DAILY_CAP``; ``pre_cap_total`` is the count before
    the cap, so the UI can say "20 of 47 due".

    Sort key: ``(due_date, box, reference)`` -- most overdue first, then lowest
    box, then reference as a plain **string** sort. That is alphabetical, not
    canonical Bible book order (``Isaiah`` < ``John`` < ``Leviticus`` < ...).
    Do not "helpfully" fix this.
    """
    due = [c for c in cards if c.due_date is not None and c.due_date <= today]
    if lang_filter:
        allowed = set(lang_filter)
        due = [c for c in due if c.language in allowed]

    # `or date.min` only satisfies the type checker; the filter above already
    # guarantees due_date is not None.
    due.sort(key=lambda c: (c.due_date or date.min, c.box, c.reference))

    pre_cap_total = len(due)
    return due[:DAILY_CAP], pre_cap_total
