"""Phase 0 exit criterion: the extracted spec fixtures exist and load.

No application logic is imported here — this only proves the acceptance data
extracted from the workbook (`B_Cards`, `B_Check_Schedule`, `B_Check_Answers`)
is present and well-formed. The logic that consumes it arrives in Phase 1/2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SEED = ROOT / "seed"

VALID_LANGS = {"en", "zh", "ar", "hi"}
VALID_GRADES = {"again", "hard", "good", "easy"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cards_seed_loads() -> None:
    cards = _load(SEED / "cards.json")
    assert len(cards) == 32
    for card in cards:
        assert set(card) == {"card_id", "reference", "language", "direction", "text"}
        assert card["language"] in VALID_LANGS
        assert card["direction"] in {"ltr", "rtl"}
        assert card["text"]
    assert len({c["card_id"] for c in cards}) == 32


def test_check_schedule_loads() -> None:
    traces = _load(FIXTURES / "check_schedule.json")
    assert len(traces) == 8
    for trace in traces:
        assert {"grades", "expected_box", "expected_due"} <= set(trace)
        assert trace["grades"]
        assert set(trace["grades"]) <= VALID_GRADES
        assert 0 <= trace["expected_box"] <= 5
        assert trace["expected_due"].count("-") == 2


def test_check_answers_loads() -> None:
    # The workbook header claims 22 rows; the supplied markdown export contains 21.
    # See docs/DECISIONS.md.
    cases = _load(FIXTURES / "check_answers.json")
    assert len(cases) == 21
    for case in cases:
        assert {"reference", "lang", "input", "expected_verdict"} <= set(case)
        assert case["lang"] in VALID_LANGS
        assert isinstance(case["input"], str)
        assert case["expected_verdict"]
