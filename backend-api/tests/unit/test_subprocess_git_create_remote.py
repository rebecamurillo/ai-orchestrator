"""`SubprocessGit.create_remote_branch` against a real bare repository (epic 7 story 3, AC13)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from tests.unit.test_subprocess_git_worktrees import BRANCH, TOKEN, origin, run_git  # noqa: F401

SPEC = "spec/demo"


@pytest.fixture
def clone(origin: Path, tmp_path: Path) -> Path:  # noqa: F811
    path = tmp_path / "clone"
    run_git("clone", "--quiet", f"file://{origin}", str(path), cwd=tmp_path)
    return path


def tip(bare: Path, branch: str) -> str:
    return subprocess.run(
        ["git", "-C", str(bare), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def test_the_adapter_satisfies_the_port() -> None:
    assert isinstance(SubprocessGit(TOKEN), RemoteBranches)


def test_a_branch_is_created_at_the_sha(clone: Path, origin: Path) -> None:  # noqa: F811
    main = tip(origin, BRANCH)

    SubprocessGit(TOKEN).create_remote_branch(clone, SPEC, main)

    assert tip(origin, SPEC) == main


def test_an_existing_branch_is_refused_and_unchanged(clone: Path, origin: Path) -> None:  # noqa: F811
    main = tip(origin, BRANCH)
    git = SubprocessGit(TOKEN)
    git.create_remote_branch(clone, SPEC, main)
    run_git("commit", "--quiet", "--allow-empty", "-m", "next", cwd=clone)
    ahead = run_git("rev-parse", "HEAD", cwd=clone).strip()

    with pytest.raises(GitError):
        git.create_remote_branch(clone, SPEC, main)
    with pytest.raises(GitError):
        git.create_remote_branch(clone, SPEC, ahead)

    assert tip(origin, SPEC) == main
