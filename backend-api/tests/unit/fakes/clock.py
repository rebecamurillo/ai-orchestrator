"""In-memory `Clock` — the one fake for that port (AD-18). Reuse it; do not write another.

`sleep` advances the clock rather than blocking, and calls `on_sleep` if one was given —
which is how a test makes `.git/index.lock` disappear part-way through the `agent`
executor's poll (AD-14) without a real file and without a real second passing.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class FakeClock:
    """A clock that only moves when a test moves it."""

    def __init__(self, start: datetime = EPOCH, on_sleep: Callable[[], None] | None = None) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware start")
        self._now = start.astimezone(UTC)
        self.on_sleep = on_sleep
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        """Move the clock forward by `seconds` and let the test change the world."""
        self.slept.append(seconds)
        self.advance(seconds)
        if self.on_sleep is not None:
            self.on_sleep()

    def advance(self, seconds: float) -> datetime:
        if seconds < 0:
            raise ValueError("a clock only moves forward")
        self._now += timedelta(seconds=seconds)
        return self._now
