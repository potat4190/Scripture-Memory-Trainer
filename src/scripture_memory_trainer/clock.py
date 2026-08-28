"""Single source of time for the whole app.

Nothing outside this module may call ``date.today()`` or ``datetime.now()`` --
that is what breaks time travel. Every "what day is it" goes through a ``Clock``
instance carrying a persisted offset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Clock:
    """A clock offset by a whole number of days from the real system date."""

    offset_days: int = 0

    def today(self) -> date:
        """The current app date: real today plus the offset."""
        return date.today() + timedelta(days=self.offset_days)

    def advance(self, days: int) -> date:
        """Move the app date forward (or back, if negative) and return it."""
        self.offset_days += days
        return self.today()

    def jump_to(self, target: date) -> date:
        """Set the app date to ``target`` and return it."""
        self.offset_days = (target - date.today()).days
        return self.today()

    def reset(self) -> date:
        """Drop the offset; the app date becomes the real system date."""
        self.offset_days = 0
        return self.today()
