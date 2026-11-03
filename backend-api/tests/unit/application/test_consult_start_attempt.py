"""`start_attempt` and the consult (story 1-4, spine AD-21/AD-22, 2026-11-02).

A row whose consult entry is `due` opens a `consult` attempt; every other row opens an
`agent` attempt, and both are written with their role. An interrupted consult attempt hands
its process group to the entry, because the timers that bounded it died with the backend."""

from __future__ import annotations

from typing import Any

from orchestrator.application.use_cases.start_attempt import start_attempt
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt

BUILD = "stories[0].build"
DUE = {"state": "due", "question": "q", "snapshot": {}}


def a_queued_world(status: str = "queued", consults: dict[str, Any] | None = None) -> World:
    world = a_world("running", EPIC_PLAN, {BUILD: status})  # type: ignore[dict-item]
    world.ports.steps.update(world.row(BUILD).model_copy(update={"consults": consults or {}}))
    return world


def start(world: World) -> None:
    start_attempt(world.ports, world.run.id, world.row(BUILD).seq)


def test_a_due_consult_opens_a_consult_attempt_stored_with_its_role() -> None:
    world = a_queued_world(consults={"blocked": DUE})
    an_attempt(world, BUILD, n=1, status="error", ended_at=world.clock.now())

    start(world)

    latest = world.attempts_of(BUILD)[-1]
    assert (latest.n, latest.role) == (2, "consult")
    assert world.row(BUILD).status == "running"


def test_a_row_with_no_due_consult_opens_an_agent_attempt() -> None:
    world = a_queued_world(consults={"blocked": {**DUE, "state": "answer", "answered_by": 2}})

    start(world)

    assert world.attempts_of(BUILD)[-1].role == "agent"


def test_an_interrupted_consult_hands_its_process_group_to_the_entry() -> None:
    world = a_queued_world("running", consults={"blocked": DUE})
    an_attempt(world, BUILD, n=1, status="error", ended_at=world.clock.now())
    an_attempt(world, BUILD, n=2, role="consult", pgid=4321)

    start(world)

    attempts = world.attempts_of(BUILD)
    assert attempts[1].status == "error"
    assert attempts[1].ended_at is not None
    assert (attempts[2].n, attempts[2].role) == (3, "consult")
    assert world.row(BUILD).consults["blocked"] == {**DUE, "orphan_pgid": 4321}
    assert "consult" not in world.events()


def test_an_interrupted_consult_that_recorded_no_group_hands_over_none() -> None:
    world = a_queued_world("running", consults={"blocked": {**DUE, "orphan_pgid": 99}})
    an_attempt(world, BUILD, n=1, role="consult")

    start(world)

    assert world.row(BUILD).consults["blocked"]["orphan_pgid"] is None


def test_an_interrupted_agent_attempt_leaves_the_entries_alone() -> None:
    world = a_queued_world("running", consults={"blocked": {**DUE, "state": "answer"}})
    an_attempt(world, BUILD, n=1, pgid=55)

    start(world)

    assert world.row(BUILD).consults == {"blocked": {**DUE, "state": "answer"}}
    assert world.attempts_of(BUILD)[-1].role == "agent"
