"""The consult offer at a `protected_path` stop (story 1-8, spine AD-17/AD-22, hard rule 1 as
amended 2026-11-02). A hit on frozen tests only, on a row that declares the stop and has not
used it, becomes `error` plus `Consult{kind, question, snapshot, hits}`: the stopped attempt's
spend is recorded first, then both trees are swept and snapshotted. A hit holding a document,
a stall or timeout hit, and every row that did not declare the stop park as today."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from orchestrator.application.steps import agent_consult
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.agent_tail import PROTECTED
from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.domain.ports.git import Change, GitError
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import Park, StepResult
from tests.unit.application.consult_fixtures import consulting, planned, with_consults
from tests.unit.application.steps.agent_budget_fixtures import spend
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    ROW_PATH,
    SPEC_FOLDER,
    WORKTREE,
    World,
    a_run,
)
from tests.unit.application.steps.agent_tail_fixtures import END_SHA, LOG_PATH, a_tail_world
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

SPEC_MD = f"{SPEC_FOLDER}/SPEC.md"
FROZEN = "tests/a.py"
OTHER = "tests/b.py"
ANCHORS = frozenset({SPEC_MD, FROZEN, OTHER})
REVIEWING = ["blocked", "protected_path"]
DIRTY = " M src/app.py"
SWEEP = "wip: story 4-1 attempt 1 (consult)"


def reason_for(*paths: str, hidden: str = "story done") -> str:
    return f"{PROTECTED.format(paths=', '.join(paths))} · {hidden}"


def hits_of(*paths: str) -> dict[str, Any]:
    return {"hits": [{"path": path, "kind": "modified"} for path in paths]}


def a_git(*paths: str, status: str = "", **over: Any) -> FakeGit:
    fields: dict[str, Any] = {
        "status": [status],
        "head_sha": [HEAD_SHA, END_SHA],
        "diff_changes": [tuple(Change(path=path, kind="modified") for path in paths)],
    }
    fields.update(over)
    return FakeGit(**fields)


def with_anchors(world: World) -> World:
    environment = world.ctx.ports.run_env
    assert environment is not None
    ports = replace(world.ctx.ports, run_env=replace(environment, anchors=ANCHORS))
    return replace(world, ctx=replace(world.ctx, ports=ports))


def a_hit_world(*paths: str, on: list[str] | None = None, **over: Any) -> World:
    """A dispatch whose own range modified `paths`, on a row consulting on `on`."""
    fields: dict[str, Any] = {
        "git": a_git(*paths),
        "with_resolved": consulting(consult=planned(on=on if on is not None else REVIEWING)),
    }
    fields.update(over)
    return with_anchors(a_tail_world(**fields))


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def parks_as_today(world: World, reason: str, *paths: str) -> None:
    result = run(world)

    assert result.consult is None
    assert result.status == "error"
    assert result.park == Park(kind="protected_path", reason=reason, path=ROW_PATH)
    assert result.payload == hits_of(*paths)


# ── the offer ────────────────────────────────────────────────────────────────


def test_a_hit_on_frozen_tests_only_becomes_an_offer() -> None:
    world = a_hit_world(FROZEN, OTHER)

    result = run(world)

    question = reason_for(FROZEN, OTHER)
    assert result.status == "error"
    assert result.park is None
    assert result.reason == f"consult: {question}"
    assert result.output_ref == str(LOG_PATH)
    assert result.consult is not None
    assert (result.consult.kind, result.consult.question) == ("protected_path", question)
    assert result.consult.outcome is None
    assert result.consult.hits == hits_of(FROZEN, OTHER)


def test_the_offer_sweeps_the_tree_before_it_takes_the_snapshot() -> None:
    world = a_hit_world(FROZEN, git=a_git(FROZEN, status=DIRTY))

    result = run(world)

    assert (Path(WORKTREE), SWEEP) in world.git.called("commit")
    assert result.consult is not None
    assert result.consult.snapshot == {"tree": {"head": END_SHA, "status": DIRTY}}


def test_an_attempt_without_a_session_is_offered_too() -> None:
    harness = FakeHarness(results=[HarnessResult(session_id=None, exit_code=0, log_path=LOG_PATH)])

    result = run(a_hit_world(FROZEN, harness=harness))

    assert result.consult is not None
    assert result.consult.kind == "protected_path"


def spend_scope(world: World, gateway: FakeGateway) -> tuple[World, FakeRunRepository]:
    """`agent_budget_fixtures.with_spend`'s scope, keeping its Run repository to read back."""
    runs = FakeRunRepository([world.run])
    steps = FakeStepRunRepository([world.row])
    attempts = FakeAttemptRepository([world.attempt])

    @contextmanager
    def open_scope() -> Iterator[SpendPorts]:
        yield SpendPorts(
            gateway=gateway, runs=runs, steps=steps, attempts=attempts, uow=FakeUnitOfWork()
        )

    ports = replace(world.ctx.ports, spend_writes=open_scope)
    return replace(world, ctx=replace(world.ctx, ports=ports)), runs


