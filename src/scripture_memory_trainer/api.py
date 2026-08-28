"""The FastAPI application: seven endpoints plus a health check.

Routing only. Every rule lives in ``service.py`` and every calculation in the
pure Phase 1 modules, so a handler here is a translation between HTTP and a
service call -- which is why they are all a few lines long.

Run it with::

    uv run uvicorn scripture_memory_trainer.api:app --reload

The auto-generated docs at ``/docs`` are the Phase 3 exit criterion: the whole
flow -- seed, queue, check, review, travel forward, export, restore -- has to be
drivable there with no frontend at all.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import text
from sqlmodel import Session, func, select

from .database import get_session
from .queue import DAILY_CAP, build_queue
from .schemas import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    CardOut,
    CheckIn,
    CheckOut,
    ClockIn,
    ClockOut,
    ExportOut,
    ImportIn,
    ImportOut,
    Language,
    QueueOut,
    ReviewIn,
    ReviewOut,
    VerdictOut,
)
from .service import (
    app_clock,
    check_answer,
    export_payload,
    get_app_state,
    import_payload,
    joined_cards,
    language_filter_of,
    review_card,
    set_clock,
    to_domain,
)
from .tables import Card, CardState

app = FastAPI(
    title="Scripture Memory Trainer",
    version="0.1.0",
    summary="Leitner spaced repetition for scripture in English, Chinese, Arabic and Hindi.",
    description=(
        "Every date in this API comes from a travellable clock, so a reviewer can "
        "advance the app date and watch the schedule respond. See `/api/clock`."
    ),
)

SessionDep = Annotated[Session, Depends(get_session)]


def _get_card(session: Session, card_id: str) -> Card:
    card = session.get(Card, card_id)
    if card is None or card.deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No card with id {card_id!r}")
    return card


def _card_out(card: Card, state: CardState | None) -> CardOut:
    domain = to_domain(card, state)
    return CardOut(
        card_id=domain.card_id,
        reference=domain.reference,
        language=domain.language,
        direction=domain.direction,
        text=domain.text,
        box=domain.box,
        due_date=domain.due_date,
        updated_at=card.updated_at,
    )


@app.get("/api/health", tags=["meta"])
def health(session: SessionDep) -> dict[str, object]:
    """Liveness plus a real query, so a broken DB URL fails here and not mid-review."""
    session.exec(select(text("1"))).first()
    cards = session.exec(select(func.count()).select_from(Card)).one()
    states = session.exec(select(func.count()).select_from(CardState)).one()
    return {"status": "ok", "cards": cards, "card_states": states}


@app.get("/api/cards", tags=["cards"])
def list_cards(
    session: SessionDep,
    language: Annotated[
        list[Language] | None, Query(description="Repeatable. Omit for every language.")
    ] = None,
    box: Annotated[int | None, Query(ge=0, le=5, description="Leitner box, 0-5")] = None,
    include_deleted: Annotated[
        bool, Query(description="Include tombstoned rows (sync bookkeeping)")
    ] = False,
) -> list[CardOut]:
    """Every card with its review state, filtered. Ordered by reference."""
    rows = joined_cards(
        session,
        languages=list(language) if language else None,
        box=box,
        include_deleted=include_deleted,
    )
    return [_card_out(card, state) for card, state in rows]


@app.get("/api/queue", tags=["review"])
def get_queue(
    session: SessionDep,
    language: Annotated[
        list[Language] | None,
        Query(description="Overrides the stored filter for this request only."),
    ] = None,
) -> QueueOut:
    """Today's queue: due on or before the app date, sorted, capped at 20.

    ``total_due`` is the count **before** the cap, so a client can say
    "20 of 47 due". The app date is whatever the clock offset makes it.
    """
    state = get_app_state(session)
    languages: list[str] | None = (
        [str(code) for code in language] if language else language_filter_of(state)
    )

    today = app_clock(session).today()
    rows = joined_cards(session)
    by_id = {card.card_id: (card, card_state) for card, card_state in rows}

    queue, total = build_queue([to_domain(c, s) for c, s in rows], today, languages)

    return QueueOut(
        app_date=today,
        cards=[_card_out(*by_id[c.card_id]) for c in queue],
        returned=len(queue),
        total_due=total,
        cap=DAILY_CAP,
        language_filter=languages,
    )


@app.post("/api/check", tags=["review"])
def check_endpoint(session: SessionDep, body: CheckIn) -> CheckOut:
    """Check an answer and return the verdict. Changes nothing."""
    card = _get_card(session, body.card_id)
    verdict = check_answer(card, body.answer_text)
    return CheckOut(card_id=card.card_id, language=card.language, verdict=VerdictOut.of(verdict))


@app.post("/api/review", tags=["review"])
def review_endpoint(session: SessionDep, body: ReviewIn) -> ReviewOut:
    """Grade a card: move its box, set the next due date, log the review.

    ``answer_text`` is optional. When present it is checked and the verdict is
    stored alongside the grade; when absent the grade stands on its own.
    """
    card = _get_card(session, body.card_id)
    log, verdict = review_card(session, card, body.grade, body.answer_text)
    return ReviewOut(
        card_id=card.card_id,
        app_date=log.reviewed_on,
        grade=body.grade,
        box_before=log.box_before,
        box_after=log.box_after,
        interval_days=log.interval_days,
        due_date=log.due_date,
        due_today_again=log.due_date <= log.reviewed_on,
        verdict=VerdictOut.of(verdict) if verdict else None,
    )


@app.get("/api/clock", tags=["clock"])
def read_clock(session: SessionDep) -> ClockOut:
    """Where the app clock is now."""
    state = get_app_state(session)
    clock = app_clock(session)
    return ClockOut(
        offset_days=state.offset_days,
        app_date=clock.today(),
        real_date=clock.today() - timedelta(days=state.offset_days),
        language_filter=language_filter_of(state),
    )


@app.post("/api/clock", tags=["clock"])
def write_clock(session: SessionDep, body: ClockIn) -> ClockOut:
    """Move the clock: set the offset, advance by N days, or jump to a date.

    ``offset_days: 0`` is the reset. Passing more than one move is rejected
    rather than silently picking a winner.
    """
    moves = [body.offset_days, body.advance_days, body.target_date]
    if sum(move is not None for move in moves) > 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Pass at most one of offset_days, advance_days, target_date.",
        )
    set_clock(
        session,
        offset_days=body.offset_days,
        advance_days=body.advance_days,
        target_date=body.target_date,
        language_filter=list(body.language_filter) if body.language_filter is not None else None,
    )
    return read_clock(session)


@app.get("/api/export", tags=["backup"])
def export_endpoint(session: SessionDep) -> ExportOut:
    """A complete JSON dump: cards, state, review history, clock. Tombstones included."""
    payload = export_payload(session)
    return ExportOut(
        exported_at=payload["exported_at"],
        app_date=payload["app_date"],
        app_state=payload["app_state"],
        cards=payload["cards"],
        card_states=payload["card_states"],
        review_logs=payload["review_logs"],
    )


@app.post("/api/import", tags=["backup"])
def import_endpoint(session: SessionDep, body: ImportIn) -> ImportOut:
    """Restore an exported document. Merges last-write-wins; safe to repeat.

    A row older than what is already stored is skipped rather than applied, so
    restoring an old backup onto a device that has studied since does not throw
    that work away.
    """
    if body.format != EXPORT_FORMAT:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unrecognised export format {body.format!r}.",
        )
    if body.version > EXPORT_VERSION:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Export version {body.version} is newer than this build understands "
            f"({EXPORT_VERSION}). Upgrade before restoring.",
        )
    counts = import_payload(
        session,
        {
            "app_state": body.app_state,
            "cards": body.cards,
            "card_states": body.card_states,
            "review_logs": body.review_logs,
        },
    )
    return ImportOut.model_validate(counts)
