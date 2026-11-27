"""`FakeRemoteGit.create_remote_branch` (epic 7 story 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.remote_branches import RemoteBranches
from tests.unit.fakes.remote_branches import FakeRemoteGit

WORKTREE = Path("/work/p/hub/base")
SHA = "a" * 40


def test_a_create_is_recorded_and_the_branch_is_held() -> None:
    git = FakeRemoteGit()

    git.create_remote_branch(WORKTREE, "spec/x", SHA)

    assert git.calls[-1] == ("create_remote_branch", (WORKTREE, "spec/x", SHA))
    assert "spec/x" in git.remote_branches
    assert isinstance(git, RemoteBranches)


def test_a_later_ls_remote_sees_the_branch_when_refs_are_mapped() -> None:
    git = FakeRemoteGit(refs={"main": SHA})

    git.create_remote_branch(WORKTREE, "spec/x", SHA)

    found = git.ls_remote("https://example/hub.git", "spec/x")
    assert found is not None
    assert found.sha == SHA
    assert git.refs == {"main": SHA, "spec/x": SHA}


def test_an_existing_branch_raises_a_git_error_naming_it() -> None:
    git = FakeRemoteGit(remote_branches=["spec/x"])

    with pytest.raises(GitError) as refusal:
        git.create_remote_branch(WORKTREE, "spec/x", SHA)

    assert "spec/x" in refusal.value.output


def test_a_scripted_exception_is_raised_and_nothing_is_created() -> None:
    git = FakeRemoteGit(create_remote_branch=[GitError(command="push", exit_code=1, output="no")])

    with pytest.raises(GitError):
        git.create_remote_branch(WORKTREE, "spec/x", SHA)

    assert "spec/x" not in git.remote_branches
    assert git.calls[-1][0] == "create_remote_branch"


def test_a_scripted_non_exception_answer_creates_normally() -> None:
    git = FakeRemoteGit(create_remote_branch=[None])

    git.create_remote_branch(WORKTREE, "spec/x", SHA)

    assert "spec/x" in git.remote_branches
