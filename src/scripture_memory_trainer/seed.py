"""Idempotent seed loader for ``seed/cards.json``.

Idempotent in the strict sense the checklist asks for: running it twice leaves
the database exactly as running it once did, and it never resets a card the
user has already been studying. Card **content** is upserted (so a corrected
verse reaches an existing install), while ``CardState`` is only ever *created*,
never overwritten -- re-seeding must not knock a card back to box 0.

``updated_at`` is bumped only for rows whose content actually changed, so a
no-op re-seed does not manufacture sync traffic (Phase 5 pushes rows where
``updated_at > last_sync_at``).

A newly created ``CardState`` is due on the app date, not null: a null due date
never satisfies ``build_queue``'s ``due_date <= today``, so the card would be
seeded and then never appear.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlmodel import Session, select

from .clock import Clock, real_now
from .tables import APP_STATE_ID, AppState, Card, CardState

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SEED_PATH = ROOT / "seed" / "cards.json"

CARD_CONTENT_FIELDS = ("reference", "language", "direction", "text")


def _app_today(session: Session) -> date:
    """The app date, honouring any clock offset already stored.

    Read directly rather than through ``service`` so the seed loader stays
    usable on its own -- it runs before the API exists, from a script or a
    migration.
    """
    state = session.get(AppState, APP_STATE_ID)
    return Clock(offset_days=state.offset_days if state else 0).today()


@dataclass
class SeedResult:
    """What a seed run actually did, so callers can report it honestly."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    states_created: int = 0


def load_seed_rows(seed_path: Path | None = None) -> list[dict[str, str]]:
    """Read the seed file. Pure -- no database involved."""
    path = seed_path or DEFAULT_SEED_PATH
    rows: list[dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))
    return rows


def seed_cards(session: Session, seed_path: Path | None = None) -> SeedResult:
    """Import ``seed/cards.json`` into the database, idempotently."""
    result = SeedResult()
    # A new card is due immediately: box 0, due now. Leaving `due_date` null
    # would make it invisible to `build_queue` forever, since that filters on
    # `due_date <= today` -- a freshly seeded install would show an empty queue.
    today = _app_today(session)

    existing = {c.card_id: c for c in session.exec(select(Card)).all()}
    state_ids = {s.card_id for s in session.exec(select(CardState)).all()}

    for row in load_seed_rows(seed_path):
        card = existing.get(row["card_id"])

        if card is None:
            session.add(Card(**row))
            result.created += 1
        elif any(getattr(card, f) != row[f] for f in CARD_CONTENT_FIELDS):
            for f in CARD_CONTENT_FIELDS:
                setattr(card, f, row[f])
            card.deleted = False
            card.updated_at = real_now()
            session.add(card)
            result.updated += 1
        else:
            # Byte-identical to what is already stored. Touching `updated_at`
            # here would push an unchanged row on the next sync.
            result.unchanged += 1

        # State is created once and then left alone -- a re-seed must never
        # reset a card the user has been studying.
        if row["card_id"] not in state_ids:
            session.add(CardState(card_id=row["card_id"], box=0, due_date=today))
            state_ids.add(row["card_id"])
            result.states_created += 1

    session.commit()
    return result
