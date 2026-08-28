"""Everything the API does to the database, kept out of the routing layer.

``api.py`` translates HTTP to these calls and back; the rules live here. That
split is what lets the endpoint tests read like the checklist and keeps the
route handlers to a few lines each.

Nothing in this module calls ``date.today()``. The app date always comes from a
``Clock`` built from the persisted offset (``app_clock``), which is what makes
time travel work end to end rather than only in the pure logic.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlmodel import Session, col, select

from .checker import Verdict, check
from .clock import Clock, real_now
from .models import Card as DomainCard
from .scheduler import apply_grade, next_due
from .tables import APP_STATE_ID, AppState, Card, CardState, ReviewLog

CARD_CONTENT_FIELDS = ("reference", "language", "direction", "text")


# ---------------------------------------------------------------------------
# App state and the clock
# ---------------------------------------------------------------------------


def get_app_state(session: Session) -> AppState:
    """The single ``AppState`` row, created on first use."""
    state = session.get(AppState, APP_STATE_ID)
    if state is None:
        state = AppState(id=APP_STATE_ID)
        session.add(state)
        session.commit()
        session.refresh(state)
    return state


def app_clock(session: Session) -> Clock:
    """A ``Clock`` carrying the persisted offset -- the only source of "today"."""
    return Clock(offset_days=get_app_state(session).offset_days)


def language_filter_of(state: AppState) -> list[str] | None:
    """The stored filter as a list. Null and empty both mean "every language"."""
    if not state.language_filter:
        return None
    return state.language_filter.split(",")


def set_clock(
    session: Session,
    *,
    offset_days: int | None = None,
    advance_days: int | None = None,
    target_date: date | None = None,
    language_filter: list[str] | None = None,
) -> AppState:
    """Apply one clock move, and optionally the language filter, then persist."""
    state = get_app_state(session)
    clock = Clock(offset_days=state.offset_days)

    if target_date is not None:
        clock.jump_to(target_date)
    elif advance_days is not None:
        clock.advance(advance_days)
    elif offset_days is not None:
        clock.offset_days = offset_days

    state.offset_days = clock.offset_days
    if language_filter is not None:
        state.language_filter = ",".join(language_filter) or None
    state.updated_at = real_now()

    session.add(state)
    session.commit()
    session.refresh(state)
    return state


# ---------------------------------------------------------------------------
# Reading cards
# ---------------------------------------------------------------------------


def _state_for(session: Session, card_id: str) -> CardState:
    """The card's review state, created at box 0 / due now if it has none yet."""
    state = session.get(CardState, card_id)
    if state is None:
        state = CardState(card_id=card_id, box=0, due_date=app_clock(session).today())
        session.add(state)
        session.commit()
        session.refresh(state)
    return state


def joined_cards(
    session: Session,
    *,
    languages: list[str] | None = None,
    box: int | None = None,
    include_deleted: bool = False,
) -> list[tuple[Card, CardState | None]]:
    """Cards with their state attached, filtered and ordered by reference."""
    statement = select(Card, CardState).join(
        CardState, onclause=col(Card.card_id) == col(CardState.card_id), isouter=True
    )
    if not include_deleted:
        statement = statement.where(col(Card.deleted).is_(False))
    if languages:
        statement = statement.where(col(Card.language).in_(languages))
    if box is not None:
        statement = statement.where(col(CardState.box) == box)

    rows: list[tuple[Card, CardState | None]] = list(session.exec(statement).all())
    return sorted(rows, key=lambda row: row[0].reference)


def to_domain(card: Card, state: CardState | None) -> DomainCard:
    """The pure-logic view of a stored card. This is the D13 boundary."""
    return DomainCard(
        card_id=card.card_id,
        reference=card.reference,
        language=card.language,
        direction=card.direction,
        text=card.text,
        box=state.box if state else 0,
        due_date=state.due_date if state else None,
    )


# ---------------------------------------------------------------------------
# Checking and reviewing
# ---------------------------------------------------------------------------


def check_answer(card: Card, answer_text: str) -> Verdict:
    """Run the checker. No state is touched -- that is the point of `/api/check`."""
    return check(card.text, answer_text, card.language)


