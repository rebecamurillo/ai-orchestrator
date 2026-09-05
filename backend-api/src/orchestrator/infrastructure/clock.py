"""The `Clock` adapter: the one reader of the wall clock.

`tests/unit/test_source_limits.py` forbids `datetime.now()` in `domain/`, `application/`
and `api/`, so this module is where "now" enters the system. It returns a timezone-aware
UTC instant, because every timestamp this system stores and serialises is UTC (Consistency
Conventions — Dates); a naive value here would be the server's local zone wearing no label.
"""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Reads the machine's clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)
