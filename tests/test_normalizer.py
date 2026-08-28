"""Normalization and answer checking against all 21 cases of ``B_Check_Answers``.

The checklist names this file for the CHECK cases, and each case is an
end-to-end assertion: card text and user input both go through ``normalize``
and are compared by ``check``. The rule-by-rule normalizer tests come first;
the fixture-driven cases follow.

**On the count:** the checklist says 22 cases; the sheet holds 21 data rows.
See ``docs/DECISIONS.md`` D1.

**Expected values are parsed from the workbook's own prose**, not retyped.
``B_Check_Answers`` states verdicts like "Partial. 7 of 10 words matched; 3
missing from position 8." -- every number in that sentence is extracted and
asserted, so the tests check the counts and positions, not just the
correct/partial/incorrect label.

**Three cases are known to deviate** and are marked ``xfail(strict=True)``:
ids 6 and 7 on their counts (D5) and id 10 on its status (D10). Strict xfail
means that if someone "fixes" the checker to reproduce the workbook's numbers,
these turn into failures rather than passing silently -- which is exactly the
outcome the checklist warns against.
"""

from __future__ import annotations

from typing import Any, TypedDict

import pytest
import regex as re

from scripture_memory_trainer.checker import Verdict, check
from scripture_memory_trainer.normalizer import normalize

from .conftest import CaseResult, CheckReport, load_answer_cases, load_seed_cards

CASES = load_answer_cases()
CARDS = load_seed_cards()

# Case ids whose *status* disagrees with the workbook, and why.
STATUS_DEVIATIONS = {
    10: "D10 -- traditional zh shares 23 of 30 chars with the simplified card, "
    "so the rules give Partial where the workbook says Incorrect",
}
# Case ids whose *counts* disagree with the workbook, and why.
COUNT_DEVIATIONS = {
    6: "D5 -- B_Cards gives 24 words, so Father's is at position 15, not 16",
    7: "D5 -- B_Cards gives 24 words, not the 22 the workbook counted",
}


class Expectation(TypedDict, total=False):
    status: str
    matched: int
    total: int
    wrong_count: int
    wrong_position: int
    missing_count: int
    missing_from: int
    unit: str


# The workbook says "words" / "characters"; ``Verdict.unit`` says "words" / "chars".
_UNIT_NAMES = {"words": "words", "characters": "chars"}

_MATCHED_RE = re.compile(r"(?P<matched>\d+) of (?P<total>\d+) (?P<unit>words|characters) matched")
_WRONG_OF_RE = re.compile(
    r"(?P<count>\d+) of (?P<total>\d+) (?P<unit>words|characters) wrong"
    r"(?: at position (?P<pos>\d+))?"
)
_WRONG_RE = re.compile(
    r"(?P<count>\d+) (?P<unit>word|character)s? wrong(?: at position (?P<pos>\d+))?"
)
_MISSING_RE = re.compile(r"(?P<count>\d+) missing from position (?P<pos>\d+)")


def parse_expectation(prose: str) -> Expectation:
    """Extract every number the workbook's verdict sentence states."""
    exp: Expectation = {"status": prose.split(".", 1)[0].strip().casefold()}

    if m := _MATCHED_RE.search(prose):
        exp["matched"] = int(m["matched"])
        exp["total"] = int(m["total"])
        exp["unit"] = m["unit"]

    if m := _WRONG_OF_RE.search(prose):
        exp["wrong_count"] = int(m["count"])
        exp["total"] = int(m["total"])
        exp["unit"] = m["unit"]
        if m["pos"]:
            exp["wrong_position"] = int(m["pos"])
    elif m := _WRONG_RE.search(prose):
        exp["wrong_count"] = int(m["count"])
        exp["unit"] = m["unit"] + "s"
        if m["pos"]:
            exp["wrong_position"] = int(m["pos"])

    if m := _MISSING_RE.search(prose):
        exp["missing_count"] = int(m["count"])
        exp["missing_from"] = int(m["pos"])

    return exp


def status_deviations(verdict: Verdict, exp: Expectation) -> list[str]:
    if verdict.status == exp["status"]:
        return []
    return [f"status: workbook says {exp['status']}, computed {verdict.status}"]


