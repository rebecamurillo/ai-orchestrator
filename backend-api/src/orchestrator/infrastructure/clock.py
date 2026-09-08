"""The `Clock` adapter: the one reader of the wall clock.

`tests/unit/test_source_limits.py` forbids `datetime.now()` in `domain/`, `application/`
and `api/`, so this module is where "now" enters the system — and, since 5.4, where waiting
on it does too: `sleep` is the one `time.sleep` in the package, for the index-lock poll the
`agent` executor runs after it kills an orphaned harness (AD-14). It returns a timezone-aware
UTC instant, because every timestamp this system stores and serialises is UTC (Consistency
Conventions — Dates); a naive value here would be the server's local zone wearing no label.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime


class SystemClock:
    """Reads the machine's clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)
