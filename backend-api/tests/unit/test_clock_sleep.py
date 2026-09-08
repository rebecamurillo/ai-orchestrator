"""`Clock.sleep`: waiting is reading the clock forward, so it is a member of that port.

The `agent` executor polls `.git/index.lock` after killing an orphaned harness (AD-14), and
`application/` may not import `time` (AD-2) — `tests/unit/test_source_limits.py` polices the
wall clock in that layer. `tests/unit/test_clock_adapter.py` and `test_clock_fake.py` are
frozen and predate the member; this module is its own.
"""

from __future__ import annotations

import inspect

from orchestrator.domain.ports.clock import Clock
from orchestrator.infrastructure.clock import SystemClock
from tests.unit.fakes.clock import EPOCH, FakeClock

#: An interval no poll interval in the system happens to use, so an assertion on it is
#: asserting the argument and not a default.
SECONDS = 2.5


def test_the_port_declares_sleep() -> None:
    assert "sleep" in Clock.__protocol_attrs__


def test_both_implementations_satisfy_the_port() -> None:
    assert isinstance(SystemClock(), Clock)
    assert isinstance(FakeClock(), Clock)


def test_the_adapter_really_waits_and_returns_nothing() -> None:
    """A zero delay, because a unit test that slept would be a unit test that is slow."""
    assert SystemClock().sleep(0) is None


def test_the_adapters_signature_is_the_ports() -> None:
    assert list(inspect.signature(SystemClock.sleep).parameters) == ["self", "seconds"]


def test_the_fake_advances_instead_of_blocking() -> None:
    clock = FakeClock(EPOCH)

    clock.sleep(SECONDS)

    assert (clock.now() - EPOCH).total_seconds() == SECONDS
    assert clock.slept == [SECONDS]


def test_the_hook_is_how_a_test_changes_the_world_mid_poll() -> None:
    """`.git/index.lock` vanishing between two polls is the case this exists for."""
    seen: list[int] = []
    clock = FakeClock(EPOCH, on_sleep=lambda: seen.append(len(seen)))

    clock.sleep(1.0)
    clock.sleep(1.0)

    assert seen == [0, 1]


def test_a_fake_with_no_hook_simply_advances() -> None:
    clock = FakeClock(EPOCH)

    clock.sleep(1.0)

    assert clock.on_sleep is None
    assert clock.slept == [1.0]
