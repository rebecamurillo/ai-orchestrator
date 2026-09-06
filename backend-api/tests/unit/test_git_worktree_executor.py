"""`application/steps/git_worktree.py`: the worktree, and the install that follows it.

Every branch AD-14 gives the kind, over the shared `Git`, `Workspace` and `ProcessRunner`
fakes: the base clone ensured, the three ways a worktree can be opened, the two `RunUpdates`
it produces, and the Repository's own `install_command`. What a real `git worktree add` does
is `tests/unit/test_subprocess_git_worktrees.py`'s.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps.context import NO_ENVIRONMENT, NO_WORKSPACE, StepExecutor
from orchestrator.application.steps.git_worktree import (
    DIRTY,
    INSTALL_FAILED,
    INSTALL_TIMED_OUT,
    KIND,
    NO_INSTALL,
    REUSED,
    GitWorktreeExecutor,
)
from orchestrator.application.steps.registry import executor_for
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.process import Outcome
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.workspace import FakeWorkspace
from tests.unit.step_fixtures import (
    BASE_DIR,
    BRANCH,
    DEFAULT_BRANCH,
    REPOSITORY_URL,
    WORKTREE,
    a_context,
    a_row,
    a_worktree,
    an_environment,
    without,
)

RESOLVED = {"base": DEFAULT_BRANCH, "branch": BRANCH, "timeout_min": 5}
INSTALL = "uv sync"

#: A `FakeWorkspace` whose root answers `exists(".")` — what "the worktree is already there"
#: looks like to the executor.
PRESENT = {".": ""}


def a_worktree_row() -> StepRun:
    return a_row(kind=KIND, with_resolved=dict(RESOLVED))


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(GitWorktreeExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), GitWorktreeExecutor)


# ── the base clone ──────────────────────────────────────────────────────────


def test_a_repository_with_no_base_clone_is_cloned_from_its_url() -> None:
    git = FakeGit(base_exists=[False], branch_exists=[False])

    GitWorktreeExecutor().execute(a_context(a_worktree_row(), git=git))

    assert git.called("clone_base") == [(REPOSITORY_URL, git.called("clone_base")[0][1])]
    assert str(git.called("clone_base")[0][1]) == BASE_DIR
    assert git.called("fetch_base") == []


def test_a_base_clone_that_is_already_there_is_fetched_rather_than_cloned() -> None:
    git = FakeGit(base_exists=[True], branch_exists=[False])

    GitWorktreeExecutor().execute(a_context(a_worktree_row(), git=git))

    assert git.called("fetch_base") == [(git.called("fetch_base")[0][0], DEFAULT_BRANCH)]
    assert git.called("clone_base") == []


# ── opening the worktree ────────────────────────────────────────────────────


def test_a_branch_the_origin_does_not_hold_is_created_from_the_base() -> None:
    git = FakeGit(base_exists=[True], branch_exists=[False])

    result = GitWorktreeExecutor().execute(a_context(a_worktree_row(), git=git))

    [(base, path, branch, start)] = git.called("worktree_add")
    assert (str(base), str(path), branch, start) == (
        BASE_DIR,
        WORKTREE,
        BRANCH,
        f"origin/{DEFAULT_BRANCH}",
    )
    assert result.run_updates is not None
    assert result.run_updates.worktrees is not None
    assert result.run_updates.worktrees[0].created_branch is True


def test_a_branch_the_origin_holds_is_checked_out_and_tracks_it() -> None:
    git = FakeGit(base_exists=[True], branch_exists=[True])

    result = GitWorktreeExecutor().execute(a_context(a_worktree_row(), git=git))

    [(_, _, branch, start)] = git.called("worktree_add")
    assert (branch, start) == (BRANCH, None)
    assert result.run_updates is not None
    assert result.run_updates.worktrees is not None
    assert result.run_updates.worktrees[0].created_branch is False


def test_the_run_updates_name_the_worktree_the_run_now_works_in() -> None:
    result = GitWorktreeExecutor().execute(a_context(a_worktree_row()))

    assert result.status == "done"
    assert result.run_updates is not None
    assert result.run_updates.worktree_path == WORKTREE
    entry = result.run_updates.worktrees[0]  # type: ignore[index]
    assert (entry.branch, entry.path, entry.pushed) == (BRANCH, WORKTREE, False)


def test_a_clean_worktree_that_is_already_there_is_reused() -> None:
    git = FakeGit(base_exists=[True], status=[""])
    context = a_context(
        a_worktree_row(),
        git=git,
        workspace=FakeWorkspace(files=dict(PRESENT)),
        env=an_environment(worktrees=(a_worktree(),)),
    )

    result = GitWorktreeExecutor().execute(context)

    assert result.status == "done"
    assert result.reason == REUSED
    assert git.called("worktree_add") == []


def test_a_reused_worktree_keeps_the_created_branch_the_run_already_recorded() -> None:
    """`git.push` reads `-u` off this flag; a reuse must not forget the branch was made here."""
    context = a_context(
        a_worktree_row(),
        git=FakeGit(base_exists=[True], status=[""]),
        workspace=FakeWorkspace(files=dict(PRESENT)),
        env=an_environment(worktrees=(a_worktree(created_branch=True),)),
    )

    result = GitWorktreeExecutor().execute(context)

    assert result.run_updates is not None
    assert result.run_updates.worktrees == (a_worktree(created_branch=True),)


def test_a_worktree_no_entry_records_is_reused_without_claiming_the_branch() -> None:
    context = a_context(
        a_worktree_row(),
        git=FakeGit(base_exists=[True], status=[""]),
        workspace=FakeWorkspace(files=dict(PRESENT)),
    )

    result = GitWorktreeExecutor().execute(context)

    assert result.run_updates is not None
    assert result.run_updates.worktrees[0].created_branch is False  # type: ignore[index]


def test_a_dirty_worktree_parks_misconfigured_naming_the_path() -> None:
    context = a_context(
        a_worktree_row(),
        git=FakeGit(base_exists=[True], status=[" M src/thing.py\n"]),
        workspace=FakeWorkspace(files=dict(PRESENT)),
    )

    result = GitWorktreeExecutor().execute(context)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == DIRTY.format(path=WORKTREE)
    assert result.run_updates is None


# ── the install ─────────────────────────────────────────────────────────────


def test_a_repository_that_declares_no_install_command_runs_nothing_and_says_so() -> None:
    runner = FakeProcessRunner()

    result = GitWorktreeExecutor().execute(a_context(a_worktree_row(), process=runner))

    assert result.reason == NO_INSTALL
    assert runner.called("start") == []


def test_a_whitespace_only_install_command_is_no_command_at_all() -> None:
    runner = FakeProcessRunner()
    context = a_context(a_worktree_row(), process=runner, env=an_environment(install_command="   "))

    assert GitWorktreeExecutor().execute(context).reason == NO_INSTALL
    assert runner.called("start") == []


def test_the_install_command_runs_in_the_new_worktree_under_the_rows_timeout() -> None:
    runner = FakeProcessRunner()
    context = a_context(
        a_worktree_row(), process=runner, env=an_environment(install_command=INSTALL)
    )

    result = GitWorktreeExecutor().execute(context)

    [call] = runner.called("start")
    assert call["cmd"] == INSTALL
    assert str(call["cwd"]) == WORKTREE
    assert call["timeout_min"] == RESOLVED["timeout_min"]
    assert call["env"] == {}
    assert result.status == "done"
    assert result.output_ref == str(call["log_path"])


def test_a_failing_install_parks_misconfigured_with_the_exit_code_and_the_log() -> None:
    runner = FakeProcessRunner(outcomes={"false": Outcome(exit_code=1, timed_out=False)})
    context = a_context(
        a_worktree_row(), process=runner, env=an_environment(install_command="false")
    )

    result = GitWorktreeExecutor().execute(context)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == INSTALL_FAILED.format(code=1)
    assert result.output_ref is not None


def test_a_failed_install_still_records_the_worktree_it_made() -> None:
    """`cancel` removes a worktree by reading `run.worktrees[]` (AD-13)."""
    runner = FakeProcessRunner(outcomes={"false": Outcome(exit_code=1, timed_out=False)})
    context = a_context(
        a_worktree_row(), process=runner, env=an_environment(install_command="false")
    )

    result = GitWorktreeExecutor().execute(context)

    assert result.run_updates is not None
    assert result.run_updates.worktree_path == WORKTREE


def test_an_install_the_runner_killed_parks_timeout_rather_than_misconfigured() -> None:
    runner = FakeProcessRunner(outcomes={INSTALL: Outcome(exit_code=None, timed_out=True)})
    context = a_context(
        a_worktree_row(), process=runner, env=an_environment(install_command=INSTALL)
    )

    result = GitWorktreeExecutor().execute(context)

    assert result.park is not None
    assert result.park.kind == "timeout"
    assert result.park.reason == INSTALL_TIMED_OUT.format(path="checkout", n=5)


def test_an_install_row_with_no_resolved_timeout_falls_back_to_the_kinds_own() -> None:
    runner = FakeProcessRunner()
    row = a_row(kind=KIND, with_resolved={"base": DEFAULT_BRANCH, "branch": BRANCH})
    context = a_context(row, process=runner, env=an_environment(install_command=INSTALL))

    GitWorktreeExecutor().execute(context)

    assert runner.called("start")[0]["timeout_min"] == 5  # noqa: PLR2004 — the kind's default


# ── the wiring the composition root owes it ─────────────────────────────────


def test_without_an_environment_the_executor_refuses_rather_than_guesses() -> None:
    """A wiring bug raises; `registry.execute` turns it into an `internal` park (AD-5)."""
    with pytest.raises(RuntimeError, match=NO_ENVIRONMENT):
        GitWorktreeExecutor().execute(without(a_context(a_worktree_row()), run_env=None))


def test_without_a_workspace_factory_the_executor_refuses() -> None:
    with pytest.raises(RuntimeError, match=NO_WORKSPACE):
        GitWorktreeExecutor().execute(without(a_context(a_worktree_row()), workspace=None))
