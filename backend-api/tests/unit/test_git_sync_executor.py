"""`application/steps/git_sync.py`: fetch, fast-forward, and the two things that are not that.

The three outcomes AD-14 and AD-13 give the kind, each asserted as the fact about the branch
it reports: no upstream is a recorded no-op, a fast-forward is `done`, and a divergence is
the `push_rejected` park with git's own words beside it.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps.context import NO_ENVIRONMENT, NO_WORKTREE, StepExecutor
from orchestrator.application.steps.git_sync import (
    DIVERGED,
    KIND,
    NO_UPSTREAM,
    UNKNOWN_WORKTREE,
    GitSyncExecutor,
)
from orchestrator.application.steps.registry import executor_for
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import (
    BRANCH,
    WORKTREE,
    a_context,
    a_row,
    a_worktree,
    an_environment,
    without,
)

REJECTION = "! [rejected] main -> main (non-fast-forward)"
FETCHED = "Fast-forward\n"


def a_sync_row() -> StepRun:
    return a_row(kind=KIND, with_resolved={"timeout_min": 5}, path="stories[0].sync")


def an_env() -> object:
    return an_environment(worktrees=(a_worktree(),))


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(GitSyncExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), GitSyncExecutor)


def test_a_branch_with_no_upstream_is_a_recorded_no_op() -> None:
    """A branch this Run created and never pushed: AD-14 calls this `done`, not a failure."""
    git = FakeGit(sync=[None])

    result = GitSyncExecutor().execute(a_context(a_sync_row(), git=git, env=an_env()))

    assert result.status == "done"
    assert result.reason == NO_UPSTREAM
    assert result.park is None


def test_a_fast_forward_is_done_with_gits_own_output() -> None:
    git = FakeGit(sync=[FETCHED])

    result = GitSyncExecutor().execute(a_context(a_sync_row(), git=git, env=an_env()))

    assert result.status == "done"
    assert result.output_ref == FETCHED
    assert git.called("sync") == [(git.called("sync")[0][0], BRANCH)]
    assert str(git.called("sync")[0][0]) == WORKTREE


def test_a_diverged_branch_parks_push_rejected_with_the_output_beside_it() -> None:
    git = FakeGit(sync=[GitError(command="git pull", exit_code=1, output=REJECTION)])

    result = GitSyncExecutor().execute(a_context(a_sync_row(), git=git, env=an_env()))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "push_rejected"
    assert result.park.reason == DIVERGED
    assert result.output_ref == REJECTION


def test_a_row_reached_before_any_worktree_exists_refuses() -> None:
    context = a_context(a_sync_row(), env=an_env(), cwd=None)

    with pytest.raises(RuntimeError, match="no worktree"):
        GitSyncExecutor().execute(context)
    assert NO_WORKTREE.format(path="stories[0].sync").startswith("no worktree")


def test_a_worktree_the_run_never_recorded_refuses_rather_than_syncing_a_guess() -> None:
    context = a_context(a_sync_row(), env=an_environment(worktrees=()))

    with pytest.raises(RuntimeError, match=UNKNOWN_WORKTREE.format(path=WORKTREE)):
        GitSyncExecutor().execute(context)


def test_without_an_environment_the_executor_refuses() -> None:
    with pytest.raises(RuntimeError, match=NO_ENVIRONMENT):
        GitSyncExecutor().execute(without(a_context(a_sync_row()), run_env=None))
