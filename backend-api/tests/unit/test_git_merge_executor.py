"""`application/steps/git_merge.py`: one epic's branch into the integration branch (AD-13).

The three outcomes the spine's shipped-kinds row gives the kind, each asserted as the fact
about the two branches it reports: a merge that went through is `done` with the commit it
made, a ref the branch already contains is `done · already merged`, and a conflict parks
`merge_conflict` with git's own words beside it.

The fourth rule has no output of its own and is asserted as an absence: AD-13's amended
`retry` row re-runs a `merge_conflict` row **whole**, with no `Git.sync` before it — that
pre-step belongs to `push_rejected` and `verify_failed`, and the abort-any-merge-in-progress
guard inside `Git.merge` is what makes re-running the row safe instead.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps.context import NO_ENVIRONMENT, NO_WORKTREE, StepExecutor
from orchestrator.application.steps.git_merge import (
    ALREADY_MERGED,
    CONFLICT,
    FROM_KEY,
    KIND,
    UNKNOWN_WORKTREE,
    GitMergeExecutor,
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

FROM_BRANCH = "feat/epic-1"
MERGE_SHA = "beef0123456789abcdefbeef0123456789abcdef"
LISTING = "CONFLICT (content): Merge conflict in src/app.py\nsrc/app.py"
PATH = "merge"


def a_merge_row() -> StepRun:
    return a_row(kind=KIND, with_resolved={FROM_KEY: FROM_BRANCH, "timeout_min": 5}, path=PATH)


def an_env() -> object:
    return an_environment(worktrees=(a_worktree(),))


def a_conflict() -> GitError:
    return GitError(command="git merge --no-ff", exit_code=1, output=LISTING)


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(GitMergeExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), GitMergeExecutor)


def test_a_clean_merge_is_done_with_the_commit_it_made() -> None:
    git = FakeGit(merge=[MERGE_SHA])

    result = GitMergeExecutor().execute(a_context(a_merge_row(), git=git, env=an_env()))

    assert result.status == "done"
    assert result.output_ref == MERGE_SHA
    assert result.park is None


def test_the_merge_names_the_declared_source_branch_in_the_runs_own_worktree() -> None:
    git = FakeGit(merge=[MERGE_SHA])

    GitMergeExecutor().execute(a_context(a_merge_row(), git=git, env=an_env()))

    assert [(str(path), branch) for path, branch in git.called("merge")] == [
        (WORKTREE, FROM_BRANCH)
    ]


def test_a_ref_the_branch_already_holds_is_done_and_says_so() -> None:
    """The spine's own words: `already contained → done · already merged`. This is also the
    Operator who resolved the conflict out of band and pushed — the retry finds it landed."""
    git = FakeGit(merge=[None])

    result = GitMergeExecutor().execute(a_context(a_merge_row(), git=git, env=an_env()))

    assert result.status == "done"
    assert result.reason == ALREADY_MERGED
    assert result.park is None


def test_a_conflict_parks_merge_conflict_naming_both_branches() -> None:
    git = FakeGit(merge=[a_conflict()])

    result = GitMergeExecutor().execute(a_context(a_merge_row(), git=git, env=an_env()))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "merge_conflict"
    assert result.park.reason == f"merge conflict: {FROM_BRANCH} into {BRANCH}"
    assert result.park.path == PATH


def test_a_conflict_carries_the_conflicted_files_beside_the_reason() -> None:
    """AD-13 fixes the sentence; the listing is what the Operator opens the worktree with."""
    git = FakeGit(merge=[a_conflict()])

    result = GitMergeExecutor().execute(a_context(a_merge_row(), git=git, env=an_env()))

    assert result.output_ref == LISTING
    assert result.reason == CONFLICT.format(**{FROM_KEY: FROM_BRANCH, "branch": BRANCH})


def test_a_retry_re_runs_the_row_whole_with_no_sync_before_it() -> None:
    """AD-13 (amended 2026-09-23): on `merge_conflict` the row re-runs whole, aborting any
    merge in progress first — the `Git.sync` pre-step is `push_rejected`'s, not this one's."""
    git = FakeGit(merge=[MERGE_SHA])

    result = GitMergeExecutor().execute(
        a_context(a_merge_row(), git=git, env=an_env(), resume="retry")
    )

    assert result.status == "done"
    assert git.called("sync") == []
    assert len(git.called("merge")) == 1


def test_a_row_reached_before_any_worktree_exists_refuses() -> None:
    context = a_context(a_merge_row(), env=an_env(), cwd=None)

    with pytest.raises(RuntimeError, match="no worktree"):
        GitMergeExecutor().execute(context)
    assert NO_WORKTREE.format(path=PATH).startswith("no worktree")


def test_a_worktree_the_run_never_recorded_refuses_rather_than_merging_into_a_guess() -> None:
    """The reason names the branch merged *into*, so a row that cannot name it must not run."""
    context = a_context(a_merge_row(), env=an_environment(worktrees=()))

    with pytest.raises(RuntimeError, match=UNKNOWN_WORKTREE.format(path=WORKTREE)):
        GitMergeExecutor().execute(context)


def test_without_an_environment_the_executor_refuses() -> None:
    with pytest.raises(RuntimeError, match=NO_ENVIRONMENT):
        GitMergeExecutor().execute(without(a_context(a_merge_row()), run_env=None))
