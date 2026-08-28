"""Hypothesis properties -- the invariants that must hold for inputs nobody wrote by hand.

The fixture suites prove the 8 traces and 21 CHECK cases. These prove the
shapes those examples imply, over arbitrary text and arbitrary grade
sequences. Three properties come straight from the checklist:

1. ``normalize`` is idempotent, in every language.
2. Normalization never increases the word count.
3. The box lands in 0-5 for any grade sequence, of any length.
"""

from __future__ import annotations

from datetime import date, timedelta

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from scripture_memory_trainer.checker import check
from scripture_memory_trainer.normalizer import normalize
from scripture_memory_trainer.scheduler import GRADES, INTERVALS, MAX_BOX, apply_grade, next_due

LANGS = st.sampled_from(["en", "zh", "ar", "hi"])
GRADE = st.sampled_from(GRADES)
BOX = st.integers(min_value=0, max_value=MAX_BOX)

# Arbitrary text, plus text drawn from the scripts the app actually handles, so
# the Arabic and Devanagari branches get exercised rather than only Latin noise.
SCRIPT_TEXT = st.text(
    alphabet=st.characters(
        codec="utf-8",
        include_characters=" \t\n'’“,;.，；،।",
        categories=("Lu", "Ll", "Lo", "Mn", "Nd", "Zs", "Po"),
    ),
    max_size=120,
)
ANY_TEXT = st.text(max_size=120)
TEXT = st.one_of(SCRIPT_TEXT, ANY_TEXT)


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


@given(text=TEXT, lang=LANGS)
def test_normalize_is_idempotent(text: str, lang: str) -> None:
    once = normalize(text, lang)
    assert normalize(once, lang) == once


@given(text=TEXT, lang=LANGS)
def test_normalize_never_increases_the_word_count(text: str, lang: str) -> None:
    assert len(normalize(text, lang).split()) <= len(text.split())


@given(text=TEXT, lang=LANGS)
def test_normalize_output_has_no_outer_or_repeated_whitespace(text: str, lang: str) -> None:
    out = normalize(text, lang)
    assert out == out.strip()
    assert "  " not in out


@given(text=TEXT, lang=LANGS)
def test_normalize_output_is_case_folded(text: str, lang: str) -> None:
    out = normalize(text, lang)
    assert out == out.casefold()


@given(text=TEXT, lang=LANGS)
def test_normalize_is_deterministic(text: str, lang: str) -> None:
    assert normalize(text, lang) == normalize(text, lang)


@given(text=TEXT, lang=LANGS)
def test_padding_and_case_never_change_the_result(text: str, lang: str) -> None:
    assert normalize(f"  {text}  ", lang) == normalize(text, lang)
    assert normalize(text.upper(), lang) == normalize(text.upper().casefold(), lang)


@given(text=TEXT, lang=LANGS)
def test_a_card_always_matches_itself(text: str, lang: str) -> None:
    """Whatever the script, a verbatim answer is Correct -- unless it normalizes away."""
    assume(normalize(text, lang) != "")
    verdict = check(text, text, lang)
    assert verdict.status == "correct"
    assert verdict.matched == verdict.total
    assert verdict.mismatch_positions == []
    assert verdict.missing_from is None


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


@given(card=TEXT, answer=TEXT, lang=LANGS)
def test_verdict_counts_are_internally_consistent(card: str, answer: str, lang: str) -> None:
    # A card that normalizes to nothing has no units to compare; every real card
    # in B_Cards has text (tests/test_fixtures.py pins that).
    assume(normalize(card, lang) != "")
    verdict = check(card, answer, lang)
    assert 0 <= verdict.matched <= verdict.total
    assert len(verdict.mismatch_positions) <= verdict.total
    assert all(1 <= p <= verdict.total for p in verdict.mismatch_positions)
    assert verdict.missing_count <= verdict.total
    if verdict.missing_from is not None:
        assert 1 <= verdict.missing_from <= verdict.total
    assert verdict.status in {"correct", "partial", "incorrect"}
    assert (verdict.status == "incorrect") == (verdict.matched == 0)


@given(card=TEXT, answer=TEXT, lang=LANGS)
def test_matched_plus_mismatched_plus_missing_covers_the_card(
    card: str, answer: str, lang: str
) -> None:
    assume(normalize(card, lang) != "")
    verdict = check(card, answer, lang)
    if verdict.status == "correct":
        assert verdict.matched == verdict.total
        return
    assert (
        verdict.matched + len(verdict.mismatch_positions) + verdict.missing_count == verdict.total
    )


