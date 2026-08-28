"""The one shared data type for Phase 1: a card that knows its own box.

Phase 3 of the checklist splits this into separate ``Card`` / ``CardState``
SQLModel tables (state broken out for sync bookkeeping). Until a database
exists, ``box`` and ``due_date`` live on the card itself. See
``docs/DECISIONS.md`` (D8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Card:
    card_id: str
    reference: str
    language: str
    direction: str
    text: str
    box: int = 0
    due_date: date | None = None
