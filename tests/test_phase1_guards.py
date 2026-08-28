"""The guard rails Phase 1 of the checklist calls out by name.

Not the Phase 2 suite (parametrized fixtures + Hypothesis) -- just the specific
invariants the checklist says to pin down now so nobody "fixes" them later.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from scripture_memory_trainer.models import Card
from scripture_memory_trainer.normalizer import normalize
from scripture_memory_trainer.queue import build_queue
from scripture_memory_trainer.scheduler import apply_grade


def test_chinese_traditional_is_not_folded_to_simplified() -> None:
    # 愛 (traditional) must NOT normalize to 爱 (simplified). This is a rule.
    assert normalize("神愛世人", "zh") != normalize("神爱世人", "zh")


def test_normalizer_uses_regex_unicode_punctuation() -> None:
    # Arabic comma U+060C and Devanagari danda U+0964 are punctuation and must go.
    assert normalize("a،b", "ar") == "ab"
    assert normalize("क।ख", "hi") == normalize("कख", "hi")


def test_hard_on_box_zero_advances_one_day_and_keeps_box() -> None:
    assert apply_grade(0, "hard") == (0, 1)


def test_hard_floors_and_does_not_round() -> None:
    # Box 4: 21 * 60 // 100 == 12, not 13.
    assert apply_grade(4, "hard") == (4, 12)


def test_queue_sorts_reference_as_string_not_canonical_book_order() -> None:
    today = date(2026, 9, 1)
    cards = [
        Card("a", "Leviticus 19:34", "en", "ltr", "x", box=0, due_date=today),
        Card("b", "John 3:16", "en", "ltr", "x", box=0, due_date=today),
    ]
    queue, total = build_queue(cards, today)
    assert [c.reference for c in queue] == ["John 3:16", "Leviticus 19:34"]
    assert total == 2


def test_queue_caps_at_twenty_and_reports_pre_cap_total() -> None:
    today = date(2026, 9, 1)
    cards = [
        Card(f"c{i:02d}", f"Ref {i:02d}", "en", "ltr", "x", box=0, due_date=today)
        for i in range(25)
    ]
    queue, total = build_queue(cards, today)
    assert len(queue) == 20
    assert total == 25


# ---------------------------------------------------------------------------
# Phase 1's exit criterion, now that Phase 3 has put a DB driver in the package
# ---------------------------------------------------------------------------

SRC = Path(__file__).resolve().parent.parent / "src" / "scripture_memory_trainer"

# "five modules, no imports of FastAPI or any DB driver" -- plus `models`, which
# they import, so it is bound by the same rule (DECISIONS D13).
PURE_MODULES = ["clock", "scheduler", "normalizer", "checker", "queue", "models"]

FORBIDDEN_ROOTS = {"fastapi", "sqlmodel", "sqlalchemy", "alembic", "psycopg", "starlette"}


def imported_roots(module: str) -> set[str]:
    """Every top-level package `module` imports, read statically from its source."""
    tree = ast.parse((SRC / f"{module}.py").read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("module", PURE_MODULES)
def test_the_pure_modules_import_no_framework_or_db_driver(module: str) -> None:
    """Phase 1's exit criterion, enforced rather than trusted.

    Putting the SQLModel tables in `models.py` -- which the checklist's Phase 3
    line literally says to do -- would break this through `queue.py`'s import of
    `models`. That is why the tables live in `tables.py` instead.
    """
    offenders = imported_roots(module) & FORBIDDEN_ROOTS
    assert offenders == set(), f"{module}.py imports {sorted(offenders)}"


@pytest.mark.parametrize("module", PURE_MODULES)
def test_the_pure_modules_do_not_pull_in_a_db_driver_transitively(module: str) -> None:
    """A static import check misses re-exports, so import the module for real.

    In a **clean interpreter**: by the time this runs, the rest of the suite has
    already loaded SQLModel into the current one, which would make an in-process
    check pass vacuously.
    """
    code = (
        "import sys, scripture_memory_trainer." + module + "; "
        "print(sorted({n.split('.')[0] for n in sys.modules} & " + repr(FORBIDDEN_ROOTS) + "))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]", (
        f"{module}.py transitively imports {result.stdout.strip()}"
    )


def test_only_clock_reaches_for_the_real_time() -> None:
    """The checklist's "grep the whole repo" item, as a test.

    `date.today()` and `datetime.now()` may appear in `clock.py` and nowhere
    else in `src/` -- that is what makes time travel total.
    """
    offenders = []
    for path in sorted(SRC.glob("*.py")):
        if path.name == "clock.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            target = node.func.value
            if (
                node.func.attr in {"today", "now"}
                and isinstance(target, ast.Name)
                and target.id in {"date", "datetime"}
            ):
                offenders.append(f"{path.name}:{node.lineno} {target.id}.{node.func.attr}()")
    assert offenders == [], f"only clock.py may read the real time; found {offenders}"