def count_deviations(verdict: Verdict, exp: Expectation) -> list[str]:
    """Every numeric claim in the prose that the computed verdict contradicts."""
    out: list[str] = []
    if "matched" in exp and verdict.matched != exp["matched"]:
        out.append(f"matched: workbook {exp['matched']}, computed {verdict.matched}")
    if "total" in exp and verdict.total != exp["total"]:
        out.append(f"total: workbook {exp['total']}, computed {verdict.total}")
    if "unit" in exp and verdict.unit != _UNIT_NAMES[exp["unit"]]:
        out.append(f"unit: workbook {exp['unit']}, computed {verdict.unit}")
    if "wrong_count" in exp and len(verdict.mismatch_positions) != exp["wrong_count"]:
        out.append(
            f"wrong count: workbook {exp['wrong_count']}, "
            f"computed {len(verdict.mismatch_positions)}"
        )
    if "wrong_position" in exp and exp["wrong_position"] not in verdict.mismatch_positions:
        out.append(
            f"wrong position: workbook {exp['wrong_position']}, "
            f"computed {verdict.mismatch_positions}"
        )
    if "missing_count" in exp and verdict.missing_count != exp["missing_count"]:
        out.append(
            f"missing count: workbook {exp['missing_count']}, computed {verdict.missing_count}"
        )
    if "missing_from" in exp and verdict.missing_from != exp["missing_from"]:
        out.append(f"missing from: workbook {exp['missing_from']}, computed {verdict.missing_from}")
    return out


def run_case(case: dict[str, Any]) -> Verdict:
    """Run one CHECK case against its card in ``B_Cards``."""
    card_text = CARDS[case["reference"], case["lang"]]
    return check(card_text, case["input"], case["lang"])


# ---------------------------------------------------------------------------
# Normalizer rules, one test per checklist line
# ---------------------------------------------------------------------------


def test_case_is_folded_with_casefold_not_lower() -> None:
    # The distinguishing case: "ß".lower() is "ß" but "ß".casefold() is "ss".
    assert normalize("Straße", "en") == "strasse"
    assert normalize("SHOUTING", "en") == normalize("shouting", "en")


def test_input_is_nfc_normalized_first() -> None:
    decomposed = "é"  # e + combining acute
    assert normalize(decomposed, "en") == normalize("é", "en") == "é"


@pytest.mark.parametrize(
    ("curly", "straight"),
    [("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"')],
)
def test_curly_quotes_fold_to_straight(curly: str, straight: str) -> None:
    # Both then vanish at the punctuation step, so the test compares the pair.
    assert normalize(f"a{curly}b", "en") == normalize(f"a{straight}b", "en") == "ab"


@pytest.mark.parametrize(("full", "ascii_form"), [("，", ","), ("；", ";")])
def test_full_width_forms_fold_to_ascii(full: str, ascii_form: str) -> None:
    assert normalize(f"a{full}b", "zh") == normalize(f"a{ascii_form}b", "zh")


@pytest.mark.parametrize("mark", [chr(c) for c in range(0x064B, 0x0653)] + ["ـ", "ٰ"])
def test_arabic_harakat_tatweel_and_dagger_alef_are_stripped(mark: str) -> None:
    assert normalize(f"كتب{mark}", "ar") == "كتب"


def test_arabic_alef_forms_are_normalized() -> None:
    assert normalize("ٱلله", "ar") == normalize("الله", "ar")
    assert normalize("على", "ar") == normalize("علي", "ar")


def test_arabic_rules_do_not_apply_to_other_languages() -> None:
    # A dagger alef in an "en" card is not stripped -- the rules are per language.
    assert "ٰ" in normalize("aٰb", "en")


def test_hindi_nukta_is_stripped() -> None:
    assert normalize("ड़", "hi") == "ड"


def test_hindi_nukta_rule_does_not_apply_to_other_languages() -> None:
    assert "़" in normalize("ड़", "en")


def test_chinese_traditional_is_never_folded_to_simplified() -> None:
    """A rule, not an oversight. Do not "fix" this. See DECISIONS D10."""
    assert normalize("愛", "zh") != normalize("爱", "zh")
    assert normalize("神愛世人", "zh") != normalize("神爱世人", "zh")


@pytest.mark.parametrize(
    "punct",
    [".", ",", ";", "!", "?", "—", "،", "؛", "।", "。", "，", "«"],
)
def test_unicode_punctuation_is_stripped_in_every_script(punct: str) -> None:
    assert normalize(f"a{punct}b", "en") == "ab"


def test_whitespace_runs_collapse_and_ends_are_trimmed() -> None:
    assert normalize("  the   lord \t is\n\nmy   shepherd  ", "en") == "the lord is my shepherd"


def test_normalize_leaves_an_already_clean_string_alone() -> None:
    assert normalize("the lord is my shepherd", "en") == "the lord is my shepherd"


# ---------------------------------------------------------------------------
# The 21 CHECK cases
# ---------------------------------------------------------------------------


def test_every_case_has_a_card_in_the_seed() -> None:
    for case in CASES:
        assert (case["reference"], case["lang"]) in CARDS, case


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case,
            marks=(
                pytest.mark.xfail(reason=STATUS_DEVIATIONS[case["id"]], strict=True)
                if case["id"] in STATUS_DEVIATIONS
                else ()
            ),
            id=f"{case['id']:02d}-{case['lang']}-{case['change'].replace(' ', '-')[:40]}",
        )
        for case in CASES
    ],
)
def test_case_status_matches_the_workbook(case: dict[str, Any]) -> None:
    verdict = run_case(case)
    exp = parse_expectation(case["expected_verdict"])
    assert status_deviations(verdict, exp) == []


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case,
            marks=(
                pytest.mark.xfail(reason=COUNT_DEVIATIONS[case["id"]], strict=True)
                if case["id"] in COUNT_DEVIATIONS
                else ()
            ),
            id=f"{case['id']:02d}-{case['lang']}-{case['change'].replace(' ', '-')[:40]}",
        )
        for case in CASES
    ],
)
def test_case_counts_match_the_workbook(case: dict[str, Any]) -> None:
    verdict = run_case(case)
    exp = parse_expectation(case["expected_verdict"])
    assert count_deviations(verdict, exp) == []


