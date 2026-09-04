"""The `Clock` port and the fake every later story injects in place of wall-clock time."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.domain.ports.clock import Clock
from tests.unit.fakes.clock import EPOCH, FakeClock

ADVANCE_SECONDS = 90


def test_the_fake_satisfies_the_port() -> None:
    clock: Clock = FakeClock()

    assert isinstance(clock, Clock)


def test_now_is_timezone_aware_utc() -> None:
    now = FakeClock().now()

    assert now.tzinfo is not None
    assert now.utcoffset() == UTC.utcoffset(None)
    assert now == EPOCH


def test_time_moves_only_when_advanced() -> None:
    clock = FakeClock()
    first = clock.now()

    assert clock.now() == first

    second = clock.advance(ADVANCE_SECONDS)

    assert second - first == (clock.now() - first)
    assert (second - first).total_seconds() == ADVANCE_SECONDS


def test_a_naive_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FakeClock(datetime(2026, 1, 1))  # noqa: DTZ001 — a naive value is the point


def test_a_clock_only_moves_forward() -> None:
    clock = FakeClock()

    with pytest.raises(ValueError, match="forward"):
        clock.advance(-1)

    assert clock.now() == EPOCH
