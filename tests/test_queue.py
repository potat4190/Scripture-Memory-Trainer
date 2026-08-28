"""The daily queue: due filter, sort key, cap, pre-cap total, language filter.

The sort key is ``(due_date, box, reference)`` and each of the three is tested
in isolation -- two cards differing on exactly one component -- so a key that
happens to be right for the wrong reason still fails. The reference component
is a plain **string** sort, not canonical book order; that has its own test
because it is the rule most likely to be "helpfully" fixed later.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripture_memory_trainer.models import Card
from scripture_memory_trainer.queue import DAILY_CAP, build_queue

TODAY = date(2026, 9, 1)


def make_card(
    card_id: str,
    *,
    reference: str = "John 3:16",
    language: str = "en",
    box: int = 0,
    due: date | None = TODAY,
) -> Card:
    direction = "rtl" if language == "ar" else "ltr"
    return Card(card_id, reference, language, direction, "text", box=box, due_date=due)


# ---------------------------------------------------------------------------
# Due filter
# ---------------------------------------------------------------------------


def test_cards_due_today_and_earlier_are_included() -> None:
    cards = [
        make_card("overdue", due=TODAY - timedelta(days=3)),
        make_card("today", due=TODAY),
    ]
    queue, total = build_queue(cards, TODAY)
    assert [c.card_id for c in queue] == ["overdue", "today"]
    assert total == 2


def test_cards_due_later_are_excluded() -> None:
    cards = [make_card("tomorrow", due=TODAY + timedelta(days=1))]
    queue, total = build_queue(cards, TODAY)
    assert queue == []
    assert total == 0


def test_cards_with_no_due_date_are_excluded() -> None:
    """An unscheduled card is not due; it is not silently treated as due today."""
    queue, total = build_queue([make_card("unscheduled", due=None)], TODAY)
    assert queue == []
    assert total == 0


def test_empty_input_gives_an_empty_queue() -> None:
    assert build_queue([], TODAY) == ([], 0)


# ---------------------------------------------------------------------------
# Sort key: (due_date, box, reference) -- one component at a time
# ---------------------------------------------------------------------------


def test_sorts_by_due_date_first_most_overdue_leading() -> None:
    cards = [
        make_card("recent", box=0, due=TODAY),
        make_card("stale", box=5, due=TODAY - timedelta(days=10)),
    ]
    queue, _ = build_queue(cards, TODAY)
    # The stale card leads despite its higher box: due_date outranks box.
    assert [c.card_id for c in queue] == ["stale", "recent"]


def test_sorts_by_box_second_lowest_box_leading() -> None:
    cards = [
        make_card("box4", reference="Aaa 1:1", box=4),
        make_card("box1", reference="Zzz 1:1", box=1),
    ]
    queue, _ = build_queue(cards, TODAY)
    # box1 leads despite the later reference: box outranks reference.
    assert [c.card_id for c in queue] == ["box1", "box4"]


def test_sorts_by_reference_third() -> None:
    cards = [
        make_card("z", reference="Zephaniah 3:17"),
        make_card("a", reference="Amos 5:24"),
    ]
    queue, _ = build_queue(cards, TODAY)
    assert [c.card_id for c in queue] == ["a", "z"]


def test_reference_sort_is_alphabetical_not_canonical_book_order() -> None:
    """Plain string sort. Canonical order would be Leviticus, Psalm, Isaiah, John."""
    references = ["Psalm 23:1", "John 3:16", "Leviticus 19:34", "Isaiah 40:31"]
    cards = [make_card(r, reference=r) for r in references]
    queue, _ = build_queue(cards, TODAY)
    assert [c.reference for c in queue] == [
        "Isaiah 40:31",
        "John 3:16",
        "Leviticus 19:34",
        "Psalm 23:1",
    ]


def test_all_three_sort_components_together() -> None:
    cards = [
        make_card("d", reference="Bbb 1:1", box=1, due=TODAY),
        make_card("c", reference="Aaa 1:1", box=1, due=TODAY),
        make_card("b", reference="Zzz 1:1", box=0, due=TODAY),
        make_card("a", reference="Zzz 1:1", box=3, due=TODAY - timedelta(days=1)),
    ]
    queue, _ = build_queue(cards, TODAY)
    assert [c.card_id for c in queue] == ["a", "b", "c", "d"]


def test_build_queue_does_not_mutate_the_caller_list() -> None:
    cards = [make_card("z", reference="Zzz 1:1"), make_card("a", reference="Aaa 1:1")]
    original = [c.card_id for c in cards]
    build_queue(cards, TODAY)
    assert [c.card_id for c in cards] == original


# ---------------------------------------------------------------------------
# Cap and pre-cap total
# ---------------------------------------------------------------------------


def test_queue_caps_at_twenty() -> None:
    assert DAILY_CAP == 20
    cards = [make_card(f"c{i:02d}", reference=f"Ref {i:02d}") for i in range(47)]
    queue, total = build_queue(cards, TODAY)
    assert len(queue) == 20
    assert total == 47, "the UI needs the pre-cap count to say '20 of 47 due'"


def test_the_cap_keeps_the_highest_priority_cards_not_an_arbitrary_twenty() -> None:
    cards = [make_card(f"c{i:02d}", reference=f"Ref {i:02d}") for i in range(25)]
    queue, _ = build_queue(cards, TODAY)
    assert [c.reference for c in queue] == [f"Ref {i:02d}" for i in range(20)]


@pytest.mark.parametrize("count", [0, 1, 19, 20, 21])
def test_pre_cap_total_is_the_due_count_capped_or_not(count: int) -> None:
    cards = [make_card(f"c{i:02d}", reference=f"Ref {i:02d}") for i in range(count)]
    queue, total = build_queue(cards, TODAY)
    assert total == count
    assert len(queue) == min(count, DAILY_CAP)


def test_pre_cap_total_counts_only_due_cards() -> None:
    cards = [make_card(f"due{i}", reference=f"Ref {i}") for i in range(30)]
    cards += [make_card(f"later{i}", due=TODAY + timedelta(days=5)) for i in range(10)]
    _, total = build_queue(cards, TODAY)
    assert total == 30


# ---------------------------------------------------------------------------
# Language filter
# ---------------------------------------------------------------------------


def test_language_filter_keeps_only_the_named_languages() -> None:
    cards = [
        make_card("en", language="en"),
        make_card("ar", language="ar"),
        make_card("zh", language="zh"),
        make_card("hi", language="hi"),
    ]
    queue, total = build_queue(cards, TODAY, ["ar", "hi"])
    assert sorted(c.card_id for c in queue) == ["ar", "hi"]
    assert total == 2, "the pre-cap total counts the filtered set, not everything due"


def test_no_language_filter_keeps_every_language() -> None:
    cards = [make_card(lang, language=lang) for lang in ("en", "ar", "zh", "hi")]
    empty_filters: list[list[str] | None] = [None, []]
    for empty in empty_filters:
        queue, total = build_queue(cards, TODAY, empty)
        assert len(queue) == 4
        assert total == 4
