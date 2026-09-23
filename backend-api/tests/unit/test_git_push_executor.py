"""`application/steps/git_push.py`: the branch onto the origin, and the three refusals.

The default-branch refusal is asserted as "no push command ran", because that is what the
rule actually says — it is decided from the Repository, before anything is sent. The retry
path is asserted as an *order*: AD-13 says a `retry` on a `push_rejected` row syncs first,
and only a call log can settle "first".

A `with {workdir}` row (H2, 2026-09-23, spine AD-14 amendment) is asserted separately, below:
the default-branch refusal compares against `Git.submodule_default_branch`, the push targets
the submodule, and `run.worktrees[]` is left untouched.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps.context import NO_ENVIRONMENT, StepExecutor
from orchestrator.application.steps.git_push import (
    DEFAULT_BRANCH as REFUSED_DEFAULT,
)
from orchestrator.application.steps.git_push import (
    KIND,
    NOT_A_SUBMODULE,
    REJECTED,
    GitPushExecutor,
)
from orchestrator.application.steps.git_sync import DIVERGED
from orchestrator.application.steps.registry import executor_for
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import DEFAULT_MEMBER_BRANCH, FakeGit
from tests.unit.step_fixtures import (
    BRANCH,
    DEFAULT_BRANCH,
    WORKTREE,
    a_context,
    a_row,
    a_worktree,
    an_environment,
    without,
)

REJECTION = "! [rejected] chore/bmad-init -> chore/bmad-init (fetch first)"
PUSHED_OUTPUT = "To origin\n * [new branch] chore/bmad-init"
WORKDIR = "repos/member"


def a_push_row(branch: str = BRANCH) -> StepRun:
    return a_row(kind=KIND, with_resolved={"branch": branch}, path="push")


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(GitPushExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), GitPushExecutor)


def test_the_default_branch_is_refused_and_no_push_command_runs() -> None:
    git = FakeGit()
    env = an_environment(worktrees=(a_worktree(branch=DEFAULT_BRANCH),))

    result = GitPushExecutor().execute(a_context(a_push_row(DEFAULT_BRANCH), git=git, env=env))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "push_rejected"
    assert result.park.reason == REFUSED_DEFAULT.format(branch=DEFAULT_BRANCH)
    assert git.called("push") == []


def test_a_branch_this_run_created_is_pushed_with_its_upstream_set() -> None:
    git = FakeGit(push=[PUSHED_OUTPUT])
    env = an_environment(worktrees=(a_worktree(created_branch=True),))

    result = GitPushExecutor().execute(a_context(a_push_row(), git=git, env=env))

    [(worktree, branch, upstream)] = git.called("push")
    assert (str(worktree), branch, upstream) == (WORKTREE, BRANCH, True)
    assert result.status == "done"
    assert result.output_ref == PUSHED_OUTPUT


def test_a_branch_that_already_existed_is_pushed_without_setting_an_upstream() -> None:
    git = FakeGit()
    env = an_environment(worktrees=(a_worktree(created_branch=False),))

    GitPushExecutor().execute(a_context(a_push_row(), git=git, env=env))

    assert git.called("push")[0][2] is False


def test_a_worktree_the_run_never_recorded_is_pushed_without_an_upstream() -> None:
    git = FakeGit()

    GitPushExecutor().execute(a_context(a_push_row(), git=git, env=an_environment()))

    assert git.called("push")[0][2] is False


def test_a_successful_push_marks_its_own_entry_pushed_and_leaves_the_others() -> None:
    other = a_worktree(branch="feat/other", path="/work/acme/widgets/wt/feat/other")
    env = an_environment(worktrees=(other, a_worktree()))

    result = GitPushExecutor().execute(a_context(a_push_row(), env=env))

    assert result.run_updates is not None
    assert result.run_updates.worktrees == (other, a_worktree(pushed=True))


def test_a_rejected_push_parks_push_rejected_with_the_remotes_own_words() -> None:
    git = FakeGit(push=[GitError(command="git push", exit_code=1, output=REJECTION)])
    env = an_environment(worktrees=(a_worktree(),))

    result = GitPushExecutor().execute(a_context(a_push_row(), git=git, env=env))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "push_rejected"
    assert result.park.reason == REJECTED
    assert result.output_ref == REJECTION
    assert result.run_updates is None


# ── the retry (AD-13) ───────────────────────────────────────────────────────


def test_a_retry_syncs_before_it_pushes() -> None:
    git = FakeGit()
    env = an_environment(worktrees=(a_worktree(),))

    GitPushExecutor().execute(a_context(a_push_row(), git=git, env=env, resume="retry"))

    assert [name for name, _ in git.calls] == ["sync", "push"]


def test_a_row_resumed_by_any_other_signal_does_not_sync() -> None:
    git = FakeGit()
    env = an_environment(worktrees=(a_worktree(),))

    GitPushExecutor().execute(a_context(a_push_row(), git=git, env=env, resume="continue"))

    assert [name for name, _ in git.calls] == ["push"]


def test_a_first_attempt_does_not_sync() -> None:
    git = FakeGit()

    GitPushExecutor().execute(a_context(a_push_row(), git=git))

    assert [name for name, _ in git.calls] == ["push"]


def test_a_retry_whose_sync_cannot_fast_forward_parks_on_the_syncs_own_sentence() -> None:
    git = FakeGit(sync=[GitError(command="git pull", exit_code=1, output=REJECTION)])
    env = an_environment(worktrees=(a_worktree(),))

    result = GitPushExecutor().execute(a_context(a_push_row(), git=git, env=env, resume="retry"))

    assert result.park is not None
    assert result.park.kind == "push_rejected"
    assert result.park.reason == DIVERGED
    assert git.called("push") == []


def test_without_an_environment_the_executor_refuses() -> None:
    with pytest.raises(RuntimeError, match=NO_ENVIRONMENT):
        GitPushExecutor().execute(without(a_context(a_push_row()), run_env=None))


# ── `with {workdir}` (H2, spine AD-14 amendment, 2026-09-23) ────────────────


def a_workdir_push_row(branch: str = BRANCH) -> StepRun:
    return a_row(kind=KIND, with_resolved={"branch": branch, "workdir": WORKDIR}, path="push")


def test_a_workdir_row_pushes_the_submodule_to_its_own_origin() -> None:
    git = FakeGit(push=[PUSHED_OUTPUT], submodule_default_branch=[DEFAULT_MEMBER_BRANCH])

    result = GitPushExecutor().execute(a_context(a_workdir_push_row(), git=git))

    assert result.status == "done"
    assert result.output_ref == PUSHED_OUTPUT
    [(worktree, branch, upstream, workdir)] = git.called("push")
    assert (str(worktree), branch, upstream, workdir) == (WORKTREE, BRANCH, True, WORKDIR)


def test_a_workdir_rows_default_branch_refusal_reads_the_submodules_own_branch() -> None:
    """AD-14: "reads the SUBMODULE's default branch, not the Run Repository's" — the row's
    `branch` matches the fake's scripted member default, not `step_fixtures.DEFAULT_BRANCH`."""
    git = FakeGit(submodule_default_branch=[DEFAULT_MEMBER_BRANCH])
    env = an_environment(default_branch=DEFAULT_BRANCH)

    result = GitPushExecutor().execute(
        a_context(a_workdir_push_row(DEFAULT_MEMBER_BRANCH), git=git, env=env)
    )

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "push_rejected"
    assert result.park.reason == REFUSED_DEFAULT.format(branch=DEFAULT_MEMBER_BRANCH)
    assert git.called("push") == []