@given(card=TEXT, answer=TEXT, lang=LANGS)
def test_a_partial_verdict_always_reports_something_actionable(
    card: str, answer: str, lang: str
) -> None:
    """A Partial the UI cannot explain is a bug, not a verdict.

    The fixture-driven version of this check only ever sees the 21 CHECK cases.
    As a property it also covers the zh spacing case of DECISIONS D12, where a
    fully correct answer used to come back Partial with nothing to show.
    """
    assume(normalize(card, lang) != "")
    verdict = check(card, answer, lang)
    if verdict.status == "partial":
        assert verdict.mismatch_positions or verdict.missing_count or verdict.surplus_count


@given(card=TEXT, answer=TEXT, lang=LANGS)
def test_correct_means_every_unit_matched_and_nothing_left_over(
    card: str, answer: str, lang: str
) -> None:
    """The other half: Correct is exactly "all units matched, none extra"."""
    assume(normalize(card, lang) != "")
    verdict = check(card, answer, lang)
    if verdict.status == "correct":
        assert verdict.matched == verdict.total
        assert verdict.mismatch_positions == []
        assert verdict.missing_count == verdict.surplus_count == 0
        assert verdict.missing_from is verdict.surplus_from is None


@given(text=TEXT, gaps=st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=12))
def test_spacing_is_not_a_unit_for_character_languages(text: str, gaps: list[int]) -> None:
    """zh compares characters, so whitespace between them cannot change the verdict.

    Drawing card and answer independently will not find this -- the answer has
    to be built from the card. This is the property that pins DECISIONS D12.
    """
    card = normalize(text, "zh")
    chars = card.replace(" ", "")
    assume(chars != "")
    answer = "".join(ch + " " * gaps[i % len(gaps)] for i, ch in enumerate(chars))

    verdict = check(card, answer, "zh")
    assert verdict.status == "correct"
    assert verdict.matched == verdict.total
    assert verdict.mismatch_positions == []


@given(card=TEXT, answer=TEXT, lang=LANGS)
def test_check_ignores_case_and_outer_whitespace_in_the_answer(
    card: str, answer: str, lang: str
) -> None:
    baseline = check(card, answer, lang)
    padded = check(card, f"  {answer}  ", lang)
    assert (padded.status, padded.matched, padded.total) == (
        baseline.status,
        baseline.matched,
        baseline.total,
    )


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


@given(grades=st.lists(GRADE, min_size=1, max_size=60), start=BOX)
@settings(max_examples=300)
def test_box_always_lands_between_zero_and_five(grades: list[str], start: int) -> None:
    box = start
    for grade in grades:
        box, interval = apply_grade(box, grade)
        assert 0 <= box <= MAX_BOX
        assert interval >= 0


@given(grades=st.lists(GRADE, min_size=1, max_size=60))
def test_the_due_date_never_moves_backwards(grades: list[str]) -> None:
    box, due = 0, date(2026, 9, 1)
    for grade in grades:
        box, interval = apply_grade(box, grade)
        moved = next_due(due, interval)
        assert moved >= due
        due = moved


@given(box=BOX, grade=GRADE)
def test_only_again_can_give_a_zero_interval(box: int, grade: str) -> None:
    _, interval = apply_grade(box, grade)
    assert (interval == 0) == (grade == "again")


@given(box=BOX, grade=GRADE)
def test_a_passing_grade_never_demotes_a_card(box: int, grade: str) -> None:
    assume(grade != "again")
    new_box, _ = apply_grade(box, grade)
    assert new_box >= box


@given(box=BOX)
def test_easy_never_lands_below_good(box: int) -> None:
    assert apply_grade(box, "easy")[0] >= apply_grade(box, "good")[0]


@given(box=BOX, grade=GRADE)
def test_the_interval_is_always_one_of_the_defined_shapes(box: int, grade: str) -> None:
    _, interval = apply_grade(box, grade)
    allowed = set(INTERVALS.values()) | {max(1, INTERVALS[b] * 60 // 100) for b in INTERVALS}
    assert interval in allowed


@given(review=st.dates(), interval=st.integers(min_value=0, max_value=60))
def test_next_due_is_pure_addition(review: date, interval: int) -> None:
    assert next_due(review, interval) == review + timedelta(days=interval)
