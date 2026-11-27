"""`git.push` of the merge Run's default branch checks the anchors first (epic 8 retrospective
R1, Operator ruling 2026-11-26).

Every anchor or existing test file in `origin/{branch}..HEAD` must read at HEAD as it reads at
the tip of the merge's source branch, the `from` of the last `git.merge` row before the push.
Otherwise the row parks `protected_path` and pushes nothing; a `continue` naming the paths
lets them stand through `run.accepted_paths`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.application.rules.protected_paths import HITS_KEY
from orchestrator.application.rules.push_anchors import NO_MERGE_SOURCE
from orchestrator.application.steps import StepPorts
from orchestrator.application.steps.context import RunEnvironment, StepContext
from orchestrator.application.steps.git_push import GitPushExecutor
from orchestrator.application.use_cases import walk_context
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.initiative_fixtures import a_run
from tests.unit.step_fixtures import (
    DEFAULT_BRANCH,
    WORKTREE,
    a_context,
    a_row,
    a_worktree,
    an_environment,
)

SOURCE = "spec/my-initiative"
HEAD_SHA = "feed0123456789abcdefbeef0123456789abcdef"
ANCHOR = "AGENTS.md"
CODE = "src/app.py"
INITIATIVE = {"initiative_id": new_id(), "initiative_round": 1, "initiative_position": 1}


def a_plan_row(kind: str, seq: int, **with_resolved: Any) -> StepRun:
    row = a_row(kind=kind, with_resolved=dict(with_resolved), path=f"row-{seq}")
    return row.model_copy(update={"seq": seq})


def merge_row(seq: int = 1, source: str = SOURCE) -> StepRun:
    return a_plan_row("git.merge", seq, **{"from": source})


def push_row() -> StepRun:
    return a_plan_row("git.push", 2, branch=DEFAULT_BRANCH, allow_default_branch=True)


def a_push_context(
    git: FakeGit,
    *,
    run: Run | None = None,
    rows: tuple[StepRun, ...] | None = None,
    accepted: tuple[str, ...] = (),
) -> StepContext:
    row = push_row()
    env = an_environment(
        worktrees=(a_worktree(branch=DEFAULT_BRANCH, created_branch=False),),
        run=run if run is not None else a_run(**INITIATIVE),
        plan_rows=rows if rows is not None else (merge_row(), row),
        test_globs=("tests/**/*.py",),
        accepted_paths=accepted,
    )
    return a_context(row, git=git, env=env)


def a_git(path: str, head: str, source: str) -> FakeGit:
    return FakeGit(
        push=["ok"],
        changes={WORKTREE: (Change(path=path, kind="modified"),)},
        files={(HEAD_SHA, path): head, (SOURCE, path): source},
        heads={WORKTREE: [HEAD_SHA]},
    )


def execute(ctx: StepContext) -> StepResult:
    return GitPushExecutor().execute(ctx)


def test_an_agent_resolved_anchor_that_differs_from_the_source_parks_before_the_push() -> None:
    git = a_git(ANCHOR, head="agent's", source="spec's")

    result = execute(a_push_context(git))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.reason == f"protected path modified: {ANCHOR}"
    assert [entry["path"] for entry in result.payload[HITS_KEY]] == [ANCHOR]
    assert git.called("push") == []
    assert git.called("diff_changes") == [(Path(WORKTREE), f"origin/{DEFAULT_BRANCH}", "HEAD")]


def test_head_is_read_at_its_sha_and_the_source_at_the_merge_from() -> None:
    git = a_git(ANCHOR, head="same", source="same")

    execute(a_push_context(git))

    assert [(ref, path) for _, ref, path in git.called("read_file")] == [
        (HEAD_SHA, ANCHOR),
        (SOURCE, ANCHOR),
    ]


def test_an_anchor_equal_to_the_source_pushes() -> None:
    git = a_git(ANCHOR, head="same", source="same")

    result = execute(a_push_context(git))

    assert result.status == "done"
    assert len(git.called("push")) == 1


def test_a_resolution_outside_the_anchors_pushes_without_reading_it() -> None:
    git = a_git(CODE, head="agent's", source="spec's")

    result = execute(a_push_context(git))

    assert result.status == "done"
    assert git.called("read_file") == []
    assert len(git.called("push")) == 1


def test_after_a_continue_with_accepted_paths_the_push_goes_through() -> None:
    git = a_git(ANCHOR, head="agent's", source="spec's")

    result = execute(a_push_context(git, accepted=(ANCHOR,)))

    assert result.status == "done"
    assert len(git.called("push")) == 1


def test_a_run_without_an_initiative_is_not_checked() -> None:
    git = a_git(ANCHOR, head="agent's", source="spec's")

    result = execute(a_push_context(git, run=a_run()))

    assert result.status == "done"
    assert git.called("diff_changes") == []
    assert len(git.called("push")) == 1


def test_no_merge_row_before_the_push_parks_blocked_and_pushes_nothing() -> None:
    git = a_git(ANCHOR, head="same", source="same")
    after = merge_row(seq=3)

    result = execute(a_push_context(git, rows=(push_row(), after)))

    assert result.status == "blocked"
    assert result.park is not None
    assert result.park.kind == "blocked"
    assert result.reason == NO_MERGE_SOURCE
    assert git.called("push") == []


def test_the_last_merge_row_before_the_push_names_the_source() -> None:
    git = a_git(ANCHOR, head="same", source="same")
    rows = (merge_row(seq=0, source="spec/older"), merge_row(seq=1), push_row())

    result = execute(a_push_context(git, rows=rows))

    assert result.status == "done"
    assert [ref for _, ref, _ in git.called("read_file")][1] == SOURCE


def test_walk_context_fills_plan_rows_for_a_push_row() -> None:
    world = a_world(
        "running",
        (("merge", "git.merge"), ("push", "git.push")),
        {"merge": "done", "push": "running"},
    )
    an_attempt(world, "push")
    base = RunEnvironment(
        run_id=world.run.id,
        project_slug="acme",
        repository_slug="widgets",
        repository_url="u",
        default_branch="main",
        bmad_version="6.11.0",
        spec_folder=None,
    )
    ports = StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work", run_env=base)

    ctx = walk_context.context(world.ports, ports, world.run, world.row("push").seq, None)

    assert ctx.ports.run_env is not None
    assert [row.path for row in ctx.ports.run_env.plan_rows] == ["merge", "push"]
