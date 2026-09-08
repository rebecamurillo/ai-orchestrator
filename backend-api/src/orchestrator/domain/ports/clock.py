"""The `Clock` port.

Time is an input, not an ambient fact: nothing outside `infrastructure/` calls
`datetime.now()`. Use cases take a `Clock` and tests inject `tests/unit/fakes/clock.py`.

`sleep` is here for the same reason `now` is. The `agent` executor polls `.git/index.lock`
after killing an orphaned harness — "one second, thirty at most" (AD-14) — and
`application/` may not import `time` (AD-2, and `tests/unit/test_source_limits.py` polices
the wall clock in that layer). Waiting is reading the clock forward, so it is a member of
the port that owns the clock rather than a second port that owns only the pause.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Reads the current instant as a timezone-aware UTC datetime."""

    def now(self) -> datetime:
        """Return the current instant, tz-aware and in UTC."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block this thread for `seconds`, then return. A fake advances instead."""
        ...
