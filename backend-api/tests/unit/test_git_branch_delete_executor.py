"""`git.branch_delete`: delete the merged branch on origin and log it (epic 3 story 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.steps import git_branch_delete
from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.git_branch_delete import KIND, GitBranchDeleteExecutor
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.remote_branches import RemoteBranches
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.remote_branches import FakeRemoteGit
from tests.unit.step_fixtures import WORKTREE, a_context, a_row, an_environment

SPEC = "spec/demo"
OPERATION = f"git push origin --delete {SPEC}"


def a_delete_context(git: FakeGit, branch: str = SPEC, **extra: object) -> StepContext:
    row = a_row(kind=KIND, with_resolved={"branch": branch, **extra}, path="delete")
    return a_context(row, git=git, env=an_environment())


def lines_of(ctx: StepContext) -> tuple[str, ...]:
    return ctx.ports.step_log.writes[0][3]  # type: ignore[union-attr]


def test_the_fake_satisfies_the_port() -> None:
    assert isinstance(FakeRemoteGit(), RemoteBranches)
    assert git_branch_delete.KIND == KIND


def test_a_held_branch_is_deleted_and_logged() -> None:
    git = FakeRemoteGit(remote_branches=[SPEC])
    ctx = a_delete_context(git)

    result = GitBranchDeleteExecutor().execute(ctx)

    assert result.status == "done"
    assert result.reason == f"deleted origin/{SPEC}"
    assert SPEC not in git.remote_branches
    assert result.log_path == str(log_path(ctx))
    lines = lines_of(ctx)
    assert lines[0] == OPERATION
    assert "deleted" in lines[1]


def test_a_missing_branch_is_already_gone() -> None:
    ctx = a_delete_context(FakeRemoteGit())

    result = GitBranchDeleteExecutor().execute(ctx)

    assert result.status == "done"
    assert result.reason == "already gone"
    assert lines_of(ctx) == (OPERATION, "  already gone")


def test_the_default_branch_is_refused_before_any_call() -> None:
    git = FakeRemoteGit(remote_branches=["main"])
    ctx = a_delete_context(git, branch="main")

    result = GitBranchDeleteExecutor().execute(ctx)

    assert result.status == "error"
    assert result.park is not None and result.park.kind == "misconfigured"
    assert result.reason == "refuses to delete the default branch main"
    assert git.called("delete_remote_branch") == []
    assert ctx.ports.step_log.writes == []  # type: ignore[union-attr]


@pytest.mark.parametrize("spelling", ["heads/main", "refs/heads/main"])
def test_a_qualified_default_branch_is_refused(spelling: str) -> None:
    git = FakeRemoteGit(remote_branches=["main"])

    result = GitBranchDeleteExecutor().execute(a_delete_context(git, branch=spelling))

    assert result.park is not None and result.park.kind == "misconfigured"
    assert result.reason == f"refuses to delete the default branch {spelling}"
    assert git.called("delete_remote_branch") == []


def test_a_branch_merely_ending_in_the_default_name_is_not_refused() -> None:
    git = FakeRemoteGit(remote_branches=["spec/main"])

    result = GitBranchDeleteExecutor().execute(a_delete_context(git, branch="spec/main"))

    assert result.status == "done"


def test_a_blank_branch_is_refused() -> None:
    git = FakeRemoteGit()
    result = GitBranchDeleteExecutor().execute(a_delete_context(git, branch=""))

    assert result.status == "error"
    assert result.park is not None and result.park.kind == "misconfigured"
    assert result.reason == "branch_delete needs a branch and a known default branch"
    assert git.called("delete_remote_branch") == []


def test_a_blank_default_branch_is_refused() -> None:
    row = a_row(kind=KIND, with_resolved={"branch": SPEC}, path="delete")
    ctx = a_context(row, git=FakeRemoteGit(), env=an_environment(default_branch=""))

    result = GitBranchDeleteExecutor().execute(ctx)

    assert result.reason == "branch_delete needs a branch and a known default branch"


def test_a_rejected_delete_parks_with_gits_output_and_logs_it() -> None:
    rejected = GitError(command="git push", exit_code=1, output="! [remote rejected] spec/demo")
    ctx = a_delete_context(FakeRemoteGit(remote_branches=[SPEC], delete_remote_branch=[rejected]))

    result = GitBranchDeleteExecutor().execute(ctx)

    assert result.status == "error"
    assert result.park is not None and result.park.kind == "push_rejected"
    assert result.reason == "branch delete rejected"
    assert result.output_ref == "! [remote rejected] spec/demo"
    assert lines_of(ctx) == (OPERATION, "  ! [remote rejected] spec/demo")


def test_a_git_adapter_without_the_port_parks_misconfigured() -> None:
    result = GitBranchDeleteExecutor().execute(a_delete_context(FakeGit()))

    assert result.status == "error"
    assert result.park is not None and result.park.kind == "misconfigured"
    assert result.reason == "git adapter cannot delete a remote branch"


def test_a_workdir_joins_the_working_directory() -> None:
    git = FakeRemoteGit(remote_branches=[SPEC])

    GitBranchDeleteExecutor().execute(a_delete_context(git, workdir="sub"))

    assert git.called("delete_remote_branch") == [(Path(WORKTREE) / "sub", SPEC)]
