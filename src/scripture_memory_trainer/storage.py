"""Local JSON persistence for a terminal driver.

This is **not** part of Phase 1 -- every function here does file I/O. It exists
so a terminal program can remember box / due_date / clock offset between runs,
standing in for the SQLModel + Postgres backend that Phase 3 will add. Kept in
its own module, separate from the five pure logic files. See
``docs/DECISIONS.md`` (D9).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .models import Card


def load_seed_cards(seed_path: Path) -> list[Card]:
    """Read ``seed/cards.json`` into ``Card`` objects (no box/due state)."""
    rows: list[dict[str, str]] = json.loads(seed_path.read_text(encoding="utf-8"))
    return [
        Card(
            card_id=row["card_id"],
            reference=row["reference"],
            language=row["language"],
            direction=row["direction"],
            text=row["text"],
        )
        for row in rows
    ]


def load_state(state_path: Path, cards: list[Card], today: date) -> tuple[int, list[str] | None]:
    """Merge persisted box / due_date onto ``cards`` in place.

    Cards not yet in the state file start at box 0, due immediately. Returns
    ``(offset_days, language_filter)``.
    """
    offset_days = 0
    language_filter: list[str] | None = None
    saved_cards: dict[str, Any] = {}

    if state_path.exists():
        raw: dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
        offset_days = int(raw.get("offset_days", 0))
        language_filter = raw.get("language_filter")
        saved_cards = raw.get("cards", {})

    for card in cards:
        saved = saved_cards.get(card.card_id)
        if saved is None:
            card.box = 0
            card.due_date = today
        else:
            card.box = int(saved["box"])
            card.due_date = date.fromisoformat(saved["due_date"])

    return offset_days, language_filter


def save_state(
    state_path: Path,
    cards: list[Card],
    offset_days: int,
    language_filter: list[str] | None = None,
) -> None:
    """Write box / due_date for every card plus the clock offset and filter."""
    payload = {
        "offset_days": offset_days,
        "language_filter": language_filter,
        "cards": {
            c.card_id: {
                "box": c.box,
                "due_date": c.due_date.isoformat() if c.due_date is not None else None,
            }
            for c in cards
        },
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_json(
    export_path: Path,
    cards: list[Card],
    offset_days: int,
    language_filter: list[str] | None = None,
) -> None:
    """Write a full, self-contained JSON dump -- the always-free backup."""
    payload = {
        "offset_days": offset_days,
        "language_filter": language_filter,
        "cards": [
            {
                "card_id": c.card_id,
                "reference": c.reference,
                "language": c.language,
                "direction": c.direction,
                "text": c.text,
                "box": c.box,
                "due_date": c.due_date.isoformat() if c.due_date is not None else None,
            }
            for c in cards
        ],
    }
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
