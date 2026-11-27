"""`git.merge` writes its log (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.git_merge import KIND, GitMergeExecutor
from orchestrator.domain.ports.git import NO_UPSTREAM, GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import BRANCH, a_context, a_row, a_worktree, an_environment, without

A, B = "a" * 40, "b" * 40


def a_merge_context(git: FakeGit, **extra: object) -> StepContext:
    row = a_row(kind=KIND, with_resolved={"from": "feat/epic-1", "timeout_min": 5, **extra})
    return a_context(row, git=git, env=an_environment(worktrees=(a_worktree(),)))


def lines_of(ctx: StepContext) -> tuple[str, ...]:
    return ctx.ports.step_log.writes[0][3]  # type: ignore[union-attr]


def test_a_merge_logs_each_call_in_order_and_names_the_path() -> None:
    git = FakeGit(merge=["beef"])
    ctx = a_merge_context(git)

    result = GitMergeExecutor().execute(ctx)

    assert result.log_path == str(log_path(ctx))
    assert len(ctx.ports.step_log.writes) == 1  # type: ignore[union-attr]
    ops = [line.split()[1] for line in lines_of(ctx) if line.startswith("> ")]
    assert ops == [call[0] for call in git.calls]


def test_a_moved_head_logs_the_refs_line_and_a_resolved_branch_wins() -> None:
    ctx = a_merge_context(FakeGit(merge=["beef"], head_sha=[A, B]))
    GitMergeExecutor().execute(ctx)
    assert f"refs updated: {BRANCH} aaaaaaa → bbbbbbb" in lines_of(ctx)

    ctx = a_merge_context(FakeGit(merge=["beef"], head_sha=[A, B]), branch="feat/x")
    GitMergeExecutor().execute(ctx)
    assert "refs updated: feat/x aaaaaaa → bbbbbbb" in lines_of(ctx)


def test_an_unmoved_or_missing_head_logs_no_refs_line() -> None:
    for heads in ([A], [None]):
        ctx = a_merge_context(FakeGit(merge=["beef"], head_sha=heads))
        GitMergeExecutor().execute(ctx)
        assert not [line for line in lines_of(ctx) if line.startswith("refs updated:")]


def test_the_other_outcomes_carry_the_log_and_keep_their_fields() -> None:
    conflict = GitError(command="git merge", exit_code=1, output="CONFLICT")
    for script in ([NO_UPSTREAM], [None], [conflict]):
        ctx = a_merge_context(FakeGit(merge=script))
        bare = without(a_merge_context(FakeGit(merge=script)), step_log=None)

        result = GitMergeExecutor().execute(ctx)
        plain = GitMergeExecutor().execute(bare)

        assert result.log_path == str(log_path(ctx))
        assert plain.log_path is None
        assert plain.model_dump(exclude={"log_path"}) == result.model_dump(exclude={"log_path"})
    assert lines_of(ctx)[-2:] == ("  error · exit 1", "  CONFLICT")


def test_a_head_that_cannot_be_read_leaves_the_outcome_alone() -> None:
    timeout = GitError(command="git rev-parse", exit_code=124, output="timed out")
    ctx = a_merge_context(FakeGit(merge=["beef"], head_sha=[timeout, timeout, A]))

    result = GitMergeExecutor().execute(ctx)

    assert result.status == "done" and result.output_ref == "beef"
    assert not [line for line in lines_of(ctx) if line.startswith("refs updated:")]