def test_the_prose_parser_actually_extracts_numbers() -> None:
    """Guard the parser: a parser that found nothing would make the counts vacuous."""
    parsed = [parse_expectation(c["expected_verdict"]) for c in CASES]
    with_numbers = [p for p in parsed if len(p) > 1]
    # 7 of the 21 verdict sentences state numbers; the rest are bare labels.
    assert len(with_numbers) == 7
    assert parse_expectation("Partial. 7 of 10 words matched; 3 missing from position 8.") == {
        "status": "partial",
        "matched": 7,
        "total": 10,
        "unit": "words",
        "missing_count": 3,
        "missing_from": 8,
    }
    assert parse_expectation("Partial. 1 of 9 words wrong at position 5 (shepard / shepherd)."), (
        "the 'N of M wrong at position P' shape must parse"
    )


def test_partial_cases_report_something_actionable() -> None:
    """Every Partial verdict must name where it went wrong -- a count alone is not enough."""
    for case in CASES:
        if parse_expectation(case["expected_verdict"])["status"] != "partial":
            continue
        verdict = run_case(case)
        assert verdict.mismatch_positions or verdict.missing_count or verdict.surplus_count, case


def test_an_empty_card_is_a_degenerate_case_no_real_card_reaches() -> None:
    """A card with no text has nothing to compare, so an empty answer "matches" 0 of 0.

    Recorded because Hypothesis finds it: it is a property of the arithmetic, not
    a reachable state. Every one of the 32 rows in ``B_Cards`` has text, and
    ``tests/test_fixtures.py`` fails if that ever stops being true.
    """
    verdict = check("", "", "en")
    assert (verdict.status, verdict.matched, verdict.total) == ("correct", 0, 0)


def test_a_chinese_answer_that_differs_only_in_spacing_is_correct() -> None:
    """Regression: for zh the units are characters, so spacing is not a unit.

    ``check`` used to decide "exact match" on the normalized *strings* while
    counting units on the *split* lists. Those two agree for the word languages
    but not for zh, where ``_split`` drops spaces -- so a perfectly recited
    verse typed with a space between every character came back Partial with
    30 of 30 matched, no mismatches and nothing for the UI to show.
    See ``docs/DECISIONS.md`` D12.
    """
    card = CARDS["John 3:16", "zh"]
    verdict = check(card, " ".join(card), "zh")
    assert verdict.status == "correct"
    assert verdict.matched == verdict.total
    assert verdict.mismatch_positions == []
    assert verdict.missing_count == verdict.surplus_count == 0


def test_check_report_is_written(check_report: CheckReport) -> None:
    """Record every case, deviations included, for ``reports/check-report.{json,md}``."""
    for case in CASES:
        verdict = run_case(case)
        exp = parse_expectation(case["expected_verdict"])
        check_report.record(
            CaseResult(
                id=case["id"],
                reference=case["reference"],
                lang=case["lang"],
                change=case["change"],
                expected_verdict=case["expected_verdict"],
                status=verdict.status,
                matched=verdict.matched,
                total=verdict.total,
                unit=verdict.unit,
                mismatch_positions=verdict.mismatch_positions,
                missing_from=verdict.missing_from,
                missing_count=verdict.missing_count,
                surplus_count=verdict.surplus_count,
                deviations=status_deviations(verdict, exp) + count_deviations(verdict, exp),
            )
        )
    failing = {r.id for r in check_report.results if not r.agrees}
    assert failing == set(STATUS_DEVIATIONS) | set(COUNT_DEVIATIONS), (
        "the set of deviating CHECK cases changed -- update DECISIONS.md and the README"
    )
