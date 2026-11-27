"""`SubprocessGit.delete_remote_branch` against a real bare repository (epic 3 story 4, AC8)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.infrastructure.git import remote_branches
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from tests.unit.test_subprocess_git_worktrees import BRANCH, TOKEN, origin, run_git  # noqa: F401

SPEC = "spec/demo"


@pytest.fixture
def clone(origin: Path, tmp_path: Path) -> Path:  # noqa: F811
    run_git("branch", SPEC, BRANCH, cwd=origin)
    path = tmp_path / "clone"
    run_git("clone", "--quiet", f"file://{origin}", str(path), cwd=tmp_path)
    return path


def heads(bare: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(bare), "branch", "--list"], capture_output=True, text=True, check=True
    ).stdout


def test_the_adapter_satisfies_the_port() -> None:
    assert isinstance(SubprocessGit(TOKEN), RemoteBranches)
    assert remote_branches.RemoteBranchesMixin is not None


def test_a_held_branch_is_deleted_then_reported_gone(clone: Path, origin: Path) -> None:  # noqa: F811
    git = SubprocessGit(TOKEN)
    assert SPEC in heads(origin)

    assert git.delete_remote_branch(clone, SPEC) is True
    assert SPEC not in heads(origin)
    assert git.delete_remote_branch(clone, SPEC) is False


def test_any_other_failure_stays_a_git_error(clone: Path, tmp_path: Path) -> None:
    run_git("remote", "set-url", "origin", str(tmp_path / "missing.git"), cwd=clone)

    with pytest.raises(GitError):
        SubprocessGit(TOKEN).delete_remote_branch(clone, SPEC)
