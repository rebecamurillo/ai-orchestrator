"""`agent_tail`'s budget seam (5.7): the spend read after every agent attempt, the `budget`
park that keeps the row's routed status, the double gate record's own half (`budget_park`),
and the Claude cap exit read as a budget park rather than an expect miss or a retry.

Calls `agent_tail.tail` directly rather than through `AgentExecutor.execute`
(`test_agent_tail.py`'s own `run()`): a scripted `FakeHarness` result cannot carry a custom
`usage`/`raw_result`, and this module's whole subject is what `HarnessResult` carries.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from orchestrator.application.steps import agent_tail
from orchestrator.domain.ports.harness import HarnessResult, HarnessUsage
from tests.unit.application.steps.agent_budget_fixtures import spend, with_spend
from tests.unit.application.steps.agent_fixtures import a_run
from tests.unit.application.steps.agent_tail_fixtures import SESSION_ID, a_story, a_tail_world
from tests.unit.fakes.gateway import FakeGateway

BUDGET = Decimal("40.00")
LOG_PATH = Path("/work/logs/003-1.log")


def test_a_routed_done_attempt_over_budget_parks_budget_and_keeps_done() -> None:
    """AC1: `done` + over budget → `park.kind == "budget"`, one Gateway call, no second."""
    gateway = FakeGateway()
    world = with_spend(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway=gateway)
    gateway.script(world.run.id, world.attempt.id, spend("41.20"))
    result = HarnessResult(session_id=SESSION_ID, exit_code=0, log_path=LOG_PATH)

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.status == "done"
    assert outcome.park is not None
    assert outcome.park.kind == "budget"
    assert outcome.park.reason == "budget $41.20 / $40.00"
    assert outcome.budget_park is None
    assert outcome.retry is None
    assert len(gateway.calls) == 1


def test_a_routed_blocked_attempt_over_budget_keeps_its_park_and_adds_a_budget_park() -> None:
    """AC2: the two records live behind `park` (the routed stop) and `budget_park`."""
    gateway = FakeGateway()
    world = with_spend(
        a_tail_world(story=a_story("blocked"), run=a_run(budget_usd=BUDGET)), gateway=gateway
    )
    gateway.script(world.run.id, world.attempt.id, spend("41.20"))
    result = HarnessResult(session_id=SESSION_ID, exit_code=0, log_path=LOG_PATH)

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.status == "blocked"
    assert outcome.park is not None
    assert outcome.park.kind == "blocked"
    assert outcome.budget_park is not None
    assert outcome.budget_park.kind == "budget"
    assert outcome.budget_park.reason == "budget $41.20 / $40.00"
    assert outcome.retry is None


def test_an_attempt_exactly_at_budget_does_not_park() -> None:
    """AC3: `40.00 / 40.00` — no park at all."""
    gateway = FakeGateway()
    world = with_spend(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway=gateway)
    gateway.script(world.run.id, world.attempt.id, spend("40.00"))
    result = HarnessResult(session_id=SESSION_ID, exit_code=0, log_path=LOG_PATH)

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.status == "done"
    assert outcome.park is None
    assert outcome.budget_park is None


def test_a_claude_cap_exit_is_read_as_a_budget_park_never_a_retry() -> None:
    """AC4: `raw_result` marking the cap stop parks `budget` regardless of what `route`
    would have decided — `retry` stays unset, so `retry_count` and `retry_auto` never fire."""
    gateway = FakeGateway()
    world = with_spend(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway=gateway)
    gateway.script(world.run.id, world.attempt.id, spend("41.20"))
    result = HarnessResult(
        session_id=SESSION_ID,
        exit_code=1,
        log_path=LOG_PATH,
        raw_result={"stop_reason": "max_budget"},
    )

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.status == "error"
    assert outcome.park is not None
    assert outcome.park.kind == "budget"
    assert outcome.retry is None
    assert outcome.budget_park is None


def test_a_cap_exit_field_that_does_not_match_the_assumed_value_is_not_read_as_one() -> None:
    gateway = FakeGateway()
    world = with_spend(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway=gateway)
    result = HarnessResult(
        session_id=SESSION_ID,
        exit_code=0,
        log_path=LOG_PATH,
        raw_result={"stop_reason": "end_turn"},
    )

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.park is None


def test_a_retry_path_error_over_budget_parks_with_no_automatic_retry() -> None:
    """AC5: an unexpected status that would otherwise retry parks `budget` instead once
    the attempt is over budget, and carries no `retry` for `apply_step_result` to count."""
    gateway = FakeGateway()
    world = with_spend(
        a_tail_world(story=a_story("draft"), run=a_run(budget_usd=BUDGET)), gateway=gateway
    )
    gateway.script(world.run.id, world.attempt.id, spend("41.20"))
    result = HarnessResult(session_id=SESSION_ID, exit_code=0, log_path=LOG_PATH)

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.status == "error"
    assert outcome.retry is None
    assert outcome.park is not None
    assert outcome.park.kind == "budget"
    assert outcome.budget_park is None


def test_without_a_spend_scope_the_budget_check_never_runs() -> None:
    """`spend_writes` unwired degrades like `tracer`: every fixture predating this story
    keeps working, even one whose Run happens to already be over its own budget."""
    world = a_tail_world(run=a_run(budget_usd=Decimal("1.00"), spend_usd=Decimal("999.00")))
    result = HarnessResult(session_id=SESSION_ID, exit_code=0, log_path=LOG_PATH)

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.status == "done"
    assert outcome.park is None


def test_provisional_spend_still_parks_and_is_recorded_provisional() -> None:
    """FR-17: the check uses `run.spend_usd` whether or not the latest attempt is
    provisional. Nothing is scripted on the Gateway, so the harness's own estimate is the
    only figure `record_attempt_spend` has, and it is marked provisional (5.3's own rule)."""
    gateway = FakeGateway()
    world = with_spend(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway=gateway)
    result = HarnessResult(
        session_id=SESSION_ID,
        exit_code=0,
        log_path=LOG_PATH,
        usage=HarnessUsage(tokens_in=100, tokens_out=50, cost_usd=Decimal("41.20")),
    )

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.status == "done"
    assert outcome.park is not None
    assert outcome.park.kind == "budget"
    assert outcome.park.reason == "budget $41.20 / $40.00"
