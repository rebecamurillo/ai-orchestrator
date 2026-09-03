"""The `Clock` port.

Time is an input, not an ambient fact: nothing outside `infrastructure/` calls
`datetime.now()`. Use cases take a `Clock` and tests inject `tests/unit/fakes/clock.py`.
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