def test_the_stopped_attempts_spend_is_recorded_before_the_offer() -> None:
    gateway = FakeGateway()
    world, runs = spend_scope(
        a_hit_world(FROZEN, run=a_run(budget_usd=Decimal("10.00"), spend_usd=Decimal("0"))),
        gateway,
    )
    gateway.script(world.run.id, world.attempt.id, spend("2.00"))

    result = run(world)

    assert result.consult is not None
    stored = runs.get(world.run.id)
    assert stored is not None
    assert stored.spend_usd == Decimal("2.00")


def test_a_hit_offered_with_no_dispatch_result_records_no_spend() -> None:
    gateway = FakeGateway()
    world, runs = spend_scope(
        a_hit_world(FROZEN, run=a_run(budget_usd=Decimal("10.00"), spend_usd=Decimal("0"))),
        gateway,
    )
    gateway.script(world.run.id, world.attempt.id, spend("2.00"))
    hit = StepResult(
        status="error",
        gate="liveness",
        reason=reason_for(FROZEN),
        park=Park(kind="protected_path", reason=reason_for(FROZEN), path=ROW_PATH),
        payload=hits_of(FROZEN),
    )

    result = agent_consult.offer(world.ctx, world.attempt, hit)

    assert result.consult is not None
    assert result.consult.hits == hits_of(FROZEN)
    stored = runs.get(world.run.id)
    assert stored is not None
    assert stored.spend_usd == Decimal("0")


def test_a_sweep_git_refuses_parks_as_today_with_gits_words() -> None:
    refused = GitError(command="git commit", exit_code=1, output="index.lock exists")
    world = a_hit_world(FROZEN, git=a_git(FROZEN, status=DIRTY, commit=[refused]))

    parks_as_today(world, f"{reason_for(FROZEN)} · consult failed: index.lock exists", FROZEN)


# ── not offered: the park of today ───────────────────────────────────────────


def test_a_hit_holding_a_document_is_never_offered() -> None:
    world = a_hit_world(FROZEN, SPEC_MD)

    parks_as_today(world, reason_for(FROZEN, SPEC_MD), FROZEN, SPEC_MD)


def test_a_row_consulting_on_blocked_only_parks_as_today() -> None:
    parks_as_today(a_hit_world(FROZEN, on=["blocked"]), reason_for(FROZEN), FROZEN)


def test_a_row_without_a_consult_parks_as_today() -> None:
    world = with_anchors(a_tail_world(git=a_git(FROZEN)))

    parks_as_today(world, reason_for(FROZEN), FROZEN)


def test_a_used_review_parks_as_today() -> None:
    world = with_consults(a_hit_world(FROZEN), {"protected_path": {"state": "escalate"}})

    parks_as_today(world, reason_for(FROZEN), FROZEN)


def test_a_stalled_hit_is_never_offered() -> None:
    harness = FakeHarness()
    harness.results.append(
        HarnessResult(
            session_id="s-1",
            exit_code=None,
            stalled=True,
            stall_cwd=Path(WORKTREE),
            log_path=LOG_PATH,
        )
    )

    parks_as_today(
        a_hit_world(FROZEN, harness=harness), reason_for(FROZEN, hidden="stalled"), FROZEN
    )


def test_a_timed_out_hit_is_never_offered() -> None:
    harness = FakeHarness()
    harness.results.append(
        HarnessResult(session_id="s-1", exit_code=None, timed_out=True, log_path=LOG_PATH)
    )

    result = run(a_hit_world(FROZEN, harness=harness))

    assert result.consult is None
    assert result.park is not None
    assert result.park.kind == "protected_path"
