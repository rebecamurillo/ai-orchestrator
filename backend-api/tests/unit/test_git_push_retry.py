"""`git.push` `allow_default_branch` and `retry {max, sync_first}` (epic 8 story 3, AC12, AC13)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext
from orchestrator.application.steps.git_push import (
    DEFAULT_BRANCH as REFUSED_DEFAULT,
)
from orchestrator.application.steps.git_push import (
    REJECTED,
    RETRY_LANDED,
    SYNC_FAILED,
    GitPushExecutor,
)
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import (
    BRANCH,
    DEFAULT_BRANCH,
    a_context,
    a_row,
    a_worktree,
    an_environment,
)

REJECTION = GitError(command="git push", exit_code=1, output="! [rejected] fetch first")
SYNC_FAILURE = GitError(command="git pull", exit_code=1, output="diverged")
RETRY = {"max": 1, "sync_first": True}


def a_context_for(
    git: FakeGit, *, branch: str = BRANCH, created: bool = True, **extra: object
) -> StepContext:
    row = a_row(kind="git.push", with_resolved={"branch": branch, **extra}, path="push")
    env = an_environment(worktrees=(a_worktree(branch=branch, created_branch=created),))
    return a_context(row, git=git, env=env)


def log_lines(ctx: StepContext) -> tuple[str, ...]:
    return ctx.ports.step_log.writes[0][3]  # type: ignore[union-attr]


def test_the_default_branch_is_pushed_when_the_row_allows_it_on_an_attached_worktree() -> None:
    git = FakeGit(push=["ok"])
    ctx = a_context_for(git, branch=DEFAULT_BRANCH, created=False, allow_default_branch=True)

    result = GitPushExecutor().execute(ctx)

    assert result.status == "done"
    [(_, branch, upstream)] = git.called("push")
    assert (branch, upstream) == (DEFAULT_BRANCH, False)


def test_the_default_branch_stays_refused_without_the_key() -> None:
    git = FakeGit()

    result = GitPushExecutor().execute(a_context_for(git, branch=DEFAULT_BRANCH, created=False))

    assert result.park is not None
    assert result.park.reason == REFUSED_DEFAULT.format(branch=DEFAULT_BRANCH)
    assert git.called("push") == []


def test_the_key_does_not_lift_the_refusal_on_a_branch_this_run_created() -> None:
    git = FakeGit()

    result = GitPushExecutor().execute(
        a_context_for(git, branch=DEFAULT_BRANCH, created=True, allow_default_branch=True)
    )

    assert result.park is not None
    assert result.park.reason == REFUSED_DEFAULT.format(branch=DEFAULT_BRANCH)
    assert git.called("push") == []


def test_the_key_must_be_true_not_merely_present() -> None:
    git = FakeGit()

    result = GitPushExecutor().execute(
        a_context_for(git, branch=DEFAULT_BRANCH, created=False, allow_default_branch="yes")
    )

    assert result.park is not None
    assert git.called("push") == []


def test_a_rejected_push_syncs_and_pushes_again() -> None:
    git = FakeGit(push=[REJECTION, "ok"])
    ctx = a_context_for(git, retry=RETRY)

    result = GitPushExecutor().execute(ctx)

    assert result.status == "done"
    assert result.reason == RETRY_LANDED.format(k=1) == "pushed after 1 sync"
    assert [call[0] for call in git.calls] == ["push", "sync", "push"]
    lines = log_lines(ctx)
    assert len([line for line in lines if line.startswith("> push ")]) == 2  # noqa: PLR2004


def test_a_push_that_lands_the_first_time_never_syncs() -> None:
    git = FakeGit(push=["ok"])

    result = GitPushExecutor().execute(a_context_for(git, retry=RETRY))

    assert result.status == "done"
    assert result.reason is None
    assert git.called("sync") == []


def test_two_rejections_park_push_rejected() -> None:
    git = FakeGit(push=[REJECTION, REJECTION])

    result = GitPushExecutor().execute(a_context_for(git, retry=RETRY))

    assert result.status == "error"
    assert result.park is not None
    assert (result.park.kind, result.park.reason) == ("push_rejected", REJECTED)
    assert result.output_ref == REJECTION.output
    assert len(git.called("push")) == 2  # noqa: PLR2004


def test_the_bound_is_max_syncs() -> None:
    git = FakeGit(push=[REJECTION, REJECTION, "ok"])

    result = GitPushExecutor().execute(a_context_for(git, retry={"max": 2, "sync_first": True}))

    assert result.reason == RETRY_LANDED.format(k=2)
    assert len(git.called("sync")) == 2  # noqa: PLR2004


def test_a_failing_sync_parks_with_its_own_output() -> None:
    git = FakeGit(push=[REJECTION], sync=[SYNC_FAILURE])

    result = GitPushExecutor().execute(a_context_for(git, retry=RETRY))

    assert result.status == "error"
    assert result.park is not None
    assert (result.park.kind, result.park.reason) == ("push_rejected", SYNC_FAILED)
    assert result.output_ref == SYNC_FAILURE.output
    assert len(git.called("push")) == 1


def test_without_a_declared_retry_a_rejection_parks_at_once() -> None:
    git = FakeGit(push=[REJECTION])

    result = GitPushExecutor().execute(a_context_for(git))

    assert result.park is not None
    assert result.park.reason == REJECTED
    assert git.called("sync") == []
