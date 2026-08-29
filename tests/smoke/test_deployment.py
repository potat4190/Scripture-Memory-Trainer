"""One Playwright test against a running deployment.

Deliberately one test, not a suite. It loads the page, advances the clock three
days and checks the queue responds -- which in passing exercises the frontend,
the API, the database and the travellable clock in a single pass. Anything that
breaks the deployment breaks this.

It is skipped unless ``SMOKE_URL`` is set, so the default suite stays fast and
needs no browser::

    uv sync --group smoke
    uv run playwright install chromium
    SMOKE_URL=https://your-deployment.vercel.app uv run pytest tests/smoke -q

`.github/workflows/ci.yml` runs it on demand -- Actions tab, "CI", "Run
workflow", paste the URL.

**It grades cards on whatever database it points at.** Against production that
means real review history and a moved clock, so it resets the clock at the end.
Prefer a preview deployment if that matters.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="the smoke group is not installed: uv sync --group smoke",
)

from playwright.sync_api import Page, expect

SMOKE_URL = os.environ.get("SMOKE_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not SMOKE_URL, reason="set SMOKE_URL to the deployment you want to smoke test"
)


@pytest.fixture(autouse=True)
def reset_the_clock(page: Page) -> object:
    """Leave the deployment on the real date whatever the test does."""
    yield
    page.request.post(f"{SMOKE_URL}/api/clock", data={"offset_days": 0})


def test_travelling_three_days_changes_the_queue(page: Page) -> None:
    page.goto(SMOKE_URL, wait_until="domcontentloaded")

    # The page booted: Alpine ran and removed x-cloak. A blank page fails here.
    expect(page.locator(".rail")).to_be_visible()

    clock = page.request.get(f"{SMOKE_URL}/api/clock").json()
    assert clock["offset_days"] == 0, "the deployment was left time-travelled"
    assert clock["app_date"] == clock["real_date"]

    queue = page.request.get(f"{SMOKE_URL}/api/queue").json()
    assert queue["total_due"] > 0, "nothing is due, so the seed never ran"
    card_id = queue["cards"][0]["card_id"]

    # `again` first, so the card is in box 0 whatever earlier runs did to it.
    # `easy` from box 0 is box 2, which is a 3-day interval -- the one this test
    # travels. Without the reset, a card already in box 3 would schedule 60 days
    # out and three clicks would prove nothing.
    page.request.post(f"{SMOKE_URL}/api/review", data={"card_id": card_id, "grade": "again"})
    review = page.request.post(
        f"{SMOKE_URL}/api/review", data={"card_id": card_id, "grade": "easy"}
    ).json()
    assert (review["box_after"], review["interval_days"]) == (2, 3)

    # Not due today any more. Checked against /api/cards rather than the queue,
    # because the queue is capped at 20 and a card scheduled furthest out sorts
    # last -- absent from the queue would not prove it is not due.
    assert due_date_of(page, card_id) > review["app_date"]

    # Travel, through the UI, the way a reviewer would.
    for _ in range(3):
        page.get_by_role("button", name="+1d").click()
    expect(page.locator('.clock__date[data-travelled="true"]')).to_be_visible()

    after = page.request.get(f"{SMOKE_URL}/api/clock").json()
    assert after["offset_days"] == 3
    assert after["app_date"] != after["real_date"], "only the app date moves"
    assert after["real_date"] == clock["real_date"], "the real calendar did not"

    # Due again: the schedule responded, not the calendar.
    assert due_date_of(page, card_id) <= after["app_date"]


def due_date_of(page: Page, card_id: str) -> str:
    """The card's due date from the uncapped list, as an ISO string."""
    cards = page.request.get(f"{SMOKE_URL}/api/cards").json()
    due: str = next(c["due_date"] for c in cards if c["card_id"] == card_id)
    return due


def test_the_api_docs_render(page: Page) -> None:
    """The Phase 3 exit criterion, checked on the thing that is actually deployed."""
    response = page.request.get(f"{SMOKE_URL}/docs")
    assert response.status == 200
    assert page.request.get(f"{SMOKE_URL}/openapi.json").json()["info"]["title"] == (
        "Scripture Memory Trainer"
    )
