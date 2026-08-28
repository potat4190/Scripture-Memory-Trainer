"""The clock: offset arithmetic, and that moving it moves the queue.

Every assertion is relative to ``date.today()`` -- the tests never hard-code a
calendar date, so they cannot rot. ``clock.py`` is the only module allowed to
call ``date.today()``; these tests call it too, to state the expected answer.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from scripture_memory_trainer.clock import Clock
from scripture_memory_trainer.models import Card
from scripture_memory_trainer.queue import build_queue


def real_today() -> date:
    return date.today()


# ---------------------------------------------------------------------------
# Offset arithmetic
# ---------------------------------------------------------------------------


def test_a_fresh_clock_reads_the_real_date() -> None:
    assert Clock().offset_days == 0
    assert Clock().today() == real_today()


@pytest.mark.parametrize("offset", [-30, -1, 0, 1, 7, 30, 60, 365])
def test_today_is_the_real_date_plus_the_offset(offset: int) -> None:
    assert Clock(offset).today() == real_today() + timedelta(days=offset)


@pytest.mark.parametrize("days", [1, 7, 30])
def test_advance_moves_forward_and_returns_the_new_date(days: int) -> None:
    clock = Clock()
    returned = clock.advance(days)
    assert clock.offset_days == days
    assert returned == clock.today() == real_today() + timedelta(days=days)


def test_advances_accumulate() -> None:
    clock = Clock()
    clock.advance(1)
    clock.advance(7)
    clock.advance(30)
    assert clock.offset_days == 38
    assert clock.today() == real_today() + timedelta(days=38)


def test_advance_accepts_a_negative_step() -> None:
    clock = Clock(10)
    assert clock.advance(-3) == real_today() + timedelta(days=7)
    assert clock.offset_days == 7


def test_jump_to_sets_the_offset_from_the_target_date() -> None:
    clock = Clock()
    target = real_today() + timedelta(days=45)
    assert clock.jump_to(target) == target
    assert clock.offset_days == 45


def test_jump_to_works_from_an_already_offset_clock() -> None:
    clock = Clock(100)
    target = real_today() + timedelta(days=2)
    assert clock.jump_to(target) == target
    assert clock.offset_days == 2


def test_jump_to_a_past_date_gives_a_negative_offset() -> None:
    clock = Clock()
    target = real_today() - timedelta(days=5)
    assert clock.jump_to(target) == target
    assert clock.offset_days == -5


def test_reset_drops_the_offset() -> None:
    clock = Clock(90)
    assert clock.reset() == real_today()
    assert clock.offset_days == 0


def test_reset_is_idempotent() -> None:
    clock = Clock(3)
    clock.reset()
    clock.reset()
    assert clock.offset_days == 0


# ---------------------------------------------------------------------------
# Time travel is only real if it moves the queue
# ---------------------------------------------------------------------------


def card(card_id: str, due_in_days: int) -> Card:
    return Card(
        card_id,
        f"Ref {card_id}",
        "en",
        "ltr",
        "text",
        box=0,
        due_date=real_today() + timedelta(days=due_in_days),
    )


def test_advancing_the_clock_brings_future_cards_into_the_queue() -> None:
    cards = [card("today", 0), card("in3", 3), card("in30", 30)]
    clock = Clock()

    queue, total = build_queue(cards, clock.today())
    assert [c.card_id for c in queue] == ["today"]
    assert total == 1

    clock.advance(3)
    queue, total = build_queue(cards, clock.today())
    # The card that was due first still leads: the clock moved, the order did not.
    assert [c.card_id for c in queue] == ["today", "in3"]
    assert total == 2


def test_advancing_thirty_days_makes_everything_due() -> None:
    cards = [card("today", 0), card("in3", 3), card("in30", 30)]
    clock = Clock()
    clock.advance(30)
    queue, total = build_queue(cards, clock.today())
    assert total == 3
    assert len(queue) == 3


def test_rewinding_the_clock_empties_the_queue_again() -> None:
    cards = [card("today", 0), card("in3", 3)]
    clock = Clock(30)
    assert build_queue(cards, clock.today())[1] == 2
    clock.reset()
    assert build_queue(cards, clock.today())[1] == 1
    clock.advance(-1)
    assert build_queue(cards, clock.today())[1] == 0


def test_the_queue_ordering_follows_the_clock() -> None:
    """After a jump, the card that has been waiting longest still leads."""
    cards = [card("in7", 7), card("in1", 1)]
    clock = Clock()
    clock.advance(10)
    queue, _ = build_queue(cards, clock.today())
    assert [c.card_id for c in queue] == ["in1", "in7"]
