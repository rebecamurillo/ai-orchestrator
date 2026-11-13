"""RM-1 at the `agent` tail: one fact set per finished attempt, on every path of `finish`,
and no fact changes what the walker is told."""

from __future__ import annotations

from dataclasses import replace

import pytest

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.context import StepContext
from orchestrator.domain.entities.facts import AttemptFacts, UsageFact
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import World, resolved
from tests.unit.application.steps.agent_tail_fixtures import (
    LOG_PATH,
    SESSION_ID,
    a_tail_world,
    contracted,
)
from tests.unit.fakes.facts_scope import FactsScope
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.log_facts import ScriptedLogFacts

ROWS = AttemptFacts(usage=(UsageFact(source="harness", usage_class="output", tokens=3),))


def with_facts(world: World, scope: FactsScope | None) -> StepContext:
    return replace(world.ctx, ports=replace(world.ctx.ports, facts_writes=scope))


def a_killed_world(**result: object) -> World:
    harness = FakeHarness()
    world = a_tail_world(harness=harness, with_resolved=contracted(timeout_min=60, stall_min=30))
    harness.results[0] = HarnessResult(
        session_id=SESSION_ID,
        exit_code=None,
        log_path=LOG_PATH,
        **result,  # type: ignore[arg-type]
    )
    return world


def test_a_done_attempt_has_exactly_one_ok_set_holding_the_extractors_rows() -> None:
    world = a_tail_world()
    scope = FactsScope(extractor=ScriptedLogFacts(ROWS))

    AgentExecutor().execute(with_facts(world, scope))

    [stored] = scope.repository.sets
    assert (stored.status, stored.extractor, stored.extractor_version) == ("ok", "fake", 1)
    assert stored.attempt_id == world.attempt.id
    assert stored.run_id == world.attempt.run_id
    assert stored.read_at == world.clock.now()
    assert scope.repository.rows(stored.id) == ROWS


@pytest.mark.parametrize("kill", [{"timed_out": True}, {"stalled": True, "stall_cwd": "/w"}])
def test_a_killed_attempt_has_one_set_and_parks_as_it_did_without_facts(
    kill: dict[str, object],
) -> None:
    scope = FactsScope()
    with_world, without_world = a_killed_world(**kill), a_killed_world(**kill)

    parked = AgentExecutor().execute(with_facts(with_world, scope))
    plain = AgentExecutor().execute(with_facts(without_world, None))

    assert len(scope.repository.sets) == 1
    assert parked.park is not None and parked.park.kind == "timeout"
    assert parked == plain


def test_an_extractor_that_raises_changes_nothing_the_walker_sees() -> None:
    boom = FactsScope(extractor=ScriptedLogFacts(raises=ValueError("bad line")))
    with_world, without_world = a_tail_world(), a_tail_world()

    result: StepResult = AgentExecutor().execute(with_facts(with_world, boom))
    plain = AgentExecutor().execute(with_facts(without_world, None))

    [stored] = boom.repository.sets
    assert stored.status == "failed"
    assert stored.reason is not None and "bad line" in stored.reason
    assert result == plain
    ours = with_world.attempts.attempts[with_world.attempt.id]
    theirs = without_world.attempts.attempts[without_world.attempt.id]
    ids = {"id", "run_id", "step_run_id"}
    assert ours.model_dump(exclude=ids) == theirs.model_dump(exclude=ids)


def test_a_scope_that_cannot_be_opened_is_swallowed() -> None:
    world = a_tail_world()
    scope = FactsScope(fail_open=True)

    result = AgentExecutor().execute(with_facts(world, scope))

    assert result == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))
    assert scope.opens == 1


def test_a_row_with_no_facts_scope_records_nothing() -> None:
    world = a_tail_world(with_resolved=resolved())
    assert world.ctx.ports.facts_writes is None
    AgentExecutor().execute(world.ctx)
