"""Scripture Memory Trainer -- spaced-repetition scripture drill.

The six pure modules (``clock``, ``scheduler``, ``normalizer``, ``checker``,
``queue``, ``models``) do no I/O and import no framework, and
``tests/test_phase1_guards.py`` enforces that in a subprocess. Everything impure
sits outside them: ``tables`` and ``database`` for persistence, ``seed`` for the
card import, ``service`` for the rules the API applies, ``api`` for the HTTP
layer, and ``__main__`` for the seed command.

Only the pure logic is re-exported here, so importing the package never drags in
SQLAlchemy or FastAPI.
"""

from __future__ import annotations

from .checker import Verdict, check
from .clock import Clock
from .models import Card
from .normalizer import normalize
from .queue import build_queue
from .scheduler import apply_grade, next_due

__all__ = [
    "Card",
    "Clock",
    "Verdict",
    "apply_grade",
    "build_queue",
    "check",
    "next_due",
    "normalize",
]
