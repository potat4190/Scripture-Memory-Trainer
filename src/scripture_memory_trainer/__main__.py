"""``python -m scripture_memory_trainer`` -- load the seed into the database.

A module entry point rather than a console script: it works straight after
``uv sync`` with no reinstall step, which matters because seeding is the one
command a deploy has to run after ``alembic upgrade head``. Idempotent, so
running it on every deploy is fine.

Kept out of ``__init__.py`` on purpose -- importing the package must not drag in
SQLAlchemy, and this needs it.
"""

from __future__ import annotations

from sqlmodel import Session

from .database import database_url, make_engine
from .seed import seed_cards


def main() -> None:
    """Import ``seed/cards.json`` into the configured database and report what changed."""
    engine = make_engine()
    try:
        with Session(engine) as session:
            result = seed_cards(session)
    finally:
        engine.dispose()

    print(f"Seeded {database_url()}")
    print(
        f"  cards: {result.created} created, {result.updated} updated, {result.unchanged} unchanged"
    )
    print(f"  review state rows created: {result.states_created}")


if __name__ == "__main__":
    main()
