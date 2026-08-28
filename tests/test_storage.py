"""``storage.py`` -- the deliberate I/O exception (DECISIONS D9).

Not a Phase 2 checklist item, but it is shipped code, and a save/load round trip
that silently loses a box or a due date would be invisible until a terminal
driver existed. Everything here writes to pytest's ``tmp_path``; nothing touches
the repo.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from scripture_memory_trainer.models import Card
from scripture_memory_trainer.storage import (
    export_json,
    load_seed_cards,
    load_state,
    save_state,
)

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 9, 1)


def sample_cards() -> list[Card]:
    return [
        Card("c1", "John 3:16", "en", "ltr", "For God so loved the world"),
        Card("c2", "Romans 8:28", "ar", "rtl", "ونحن نعلم"),
    ]


def test_load_seed_cards_reads_the_real_seed_file() -> None:
    cards = load_seed_cards(ROOT / "seed" / "cards.json")
    assert len(cards) == 32
    assert all(c.box == 0 and c.due_date is None for c in cards), "the seed carries no state"
    assert {c.language for c in cards} == {"en", "zh", "ar", "hi"}


def test_unseen_cards_start_in_box_zero_due_today(tmp_path: Path) -> None:
    cards = sample_cards()
    offset, langs = load_state(tmp_path / "absent.json", cards, TODAY)
    assert offset == 0
    assert langs is None
    assert all(c.box == 0 and c.due_date == TODAY for c in cards)


def test_state_survives_a_save_load_round_trip(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    cards = sample_cards()
    cards[0].box, cards[0].due_date = 4, TODAY + timedelta(days=21)
    cards[1].box, cards[1].due_date = 1, TODAY

    save_state(state, cards, offset_days=17, language_filter=["ar"])

    restored = sample_cards()
    offset, langs = load_state(state, restored, TODAY)
    assert offset == 17
    assert langs == ["ar"]
    assert [(c.box, c.due_date) for c in restored] == [(4, TODAY + timedelta(days=21)), (1, TODAY)]


def test_a_card_added_after_the_last_save_starts_fresh(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    saved = sample_cards()[:1]
    saved[0].box, saved[0].due_date = 3, TODAY
    save_state(state, saved, offset_days=0)

    cards = sample_cards()
    load_state(state, cards, TODAY)
    assert (cards[0].box, cards[0].due_date) == (3, TODAY), "the saved card keeps its state"
    assert (cards[1].box, cards[1].due_date) == (0, TODAY), "new card joins at box 0, due now"


def test_a_saved_card_with_no_due_date_loads_as_due_now(tmp_path: Path) -> None:
    """Regression: `save_state` writes `"due_date": null` for an unscheduled card,
    and `load_state` used to hand that straight to `date.fromisoformat`, which
    raises `TypeError`. A card with a box but no date is due now.
    """
    state = tmp_path / "state.json"
    cards = sample_cards()
    cards[0].box = 2  # box set, never scheduled -> due_date stays None
    save_state(state, cards, offset_days=0)

    restored = sample_cards()
    load_state(state, restored, TODAY)
    assert (restored[0].box, restored[0].due_date) == (2, TODAY)


def test_save_state_creates_missing_parent_directories(tmp_path: Path) -> None:
    state = tmp_path / "nested" / "deeper" / "state.json"
    save_state(state, sample_cards(), offset_days=0)
    assert state.exists()


def test_export_is_self_contained(tmp_path: Path) -> None:
    """The export is the always-free backup -- it must carry the text, not just ids."""
    out = tmp_path / "export.json"
    cards = sample_cards()
    cards[0].box, cards[0].due_date = 2, TODAY

    export_json(out, cards, offset_days=3, language_filter=None)
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["offset_days"] == 3
    assert len(payload["cards"]) == 2
    assert set(payload["cards"][0]) == {
        "card_id",
        "reference",
        "language",
        "direction",
        "text",
        "box",
        "due_date",
    }
    assert payload["cards"][0]["text"] == "For God so loved the world"
    assert payload["cards"][0]["due_date"] == TODAY.isoformat()
    assert payload["cards"][1]["due_date"] is None


def test_export_keeps_non_latin_text_readable(tmp_path: Path) -> None:
    """``ensure_ascii=False``: an Arabic card must not come back as \\u escapes."""
    out = tmp_path / "export.json"
    export_json(out, sample_cards(), offset_days=0)
    assert "ونحن نعلم" in out.read_text(encoding="utf-8")
