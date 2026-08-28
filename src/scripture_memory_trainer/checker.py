"""Positional answer checking. Pure function of ``(card_text, user_input, lang)``.

The ``Verdict`` fields beyond the checklist's minimum
(``missing_count``, ``surplus_count``, ``surplus_from``) and the treatment of
surplus input are logged in ``docs/DECISIONS.md`` (D6, D7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .normalizer import normalize

Status = Literal["correct", "partial", "incorrect"]
Unit = Literal["words", "chars"]

CHAR_SPLIT_LANGS = frozenset({"zh"})


@dataclass
class Verdict:
    status: Status
    matched: int
    total: int
    unit: Unit
    mismatch_positions: list[int] = field(default_factory=list)  # 1-based
    missing_from: int | None = None  # 1-based position of the first absent unit
    missing_count: int = 0
    surplus_count: int = 0
    surplus_from: int | None = None  # 1-based position of the first surplus unit


def _split(text: str, lang: str) -> list[str]:
    if lang in CHAR_SPLIT_LANGS:
        return list(text.replace(" ", ""))
    return text.split()


def check(card_text: str, user_input: str, lang: str) -> Verdict:
    """Compare ``user_input`` against ``card_text`` unit by unit."""
    unit: Unit = "chars" if lang in CHAR_SPLIT_LANGS else "words"

    norm_card = normalize(card_text, lang)
    norm_input = normalize(user_input, lang)

    card_units = _split(norm_card, lang)
    input_units = _split(norm_input, lang)
    total = len(card_units)

    if norm_card == norm_input:
        return Verdict(status="correct", matched=total, total=total, unit=unit)

    matched = 0
    mismatch_positions: list[int] = []
    pairs = zip(card_units, input_units, strict=False)  # positional; the shorter side stops
    for position, (card_unit, input_unit) in enumerate(pairs, start=1):
        if card_unit == input_unit:
            matched += 1
        else:
            mismatch_positions.append(position)

    missing_from: int | None = None
    missing_count = 0
    if len(input_units) < len(card_units):
        missing_from = len(input_units) + 1
        missing_count = len(card_units) - len(input_units)

    surplus_from: int | None = None
    surplus_count = 0
    if len(input_units) > len(card_units):
        surplus_from = len(card_units) + 1
        surplus_count = len(input_units) - len(card_units)

    status: Status = "incorrect" if matched == 0 else "partial"

    return Verdict(
        status=status,
        matched=matched,
        total=total,
        unit=unit,
        mismatch_positions=mismatch_positions,
        missing_from=missing_from,
        missing_count=missing_count,
        surplus_count=surplus_count,
        surplus_from=surplus_from,
    )