def review_card(
    session: Session, card: Card, grade: str, answer_text: str | None = None
) -> tuple[ReviewLog, Verdict | None]:
    """Grade a card: move its box, set the next due date, and log the review."""
    today = app_clock(session).today()
    state = _state_for(session, card.card_id)

    verdict = check_answer(card, answer_text) if answer_text is not None else None

    box_before = state.box
    box_after, interval_days = apply_grade(box_before, grade)
    due = next_due(today, interval_days)

    state.box = box_after
    state.due_date = due
    state.deleted = False
    state.updated_at = real_now()
    session.add(state)

    log = ReviewLog(
        card_id=card.card_id,
        reviewed_on=today,
        grade=grade,
        box_before=box_before,
        box_after=box_after,
        interval_days=interval_days,
        due_date=due,
        answer_text=answer_text,
        verdict_status=verdict.status if verdict else None,
        matched=verdict.matched if verdict else None,
        total=verdict.total if verdict else None,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log, verdict


# ---------------------------------------------------------------------------
# Export and import
# ---------------------------------------------------------------------------


def _row_dict(row: Card | CardState | ReviewLog | AppState) -> dict[str, Any]:
    """A JSON-ready dict of a row, dates as ISO strings."""
    out: dict[str, Any] = {}
    for name in type(row).model_fields:
        value = getattr(row, name)
        out[name] = value.isoformat() if isinstance(value, date | datetime) else value
    return out


def export_payload(session: Session) -> dict[str, Any]:
    """Every row, tombstones included, in one self-contained document."""
    state = get_app_state(session)
    return {
        "exported_at": real_now(),
        "app_date": app_clock(session).today(),
        "app_state": _row_dict(state),
        "cards": [_row_dict(c) for c in session.exec(select(Card)).all()],
        "card_states": [_row_dict(s) for s in session.exec(select(CardState)).all()],
        "review_logs": [_row_dict(r) for r in session.exec(select(ReviewLog)).all()],
    }


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


def _as_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


def _wins(incoming: dict[str, Any], stored_updated_at: datetime) -> bool:
    """Last-write-wins: an incoming row applies only if it is strictly newer.

    An incoming row with no timestamp loses, rather than silently overwriting
    with an unknown age. Ties lose too -- re-importing the same file is a no-op,
    which is what makes import safe to retry.
    """
    incoming_at = _as_datetime(incoming.get("updated_at"))
    if incoming_at is None:
        return False
    if incoming_at.tzinfo is None:
        incoming_at = incoming_at.replace(tzinfo=stored_updated_at.tzinfo)
    return incoming_at > stored_updated_at


def import_payload(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Merge an exported document back in, last-write-wins, tombstones honoured.

    Merge rather than replace: restoring onto a device that has studied since
    the export must not throw that work away. Re-importing the same file changes
    nothing (see ``_wins``), so a nervous user can press it twice.
    """
    counts = dict.fromkeys(
        (
            "cards_created",
            "cards_updated",
            "cards_skipped",
            "states_created",
            "states_updated",
            "states_skipped",
            "review_logs_created",
            "review_logs_skipped",
        ),
        0,
    )
    app_state_updated = False

    for row in payload.get("cards") or []:
        card_id = str(row["card_id"])
        stored = session.get(Card, card_id)
        if stored is None:
            session.add(
                Card(
                    card_id=card_id,
                    reference=str(row["reference"]),
                    language=str(row["language"]),
                    direction=str(row["direction"]),
                    text=str(row["text"]),
                    deleted=bool(row.get("deleted", False)),
                    updated_at=_as_datetime(row.get("updated_at")) or real_now(),
                )
            )
            counts["cards_created"] += 1
        elif _wins(row, stored.updated_at):
            for field in CARD_CONTENT_FIELDS:
                setattr(stored, field, str(row[field]))
            stored.deleted = bool(row.get("deleted", False))
            stored.updated_at = _as_datetime(row.get("updated_at")) or real_now()
            session.add(stored)
            counts["cards_updated"] += 1
        else:
            counts["cards_skipped"] += 1

    # A state or log whose card is not in the payload and not already stored
    # would violate the foreign key. SQLite does not enforce it by default and
    # Postgres does, so an import that "worked" locally would 500 in production.
    # Skip the orphan instead, on both.
    known_cards = {card.card_id for card in session.exec(select(Card)).all()}
    known_cards.update(str(row["card_id"]) for row in payload.get("cards") or [])

    for row in payload.get("card_states") or []:
        card_id = str(row["card_id"])
        if card_id not in known_cards:
            counts["states_skipped"] += 1
            continue
        stored_state = session.get(CardState, card_id)
        if stored_state is None:
            session.add(
                CardState(
                    card_id=card_id,
                    box=int(row.get("box", 0)),
                    due_date=_as_date(row.get("due_date")),
                    deleted=bool(row.get("deleted", False)),
                    updated_at=_as_datetime(row.get("updated_at")) or real_now(),
                )
            )
            counts["states_created"] += 1
        elif _wins(row, stored_state.updated_at):
            stored_state.box = int(row.get("box", 0))
            stored_state.due_date = _as_date(row.get("due_date"))
            stored_state.deleted = bool(row.get("deleted", False))
            stored_state.updated_at = _as_datetime(row.get("updated_at")) or real_now()
            session.add(stored_state)
            counts["states_updated"] += 1
        else:
            counts["states_skipped"] += 1

    existing_logs = {
        (log.card_id, log.reviewed_on, log.grade, log.box_before, log.box_after)
        for log in session.exec(select(ReviewLog)).all()
    }
    for row in payload.get("review_logs") or []:
        if str(row["card_id"]) not in known_cards:
            counts["review_logs_skipped"] += 1
            continue
        reviewed_on = _as_date(row.get("reviewed_on"))
        due_date = _as_date(row.get("due_date"))
        if reviewed_on is None or due_date is None:
            counts["review_logs_skipped"] += 1
            continue
        key = (
            str(row["card_id"]),
            reviewed_on,
            str(row["grade"]),
            int(row["box_before"]),
            int(row["box_after"]),
        )
        # The log is append-only history, so identity is the review itself, not
        # a database id that differs between devices.
        if key in existing_logs:
            counts["review_logs_skipped"] += 1
            continue
        session.add(
            ReviewLog(
                card_id=str(row["card_id"]),
                reviewed_on=reviewed_on,
                grade=str(row["grade"]),
                box_before=int(row["box_before"]),
                box_after=int(row["box_after"]),
                interval_days=int(row["interval_days"]),
                due_date=due_date,
                answer_text=row.get("answer_text"),
                verdict_status=row.get("verdict_status"),
                matched=row.get("matched"),
                total=row.get("total"),
                deleted=bool(row.get("deleted", False)),
                updated_at=_as_datetime(row.get("updated_at")) or real_now(),
            )
        )
        existing_logs.add(key)
        counts["review_logs_created"] += 1

    incoming_state = payload.get("app_state")
    if incoming_state:
        # `session.get`, not `get_app_state`: creating the default row here would
        # stamp it with `real_now()` and that fresh timestamp would then beat the
        # incoming one, silently dropping the clock offset on a restore into an
        # empty database -- the most common restore there is.
        stored_app = session.get(AppState, APP_STATE_ID)
        if stored_app is None:
            session.add(
                AppState(
                    id=APP_STATE_ID,
                    offset_days=int(incoming_state.get("offset_days", 0)),
                    language_filter=incoming_state.get("language_filter"),
                    updated_at=_as_datetime(incoming_state.get("updated_at")) or real_now(),
                )
            )
            app_state_updated = True
        elif _wins(incoming_state, stored_app.updated_at):
            stored_app.offset_days = int(incoming_state.get("offset_days", 0))
            stored_app.language_filter = incoming_state.get("language_filter")
            stored_app.updated_at = _as_datetime(incoming_state.get("updated_at")) or real_now()
            session.add(stored_app)
            app_state_updated = True

    session.commit()
    return {**counts, "app_state_updated": app_state_updated}
