"""The guard rails Phase 1 of the checklist calls out by name.

Not the Phase 2 suite (parametrized fixtures + Hypothesis) -- just the specific
invariants the checklist says to pin down now so nobody "fixes" them later.
"""

from __future__ import annotations

from datetime import date

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
