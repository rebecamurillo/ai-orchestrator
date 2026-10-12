"""O-3, O-5 and O-6 of _bmad-output/specs/unattended-hub-run/PLAN.md at the `agent` tail:
a killed attempt keeps its gateway spend, an unreachable gateway is named before the Story
file is read, and a protected-path park carries the outcome it hides."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from orchestrator.application.steps import agent_tail
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.domain.ports.git import Change
from orchestrator.domain.ports.harness import HarnessResult
from tests.unit.application.steps.agent_budget_fixtures import spend
from tests.unit.application.steps.agent_fixtures import World, a_run
from tests.unit.application.steps.agent_tail_fixtures import (
    LOG_PATH,
    SESSION_ID,
    a_story,
    a_tail_world,
    retried,
)
from tests.unit.application.steps.test_agent_protected_paths import (
    SPEC_MD,
    a_git,
    a_protected_world,
)
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

BUDGET = Decimal("5.00")
API_ERROR = {"is_error": True, "subtype": "error_during_execution", "result": "API Error: refused"}


def _spending(world: World, gateway: FakeGateway) -> tuple[World, FakeRunRepository]:
    runs = FakeRunRepository([world.run])
    attempts = FakeAttemptRepository([world.attempt])
    steps = FakeStepRunRepository([world.row])

    @contextmanager
    def scope() -> Iterator[SpendPorts]:
        yield SpendPorts(
            gateway=gateway, runs=runs, steps=steps, attempts=attempts, uow=FakeUnitOfWork()
        )

    ports = replace(world.ctx.ports, spend_writes=scope)
    return replace(world, ctx=replace(world.ctx, ports=ports)), runs


def _killed(**flags: bool) -> HarnessResult:
    return HarnessResult(
        session_id=SESSION_ID, exit_code=None, log_path=LOG_PATH, stall_cwd=Path("/w"), **flags
    )


def test_a_stalled_attempt_records_its_gateway_spend_and_log_path() -> None:
    gateway = FakeGateway()
    world, runs = _spending(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway)
    gateway.script(world.run.id, world.attempt.id, spend("7.50"))

    result = agent_tail.finish(world.ctx, world.attempt, _killed(stalled=True), None, 30)

    assert result.park is not None
    assert result.park.kind == "timeout"
    assert result.budget_park is None
    stored = runs.get(world.run.id)
    assert stored is not None
    assert stored.spend_usd == Decimal("7.50")
    assert world.attempts.get(world.attempt.id) is not None
    assert gateway.calls == [(world.run.id, world.attempt.id)]
    assert result.output_ref == str(LOG_PATH)


def test_a_stalled_attempt_records_its_log_path_on_the_attempt() -> None:
    world = a_tail_world()

    agent_tail.finish(world.ctx, world.attempt, _killed(stalled=True), None, 30)

    assert world.attempts.get(world.attempt.id) is not None
    assert world.attempts.get(world.attempt.id).log_path == str(LOG_PATH)  # type: ignore[union-attr]


def test_a_timed_out_attempt_records_its_gateway_spend() -> None:
    gateway = FakeGateway()
    world, runs = _spending(a_tail_world(run=a_run(budget_usd=BUDGET)), gateway)
    gateway.script(world.run.id, world.attempt.id, spend("7.50"))

    result = agent_tail.finish(world.ctx, world.attempt, _killed(timed_out=True), 10)

    assert result.park is not None
    assert result.park.kind == "timeout"
    stored = runs.get(world.run.id)
    assert stored is not None
    assert stored.spend_usd == Decimal("7.50")


def test_an_unreachable_gateway_is_named_before_the_story_file_is_read() -> None:
    world = a_tail_world(story=a_story("draft"), exit_code=1)
    result = HarnessResult(
        session_id=SESSION_ID, exit_code=1, log_path=LOG_PATH, raw_result=API_ERROR
    )

    outcome = agent_tail.tail(retried(world, 2), world.attempt, result)

    assert outcome.retry is None
    assert outcome.park is not None
    assert outcome.park.kind == "misconfigured"
    assert outcome.park.reason == "gateway unreachable: API Error: refused"
    assert world.workspace.globbed == []


def test_an_unreachable_gateway_takes_the_rows_bounded_retry() -> None:
    world = a_tail_world(story=a_story("draft"), exit_code=1)
    result = HarnessResult(
        session_id=SESSION_ID, exit_code=1, log_path=LOG_PATH, raw_result=API_ERROR
    )

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert outcome.retry is not None
    assert outcome.park is None
    assert outcome.reason == "gateway unreachable: API Error: refused"


def test_the_budget_cap_stop_is_not_read_as_an_unreachable_gateway() -> None:
    world = a_tail_world(story=a_story("draft"), exit_code=1)
    raw = {"is_error": True, "subtype": "error_max_budget_usd"}
    result = HarnessResult(session_id=SESSION_ID, exit_code=1, log_path=LOG_PATH, raw_result=raw)

    outcome = agent_tail.tail(world.ctx, world.attempt, result)

    assert "gateway unreachable" not in (outcome.reason or "")


def _hidden(world: World) -> str:
    result = AgentExecutor().execute(world.ctx)
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.payload["hits"][0]["path"] == SPEC_MD
    assert result.reason is not None
    return result.reason


def _protected(story: str | None) -> World:
    return a_protected_world(story=story, git=a_git(Change(path=SPEC_MD, kind="modified")))


def test_the_park_names_a_blocked_story_and_its_condition() -> None:
    reason = _hidden(_protected(a_story("blocked", condition="intent gap")))

    assert reason == f"protected path modified: {SPEC_MD} · story blocked: intent gap"


def test_the_park_names_an_unexpected_status() -> None:
    reason = _hidden(_protected(a_story("in-review")))

    assert reason == f"protected path modified: {SPEC_MD} · unexpected status: in-review"


def test_the_park_names_a_missing_story_file() -> None:
    reason = _hidden(_protected(None))

    assert reason == f"protected path modified: {SPEC_MD} · no story file"
