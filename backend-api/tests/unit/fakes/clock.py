"""In-memory `Clock` — the one fake for that port (AD-18). Reuse it; do not write another."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class FakeClock:
    """A clock that only moves when a test moves it."""

    def __init__(self, start: datetime = EPOCH) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware start")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> datetime:
        if seconds < 0:
            raise ValueError("a clock only moves forward")
        self._now += timedelta(seconds=seconds)
        return self._now
