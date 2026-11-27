"""`start_attempt` reads the Run under its row lock, as `signal_run` does (AD-8).

Release review 2026-11-26: an initiative's cancel landed between the walk's unlocked read of
a `queued` Run and its write. The start wrote the Run back to `running` over the committed
`cancelled`, with a `plan` attempt the cancelled workflow never ended; the Run held its
working step forever and refused every instance hold.
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.start_attempt import start_attempt
from orchestrator.domain.statuses import InvalidTransition
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world
from tests.unit.fakes.runs import FakeRunRepository


def test_the_run_is_read_under_its_row_lock() -> None:
    world = a_world("queued", PAIR_PLAN, statuses={"plan": "queued"})

    start_attempt(world.ports, world.run.id, 1)

    runs = world.ports.runs
    assert isinstance(runs, FakeRunRepository)
    assert ("get_for_update", world.run.id) in runs.calls


def test_a_start_after_the_cancel_committed_refuses_and_writes_nothing() -> None:
    world = a_world("cancelled", PAIR_PLAN, statuses={"plan": "queued"})

    with pytest.raises(InvalidTransition):
        start_attempt(world.ports, world.run.id, 1)

    assert world.stored_run().status == "cancelled"
    assert world.attempts_of("plan") == []
    assert world.status_of("plan") == "queued"
