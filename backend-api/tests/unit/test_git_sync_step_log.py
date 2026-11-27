"""`git.sync` writes its log (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.git_sync import DIVERGED, KIND, GitSyncExecutor
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import BRANCH, a_context, a_row, a_worktree, an_environment, without

A, B = "a" * 40, "b" * 40


def a_sync_context(git: FakeGit, **with_resolved: object) -> StepContext:
    row = a_row(kind=KIND, with_resolved={"timeout_min": 5, **with_resolved}, path="sync")
    return a_context(row, git=git, env=an_environment(worktrees=(a_worktree(),)))


def lines_of(ctx: StepContext) -> tuple[str, ...]:
    return ctx.ports.step_log.writes[0][3]  # type: ignore[union-attr]


def test_a_done_sync_logs_each_git_call_in_order_and_names_the_path() -> None:
    git = FakeGit(sync=["Fast-forward\n"])
    ctx = a_sync_context(git)

    result = GitSyncExecutor().execute(ctx)

    assert result.log_path == str(log_path(ctx))
    writes = ctx.ports.step_log.writes  # type: ignore[union-attr]
    assert [w[:3] for w in writes] == [(ctx.attempt.run_id, ctx.row.seq, ctx.attempt.n)]
    ops = [line.split()[1] for line in lines_of(ctx) if line.startswith("> ")]
    assert ops == [call[0] for call in git.calls]
    assert "  Fast-forward" in lines_of(ctx)


def test_a_diverged_sync_still_parks_and_its_log_ends_with_the_error() -> None:
    git = FakeGit(sync=[GitError(command="git pull", exit_code=1, output="rejected")])
    ctx = a_sync_context(git)

    result = GitSyncExecutor().execute(ctx)

    assert result.park is not None and result.park.kind == "push_rejected"
    assert result.reason == DIVERGED
    assert result.log_path == str(log_path(ctx))
    assert lines_of(ctx)[-2:] == ("  error · exit 1", "  rejected")


def test_a_head_that_moved_logs_the_refs_line_on_the_recorded_branch() -> None:
    ctx = a_sync_context(FakeGit(sync=["ok"], head_sha=[A, B]))

    GitSyncExecutor().execute(ctx)

    assert f"refs updated: {BRANCH} aaaaaaa → bbbbbbb" in lines_of(ctx)


def test_a_resolved_branch_wins_over_the_recorded_one() -> None:
    ctx = a_sync_context(FakeGit(sync=["ok"], head_sha=[A, B]), branch="feat/x")

    GitSyncExecutor().execute(ctx)

    assert "refs updated: feat/x aaaaaaa → bbbbbbb" in lines_of(ctx)


def test_a_head_that_did_not_move_or_is_missing_logs_no_refs_line() -> None:
    for heads in ([A], [None]):
        ctx = a_sync_context(FakeGit(sync=["ok"], head_sha=heads))

        GitSyncExecutor().execute(ctx)

        assert not [line for line in lines_of(ctx) if line.startswith("refs updated:")]


def test_without_a_step_log_the_result_is_the_same_minus_the_path() -> None:
    with_log = GitSyncExecutor().execute(a_sync_context(FakeGit(sync=[None])))
    ctx = without(a_sync_context(FakeGit(sync=[None])), step_log=None)

    bare = GitSyncExecutor().execute(ctx)

    assert bare.log_path is None
    assert bare.model_dump(exclude={"log_path"}) == with_log.model_dump(exclude={"log_path"})


def test_a_head_that_cannot_be_read_leaves_the_outcome_alone() -> None:
    timeout = GitError(command="git rev-parse", exit_code=124, output="timed out")
    ctx = a_sync_context(FakeGit(sync=["Fast-forward"], head_sha=[timeout, timeout]))

    result = GitSyncExecutor().execute(ctx)

    assert result.status == "done" and result.output_ref == "Fast-forward"
    assert not [line for line in lines_of(ctx) if line.startswith("refs updated:")]
    assert "  error · exit 124" in lines_of(ctx)
