"""The FastAPI application.

Phase 3 initialisation: the app, its metadata, and the health endpoint that
proves the database is reachable. The seven business endpoints
(``/api/cards``, ``/api/queue``, ``/api/review``, ``/api/check``,
``/api/clock``, ``/api/export``, ``/api/import``) are the remaining Phase 3
checklist items and land on top of this.

Run it with::

    uv run uvicorn scripture_memory_trainer.api:app --reload

The auto-generated docs are the Phase 3 exit criterion -- the whole flow has to
be drivable from ``/docs`` with no frontend at all.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlmodel import Session, func, select

from .database import get_session
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


@app.get("/api/health", tags=["meta"])
def health(session: SessionDep) -> dict[str, object]:
    """Liveness plus a real query, so a broken DB URL fails here and not mid-review."""
    session.exec(select(text("1"))).first()
    cards = session.exec(select(func.count()).select_from(Card)).one()
    states = session.exec(select(func.count()).select_from(CardState)).one()
    return {"status": "ok", "cards": cards, "card_states": states}
