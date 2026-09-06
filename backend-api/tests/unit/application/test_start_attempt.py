"""`start_attempt` — the row leaves the queue and an Attempt exists (SPEC CAP-5, AD-8)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.start_attempt import start_attempt
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import InvalidTransition
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world, an_attempt

#: The attempt number a row that has already run once reaches on its next start.
SECOND = 2


def a_queued_pair() -> object:
    return a_world("queued", PAIR_PLAN, {"plan": "queued"})


# ── AC1: a Run with rows `plan, checkout` and row 1 queued ───────────────────


def test_the_row_runs_the_run_runs_and_the_record_says_start() -> None:
    world = a_queued_pair()

    attempt = start_attempt(world.ports, world.run.id, 1)

    assert world.status_of("plan") == "running"
    assert attempt.n == 1
    assert world.stored_run().status == "running"
    assert world.events() == ["start"]


def test_the_start_record_is_the_machines_and_says_what_happened() -> None:
    world = a_queued_pair()

    start_attempt(world.ports, world.run.id, 1)
    line = world.records()[0]

    assert (line.actor, line.text, line.path) == ("machine", "run started", None)


def test_the_run_and_the_attempt_are_stamped_with_the_clock() -> None:
    world = a_queued_pair()

    attempt = start_attempt(world.ports, world.run.id, 1)

    assert world.stored_run().started_at == world.clock.now()
    assert attempt.started_at == world.clock.now()


def test_the_attempt_is_stored_running_against_its_own_row() -> None:
    world = a_queued_pair()

    attempt = start_attempt(world.ports, world.run.id, 1)

    assert world.attempts_of("plan") == [attempt]
    assert attempt.status == "running"


def test_the_engine_ref_is_carried_through_without_being_read() -> None:
    world = a_queued_pair()

    attempt = start_attempt(world.ports, world.run.id, 1, engine_ref={"wf": "abc"})

    assert attempt.engine_ref == {"wf": "abc"}


def test_an_attempt_started_without_an_engine_ref_carries_an_empty_one() -> None:
    world = a_queued_pair()

    assert start_attempt(world.ports, world.run.id, 1).engine_ref == {}


def test_the_whole_start_is_one_committed_unit_of_work() -> None:
    world = a_queued_pair()

    start_attempt(world.ports, world.run.id, 1)

    assert world.ports.uow.calls == ["enter", "commit", "exit"]


# ── the second row is not a second beginning ─────────────────────────────────


def test_a_later_row_starting_leaves_the_run_and_the_record_alone() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "queued"})

    start_attempt(world.ports, world.run.id, 2)

    assert world.status_of("checkout") == "running"
    assert world.stored_run().status == "running"
    assert world.records() == []


def test_a_re_attempt_is_numbered_from_the_rows_own_latest() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "queued"})
    an_attempt(world, "plan", n=1, status="error", ended_at=world.clock.now())

    assert start_attempt(world.ports, world.run.id, 1).n == SECOND


# ── the refusals ─────────────────────────────────────────────────────────────


def test_starting_a_row_of_a_run_that_is_not_stored_is_a_not_found() -> None:
    world = a_queued_pair()

    with pytest.raises(NotFound):
        start_attempt(world.ports, new_id(), 1)


def test_starting_a_seq_the_plan_does_not_have_is_a_not_found() -> None:
    world = a_queued_pair()

    with pytest.raises(NotFound):
        start_attempt(world.ports, world.run.id, 99)


def test_starting_a_row_of_a_parked_run_is_a_bug_and_raises() -> None:
    """Only `signal_run` resumes a Run; a walker that started one has skipped that (AD-8)."""
    world = a_world("needs_you", PAIR_PLAN, {"plan": "queued"}, park_kind="blocked")

    with pytest.raises(InvalidTransition) as raised:
        start_attempt(world.ports, world.run.id, 1)

    assert "needs_you" in str(raised.value)


def test_starting_a_row_that_is_not_queued_raises_naming_its_status() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done"})

    with pytest.raises(InvalidTransition) as raised:
        start_attempt(world.ports, world.run.id, 1)

    assert "done" in str(raised.value)


def test_nothing_is_committed_when_the_start_refuses() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done"})

    with pytest.raises(InvalidTransition):
        start_attempt(world.ports, world.run.id, 1)

    assert not world.ports.uow.committed
