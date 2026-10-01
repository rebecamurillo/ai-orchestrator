"""`infrastructure/longpoll.py`: what a held connection does while it waits.

No real second passes anywhere here — `sleep` is injected, which is the whole reason the
helper takes it. What is asserted is the contract the events route depends on: how many reads
happened, how many waits, and which read is answered with.
"""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.longpoll import POLL_INTERVAL_S, Watch, hold_until_changed

QUEUED = "queued"
RUNNING = "running"
NEEDS_YOU = "needs_you"
#: Never reached: a read the helper must not make is scripted to this.
UNREACHABLE = "unreachable"

ONE_READ = 1
TWO_READS = 2
THREE_READS = 3


class Reads:
    """A scripted sequence of reads, counting how often each half of the loop ran."""

    def __init__(self, values: list[str]) -> None:
        self.values = values
        self.reads = 0
        self.slept: list[float] = []

    async def read(self) -> str:
        value = self.values[min(self.reads, len(self.values) - 1)]
        self.reads += 1
        return value

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


def watching(first: str, baseline: str) -> Watch[str, str]:
    return Watch(first=first, baseline=baseline, token=lambda value: value)


async def test_a_zero_wait_answers_the_read_the_caller_already_made() -> None:
    reads = Reads([UNREACHABLE])

    latest, changed = await hold_until_changed(
        reads.read, watching(QUEUED, QUEUED), wait=0, sleep=reads.sleep
    )

    assert (latest, changed) == (QUEUED, False)
    assert reads.reads == 0
    assert reads.slept == []


async def test_a_baseline_that_already_disagrees_answers_at_once() -> None:
    """What `?since=` buys: a change made between two calls is seen on the first read."""
    reads = Reads([UNREACHABLE])

    latest, changed = await hold_until_changed(
        reads.read, watching(RUNNING, QUEUED), wait=30, sleep=reads.sleep
    )

    assert (latest, changed) == (RUNNING, True)
    assert reads.reads == 0
    assert reads.slept == []


async def test_a_change_mid_wait_is_answered_before_the_wait_runs_out() -> None:
    reads = Reads([QUEUED, NEEDS_YOU])

    latest, changed = await hold_until_changed(
        reads.read, watching(QUEUED, QUEUED), wait=30, sleep=reads.sleep
    )

    assert (latest, changed) == (NEEDS_YOU, True)
    assert reads.reads == TWO_READS
    assert reads.slept == [POLL_INTERVAL_S] * TWO_READS


async def test_an_unchanged_read_waits_exactly_the_requested_seconds() -> None:
    reads = Reads([QUEUED])

    latest, changed = await hold_until_changed(
        reads.read, watching(QUEUED, QUEUED), wait=THREE_READS, sleep=reads.sleep
    )

    assert (latest, changed) == (QUEUED, False)
    assert reads.reads == THREE_READS
    assert reads.slept == [POLL_INTERVAL_S] * THREE_READS


async def test_the_default_sleep_is_the_event_loop_s_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """Called without a `sleep`, it awaits `asyncio.sleep` — flattened to zero here so the
    assertion is about the call rather than about time."""
    monkeypatch.setattr("orchestrator.infrastructure.longpoll.POLL_INTERVAL_S", 0)
    reads = Reads([QUEUED])

    latest, changed = await hold_until_changed(reads.read, watching(QUEUED, QUEUED), wait=TWO_READS)

    assert (latest, changed) == (QUEUED, False)
    assert reads.reads == TWO_READS
