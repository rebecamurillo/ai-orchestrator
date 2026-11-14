"""RM-1 at `commit_turn`: each session turn that closes gets exactly one fact set."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.use_cases.session_turn import commit_turn
from tests.unit.application.session_turn_fixtures import TurnWorld, a_turn_world
from tests.unit.fakes.facts_scope import FactsScope


def committed(world: TurnWorld, scope: FactsScope, attempt_id: object) -> None:
    ports = replace(world.ports, step=replace(world.step, facts_writes=scope))
    commit_turn(ports, attempt_id)  # type: ignore[arg-type]


def test_a_turn_that_ran_gets_one_set() -> None:
    world = a_turn_world()
    scope = FactsScope()
    posted = world.post()
    world.run(posted.attempt_id)

    committed(world, scope, posted.attempt_id)

    [stored] = scope.repository.sets
    assert stored.attempt_id == posted.attempt_id


def test_a_turn_closed_as_interrupted_gets_one_set() -> None:
    world = a_turn_world()
    scope = FactsScope()
    posted = world.post()

    committed(world, scope, posted.attempt_id)

    assert world.attempt(posted.attempt_id).status == "error"
    assert [s.attempt_id for s in scope.repository.sets] == [posted.attempt_id]
