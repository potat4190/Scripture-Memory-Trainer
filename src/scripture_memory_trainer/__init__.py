"""Scripture Memory Trainer -- pure logic for spaced-repetition scripture drill.

The five Phase 1 modules (``clock``, ``scheduler``, ``normalizer``, ``checker``,
``queue``) do no I/O and import no framework. ``models`` holds the one shared
data type; ``storage`` is a separate, deliberately-impure JSON helper that
prototypes the Phase 3 seed loader and export (see ``docs/DECISIONS.md`` D9).
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
