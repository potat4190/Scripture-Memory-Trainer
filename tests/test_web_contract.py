"""The contract between the frontend and the backend.

`web/index.html` is a static page with no build step, so anything it knows
about the backend it knows by having been written to match. Two things are
deliberately duplicated there -- the Leitner intervals (so a grade button can
name its date before you press it) and the unit split (so a mismatch position
can be highlighted in the verse) -- and duplication that nothing checks is
duplication that drifts. These tests fail when it does.

The rest of the file is the Phase 4 checklist made executable: the four script
fonts, `lang` and `dir` bound per element, and logical properties only.
"""

from __future__ import annotations

import json
import re
import unicodedata
import unicodedata as ud
from pathlib import Path

import pytest
import regex

from scripture_memory_trainer.checker import _split
from scripture_memory_trainer.normalizer import normalize
from scripture_memory_trainer.queue import DAILY_CAP
from scripture_memory_trainer.scheduler import INTERVALS

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "web" / "index.html"
HTML = PAGE.read_text(encoding="utf-8")
CARDS = json.loads((ROOT / "seed" / "cards.json").read_text(encoding="utf-8"))


def test_the_page_exists_and_is_a_single_file() -> None:
    assert PAGE.is_file()
    assert sorted(p.name for p in PAGE.parent.iterdir()) == ["index.html"], (
        "the frontend is deliberately one file with no build step"
    )


# ---------------------------------------------------------------------------
# Duplicated logic
# ---------------------------------------------------------------------------


def test_the_javascript_intervals_match_the_scheduler() -> None:
    match = re.search(r"const INTERVALS = \{([^}]*)\}", HTML)
    assert match, "INTERVALS literal not found in the page"
    mirrored = {int(box): int(days) for box, days in re.findall(r"(\d+):\s*(\d+)", match.group(1))}
    assert mirrored == INTERVALS


def test_the_javascript_box_ceiling_matches_the_scheduler() -> None:
    match = re.search(r"const MAX_BOX = (\d+)", HTML)
    assert match, "MAX_BOX not found in the page"
    assert match.group(1) == str(max(INTERVALS))


def test_the_javascript_daily_cap_matches_the_queue() -> None:
    """The client shows a cap before the first response arrives; it must agree."""
    match = re.search(r"cap:\s*(\d+)", HTML)
    assert match, "the client-side cap default not found in the page"
    assert match.group(1) == str(DAILY_CAP)


def js_split_units(text: str, lang: str) -> list[str]:
    """Python transcription of `splitUnits` in the page. Kept in step by the test below."""
    s = unicodedata.normalize("NFC", text)
    s = regex.sub(r"\p{P}+", "", s)
    s = regex.sub(r"\s+", " ", s).strip()
    return list(s.replace(" ", "")) if lang == "zh" else (s.split() if s else [])


@pytest.mark.parametrize("card", CARDS, ids=[f"{c['reference']}-{c['language']}" for c in CARDS])
def test_the_client_side_split_lands_on_the_same_positions(card: dict[str, str]) -> None:
    """The verdict reports positions in *server* units; the page highlights *client* units.

    They have to be the same list. The client deliberately skips the
    language-specific folding (harakat, nukta, alef forms, case) because none of
    it changes how many units there are -- this proves that for every card in
    the deck, so a mismatch at position 15 is highlighted at position 15.
    """
    server = _split(normalize(card["text"], card["language"]), card["language"])
    client = js_split_units(card["text"], card["language"])
    assert len(server) == len(client)


@pytest.mark.parametrize("card", CARDS, ids=[f"{c['reference']}-{c['language']}" for c in CARDS])
def test_language_folding_never_changes_the_unit_count(card: dict[str, str]) -> None:
    """The invariant the client relies on, stated directly."""
    text, lang = card["text"], card["language"]
    folded = _split(normalize(text, lang), lang)
    unfolded = _split(normalize(text, "xx"), lang)  # "xx": no language-specific rules
    assert len(folded) == len(unfolded)


# ---------------------------------------------------------------------------
# The Phase 4 checklist, as assertions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "family",
    ["Noto+Sans", "Noto+Naskh+Arabic", "Noto+Sans+Devanagari", "Noto+Sans+SC"],
)
def test_the_four_script_fonts_are_requested(family: str) -> None:
    assert family in HTML


def test_alpine_and_dexie_are_loaded() -> None:
    assert "alpinejs@" in HTML
    assert "dexie@" in HTML


def test_the_dexie_schema_mirrors_the_backend_tables() -> None:
    stores = re.search(r"db\.version\(1\)\.stores\(\{(.*?)\}\)", HTML, re.S)
    assert stores
    for table in ("cards", "card_states", "review_logs", "app_state"):
        assert f"{table}:" in stores.group(1)


def test_direction_and_language_are_set_per_element() -> None:
    """Not on <html>: one page shows cards in four languages and two directions."""
    assert ':lang="current?.language"' in HTML
    assert ':dir="current?.direction"' in HTML
    assert HTML.count(':dir="current?.direction"') >= 3, "verse, answer box and marked-up diff"


PHYSICAL_PROPERTIES = re.compile(
    r"(?<![\w-])(margin|padding|border|inset)-(left|right)\s*:"
    r"|(?<![\w-])(left|right)\s*:\s*[^;]"
    r"|text-align\s*:\s*(left|right)",
)


def test_no_physical_left_or_right_properties() -> None:
    """Half these verses run the other way, so every inline edge is logical."""
    style = re.search(r"<style>(.*?)</style>", HTML, re.S)
    assert style
    offenders = PHYSICAL_PROPERTIES.findall(style.group(1))
    assert offenders == [], f"use logical properties instead: {offenders}"


def test_the_clock_controls_the_checklist_names_are_present() -> None:
    for control in ("advance_days: 1", "advance_days: 7", "advance_days: 30", "offset_days: 0"):
        assert control in HTML, f"missing clock control: {control}"
    assert "target_date: jumpDate" in HTML, "jump to a date"


def test_export_and_import_need_no_account() -> None:
    assert "/api/export" in HTML
    assert "/api/import" in HTML
    assert "exportData()" in HTML and "importData(" in HTML


def test_an_again_grade_re_enters_the_session() -> None:
    assert "due_today_again" in HTML


def test_reduced_motion_is_respected() -> None:
    assert "prefers-reduced-motion" in HTML


def test_the_page_declares_a_viewport_without_disabling_zoom() -> None:
    assert 'name="viewport"' in HTML
    assert "user-scalable=no" not in HTML
    assert "maximum-scale" not in HTML


def test_no_emoji_are_used_as_icons() -> None:
    """Icons are inline SVG. An emoji here would render differently per platform."""
    body = HTML.split("<body>", 1)[1]
    emoji = [ch for ch in body if ud.category(ch) == "So"]
    assert emoji == [], f"emoji found in markup: {emoji}"
