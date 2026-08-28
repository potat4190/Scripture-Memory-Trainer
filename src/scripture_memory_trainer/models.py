"""The data type the pure logic speaks: a card that knows its own box.

Phase 3 split persistence into the ``Card`` / ``CardState`` tables in
``tables.py``, so this dataclass is now the *view* the logic works with rather
than the storage shape -- ``service.to_domain()`` joins the two tables back into
one of these before handing it to ``queue.build_queue()``. Keeping the pure
modules on a plain dataclass is what keeps SQLAlchemy out of them (D8, D13).
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