def test_a_workdir_row_is_not_refused_for_the_hubs_own_default_branch() -> None:
    """The Run Repository's default branch (`step_fixtures.DEFAULT_BRANCH`, "main") is not
    the submodule's — a workdir row pushing a branch of that name is not the default-branch
    case at all."""
    git = FakeGit(push=[PUSHED_OUTPUT], submodule_default_branch=[DEFAULT_MEMBER_BRANCH])

    result = GitPushExecutor().execute(
        a_context(a_workdir_push_row(DEFAULT_BRANCH), git=git, env=an_environment())
    )

    assert result.status == "done"
    assert git.called("push") != []


def test_a_workdir_that_is_not_an_initialized_submodule_parks_the_spines_sentence() -> None:
    git = FakeGit(push=[None], submodule_default_branch=[None])

    result = GitPushExecutor().execute(a_context(a_workdir_push_row(), git=git))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == f"workdir {WORKDIR} is not an initialized submodule"
    assert result.reason == NOT_A_SUBMODULE.format(path=WORKDIR)


def test_a_workdir_push_a_git_error_rejects_parks_push_rejected() -> None:
    git = FakeGit(
        push=[GitError(command="git push", exit_code=1, output=REJECTION)],
        submodule_default_branch=[DEFAULT_MEMBER_BRANCH],
    )

    result = GitPushExecutor().execute(a_context(a_workdir_push_row(), git=git))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "push_rejected"
    assert result.park.reason == REJECTED
    assert result.output_ref == REJECTION


def test_a_workdir_push_sets_no_pushed_flag_on_any_worktree() -> None:
    """AD-14: "`run.worktrees[]` tracks the Run's own worktrees only, so a `workdir` push
    sets no `pushed` flag" — unlike the hub-root push, this row's `run_updates` is `None`."""
    git = FakeGit(push=[PUSHED_OUTPUT], submodule_default_branch=[DEFAULT_MEMBER_BRANCH])
    env = an_environment(worktrees=(a_worktree(),))

    result = GitPushExecutor().execute(a_context(a_workdir_push_row(), git=git, env=env))

    assert result.status == "done"
    assert result.run_updates is None
