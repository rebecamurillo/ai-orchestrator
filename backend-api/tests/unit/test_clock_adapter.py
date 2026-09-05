"""The wall-clock adapter — the one module in this system that reads the machine's clock.

`tests/unit/test_source_limits.py` proves nothing outside `infrastructure/` calls
`datetime.now()`; this proves the module that does returns what every use case assumes: a
timezone-aware instant in UTC, and one that moves.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orchestrator.domain.ports.clock import Clock
from orchestrator.infrastructure.clock import SystemClock
from tests.unit.fakes.clock import FakeClock


def test_the_adapter_satisfies_the_port() -> None:
    clock: Clock = SystemClock()

    assert isinstance(clock, Clock)


def test_now_is_timezone_aware_and_in_utc() -> None:
    now = SystemClock().now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert now.tzinfo is UTC


def test_now_is_the_current_instant() -> None:
    before = datetime.now(UTC)

    now = SystemClock().now()

    assert before <= now <= datetime.now(UTC)


def test_the_adapter_and_the_fake_answer_the_same_shape() -> None:
    """Use cases are written against the fake and run against this."""
    real = SystemClock().now()
    fake = FakeClock().now()

    assert real.tzinfo == fake.tzinfo
    assert type(real) is type(fake)
