"""The scheduler against all 8 traces of ``B_Check_Schedule``.

Two layers of assertion per trace:

1. **Step by step.** The workbook spells each trace out in prose --
   ``good→box1, +1d, due 2026-09-02 | ...``. That prose is parsed and every
   intermediate box, interval and due date is checked, so a trace that arrives
   at the right answer by the wrong route still fails.
2. **End state.** ``expected_box`` and ``expected_due`` from the fixture.

Parsing the prose rather than retyping its numbers keeps the workbook as the
single source of truth -- the same reason the fixtures are extracted and not
hand-written.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, NamedTuple

import pytest
import regex as re

from scripture_memory_trainer.scheduler import GRADES, INTERVALS, MAX_BOX, apply_grade, next_due

from .conftest import load_schedule_traces

TRACES = load_schedule_traces()

_STEP_RE = re.compile(
    r"(?P<grade>again|hard|good|easy)\s*→\s*box(?P<box>\d+),\s*"
    r"\+(?P<interval>\d+)d,\s*due\s*(?P<due>\d{4}-\d{2}-\d{2})"
)


class Step(NamedTuple):
    grade: str
    box: int
    interval: int
    due: date


def parse_steps(trace: str) -> list[Step]:
    """Pull the per-step expectations out of the workbook's trace prose."""
    return [
        Step(
            grade=m["grade"],
            box=int(m["box"]),
            interval=int(m["interval"]),
            due=date.fromisoformat(m["due"]),
        )
        for m in _STEP_RE.finditer(trace)
    ]


def _ids(traces: list[dict[str, Any]]) -> list[str]:
    return [f"trace{t['id']}-{'-'.join(t['grades'])}" for t in traces]


@pytest.mark.parametrize("trace", TRACES, ids=_ids(TRACES))
def test_trace_reaches_the_expected_box_and_due_date(trace: dict[str, Any]) -> None:
    box: int = trace["start_box"]
    due = date.fromisoformat(trace["start_date"])

    for grade in trace["grades"]:
        box, interval = apply_grade(box, grade)
        due = next_due(due, interval)

    assert box == trace["expected_box"]
    assert due.isoformat() == trace["expected_due"]


@pytest.mark.parametrize("trace", TRACES, ids=_ids(TRACES))
def test_trace_matches_step_by_step(trace: dict[str, Any]) -> None:
    steps = parse_steps(trace["trace"])
    assert [s.grade for s in steps] == trace["grades"], "trace prose disagrees with grades[]"

    box: int = trace["start_box"]
    due = date.fromisoformat(trace["start_date"])

    for n, step in enumerate(steps, start=1):
        box, interval = apply_grade(box, step.grade)
        due = next_due(due, interval)
        assert box == step.box, f"step {n} ({step.grade}): box"
        assert interval == step.interval, f"step {n} ({step.grade}): interval"
        assert due == step.due, f"step {n} ({step.grade}): due date"


def test_every_trace_step_was_actually_parsed() -> None:
    """Guard the parser itself: a regex that matched nothing would pass vacuously."""
    for trace in TRACES:
        steps = parse_steps(trace["trace"])
        assert len(steps) == len(trace["grades"]) > 0


@pytest.mark.parametrize("box", sorted(INTERVALS))
def test_again_resets_to_box_zero_with_a_zero_interval(box: int) -> None:
    assert apply_grade(box, "again") == (0, 0)


@pytest.mark.parametrize("box", sorted(INTERVALS))
def test_hard_keeps_the_box_and_floors_sixty_percent_of_its_own_interval(box: int) -> None:
    new_box, interval = apply_grade(box, "hard")
    assert new_box == box, "hard must not move the card between boxes"
    assert interval == max(1, INTERVALS[box] * 60 // 100)
    assert interval >= 1, "hard always advances the due date by at least a day"


@pytest.mark.parametrize(
    ("box", "expected"),
    [(0, 1), (1, 1), (2, 1), (3, 4), (4, 12), (5, 36)],
)
def test_hard_intervals_are_floored_not_rounded(box: int, expected: int) -> None:
    # 7 * 0.6 == 4.2 -> 4; 21 * 0.6 == 12.6 -> 12 (not 13); 60 * 0.6 == 36.
    assert apply_grade(box, "hard")[1] == expected


@pytest.mark.parametrize("box", sorted(INTERVALS))
def test_good_advances_one_box_and_uses_the_new_boxs_interval(box: int) -> None:
    new_box, interval = apply_grade(box, "good")
    assert new_box == min(MAX_BOX, box + 1)
    assert interval == INTERVALS[new_box]


@pytest.mark.parametrize("box", sorted(INTERVALS))
def test_easy_advances_two_boxes_and_uses_the_new_boxs_interval(box: int) -> None:
    new_box, interval = apply_grade(box, "easy")
    assert new_box == min(MAX_BOX, box + 2)
    assert interval == INTERVALS[new_box]


def test_box_five_is_the_ceiling() -> None:
    assert apply_grade(5, "good")[0] == MAX_BOX
    assert apply_grade(5, "easy")[0] == MAX_BOX
    assert apply_grade(4, "easy")[0] == MAX_BOX


def test_unknown_grade_raises() -> None:
    with pytest.raises(ValueError, match="unknown grade"):
        apply_grade(0, "brilliant")


def test_grades_tuple_matches_the_implemented_branches() -> None:
    assert set(GRADES) == {"again", "hard", "good", "easy"}
    for grade in GRADES:
        apply_grade(0, grade)  # must not raise


@pytest.mark.parametrize("interval", [0, 1, 3, 7, 21, 60])
def test_next_due_is_review_date_plus_interval(interval: int) -> None:
    review = date(2026, 9, 1)
    assert next_due(review, interval) == review + timedelta(days=interval)


def test_again_leaves_the_card_due_the_same_day() -> None:
    """interval 0 means the card comes back in today's queue, not tomorrow's."""
    review = date(2026, 9, 1)
    _, interval = apply_grade(3, "again")
    assert next_due(review, interval) == review
