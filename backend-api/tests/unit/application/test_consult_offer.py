"""The consult offer (story 1-4, spine AD-22, 2026-11-02): a qualifying `blocked` stop is
returned as `error` plus `Consult{kind, question, snapshot}` instead of a park, after both
trees are swept into a WIP commit. Every other stop is returned exactly as it was."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from orchestrator.application.steps import agent_consult
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.harness import HarnessCapabilities, HarnessResult
from orchestrator.domain.values import Consult, Park, StepResult
from tests.unit.application.consult_fixtures import (
    CONDITION,
    QUESTION,
    a_blocking_world,
    consulting,
    planned,
    with_consults,
)
from tests.unit.application.steps.agent_budget_fixtures import spend, with_spend
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    ROW_PATH,
    STORY_ID,
    WORKTREE,
    World,
    a_run,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    END_SHA,
    LOG_PATH,
    a_section,
    a_story,
    contracted,
)
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness

SWEEP = f"wip: story {STORY_ID} attempt 1 (consult)"
DIRTY = " M src/app.py"


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def a_dirty_git(**over: Any) -> FakeGit:
    """The agent left a modified file behind. The fake scripts answers rather than simulating
    git, so the status stays dirty after the sweep: a commit is asserted, not a clean tree."""
    fields: dict[str, Any] = {"status": [DIRTY], "head_sha": [HEAD_SHA, END_SHA]}
    fields.update(over)
    return FakeGit(**fields)


def test_a_declared_blocked_stop_becomes_an_offer() -> None:
    world = a_blocking_world(git=a_dirty_git())

    result = run(world)

    assert result.status == "error"
    assert result.park is None
    assert result.reason == f"consult: {QUESTION}"
    assert result.output_ref == str(LOG_PATH)
    assert result.consult is not None
    assert result.consult.kind == "blocked"
    assert result.consult.question == QUESTION
    assert result.consult.outcome is None


def test_the_offer_sweeps_the_tree_before_it_takes_the_snapshot() -> None:
    world = a_blocking_world(git=a_dirty_git())

    result = run(world)

    assert (Path(WORKTREE), SWEEP) in world.git.called("commit")
    assert result.consult is not None
    assert result.consult.snapshot == {"tree": {"head": END_SHA, "status": DIRTY}}


def test_a_clean_tree_is_not_committed() -> None:
    world = a_blocking_world()

    run(world)

    assert not [call for call in world.git.called("commit") if call[1] == SWEEP]


def test_a_workdir_row_sweeps_and_snapshots_both_trees() -> None:
    member = f"{WORKTREE}/repos/member"
    git = FakeGit(
        heads={member: ["a" * 40, "b" * 40, "c" * 40], WORKTREE: ["d" * 40, "e" * 40, "f" * 40]},
        statuses={member: "", WORKTREE: " M repos/member"},
    )
    world = a_blocking_world(git=git, with_resolved=consulting(workdir="repos/member"))

    result = run(world)

    assert result.consult is not None
    assert set(result.consult.snapshot) == {"tree", "root"}
    assert result.consult.snapshot["root"]["status"] == " M repos/member"


def test_a_sweep_git_refuses_parks_as_today_with_gits_words() -> None:
    refused = GitError(command="git commit", exit_code=1, output="index.lock exists")
    world = a_blocking_world(git=a_dirty_git(commit=[refused]))

    result = run(world)

    expected = f"{QUESTION} · consult failed: index.lock exists"
    assert result.status == "blocked"
    assert result.consult is None
    assert result.reason == expected
    assert result.park == Park(kind="blocked", reason=expected, path=ROW_PATH)


# ── not offered: behaviour as today ──────────────────────────────────────────


def as_today(world: World) -> None:
    result = run(world)

    assert result.consult is None
    assert result.status == "blocked"
    assert result.park == Park(kind="blocked", reason=QUESTION, path=ROW_PATH)


def test_a_row_without_a_consult_parks_as_today() -> None:
    as_today(a_blocking_world(with_resolved=contracted()))


def test_a_used_consult_parks_as_today() -> None:
    world = with_consults(a_blocking_world(), {"blocked": {"state": "answer"}})

    as_today(world)


def test_an_attempt_without_a_session_parks_as_today() -> None:
    harness = FakeHarness(results=[HarnessResult(session_id=None, exit_code=0, log_path=LOG_PATH)])

    as_today(a_blocking_world(harness=harness))


def test_a_harness_that_cannot_resume_parks_as_today() -> None:
    harness = FakeHarness(capabilities=HarnessCapabilities(preassign_session=True, resume=False))

    as_today(a_blocking_world(harness=harness))


def test_a_consult_declared_on_another_kind_only_parks_as_today() -> None:
    as_today(a_blocking_world(with_resolved=contracted(consult=planned(on=["protected_path"]))))


def test_another_stop_kind_is_never_offered() -> None:
    world = a_blocking_world(
        story=a_story("ready-for-dev"), with_resolved=consulting(spec_checkpoint=True)
    )

    result = run(world)

    assert result.status == "checkpoint"
    assert result.consult is None


def test_a_misconfigured_condition_is_never_offered() -> None:
    world = a_blocking_world(story=a_story("blocked", "no subagents"))

    result = run(world)

    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.consult is None


def test_a_blocked_stop_that_is_also_over_budget_parks_as_today() -> None:
    gateway = FakeGateway()
    world = with_spend(
        a_blocking_world(run=a_run(budget_usd=Decimal("1.00"), spend_usd=Decimal("0"))),
        gateway=gateway,
    )
    gateway.script(world.run.id, world.attempt.id, spend("5.00"))

    result = run(world)

    assert result.consult is None
    assert result.park is not None
    assert result.park.kind == "blocked"
    assert result.budget_park is not None


def test_an_offer_passes_through_a_result_that_is_not_a_blocked_park() -> None:
    world = a_blocking_world()
    finished = StepResult(status="done", gate="liveness")

    assert agent_consult.offer(world.ctx, world.attempt, finished) is finished


def test_the_question_is_the_park_reason_the_operator_would_read() -> None:
    assert a_section("blocked", CONDITION) == QUESTION
    assert Consult(kind="blocked", question=QUESTION).snapshot == {}
