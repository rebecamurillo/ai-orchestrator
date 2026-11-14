"""RM-1 at the senior consult: the attempt that ends gets exactly one fact set."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.steps import agent_consult_senior
from tests.unit.application.consult_fixtures import a_consult_world
from tests.unit.application.steps.test_agent_consult_senior import a_senior
from tests.unit.fakes.facts_scope import FactsScope


def test_a_consulting_attempt_that_ends_gets_one_fact_set() -> None:
    world = a_consult_world()
    scope = FactsScope()
    ctx = replace(world.ctx, ports=replace(world.ctx.ports, facts_writes=scope))

    agent_consult_senior.dispatch(ctx, a_senior(world))

    [stored] = scope.repository.sets
    assert stored.attempt_id == world.attempt.id
    assert stored.status == "ok"
