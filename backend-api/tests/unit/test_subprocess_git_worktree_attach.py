"""`worktree_add` with no start point checks the branch out at the origin's head, even the
default branch the clone made locally, which a fetch never moves. Release review 2026-11-26: an
initiative's merge Run attached a stale `main`, merged into it, and its push was refused."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from tests.unit.test_subprocess_git_worktrees import BRANCH, SEED_FILE, TOKEN, run_git


@pytest.fixture
def git() -> SubprocessGit:
    return SubprocessGit(TOKEN)


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A bare repository with one commit on `main`."""
    bare = tmp_path / "origin.git"
    run_git("init", "--quiet", "--bare", f"--initial-branch={BRANCH}", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    seed.mkdir()
    run_git("init", "--quiet", f"--initial-branch={BRANCH}", ".", cwd=seed)
    (seed / SEED_FILE).write_text("seed\n")
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "seed", cwd=seed)
    run_git("push", "--quiet", f"file://{bare}", f"{BRANCH}:{BRANCH}", cwd=seed)
    return bare


@pytest.fixture
def base(git: SubprocessGit, origin: Path, tmp_path: Path) -> Path:
    """A base clone of the origin, as `git.worktree` makes one."""
    destination = tmp_path / "base"
    git.clone_base(f"file://{origin}", destination)
    git.fetch_base(destination, BRANCH)
    return destination


def advance_origin(origin: Path, tmp_path: Path, text: str) -> str:
    """One more commit on the origin's `main`, made from someone else's clone; its sha."""
    other = tmp_path / "other"
    run_git("clone", "--quiet", f"file://{origin}", str(other), cwd=tmp_path)
    (other / SEED_FILE).write_text(text)
    run_git("commit", "--quiet", "--all", "--message", "moved", cwd=other)
    run_git("push", "--quiet", "origin", BRANCH, cwd=other)
    return run_git("rev-parse", "HEAD", cwd=other).strip()


def test_the_default_branch_is_attached_at_the_origins_head_after_it_moved(
    git: SubprocessGit, origin: Path, base: Path, tmp_path: Path
) -> None:
    moved = advance_origin(origin, tmp_path, "moved\n")
    git.fetch_base(base, BRANCH)
    path = tmp_path / "wt-main"

    git.worktree_add(base, path, BRANCH, None)

    assert git.head_sha(path) == moved
    assert (path / SEED_FILE).read_text() == "moved\n"


def test_a_local_branch_ahead_of_its_origin_keeps_its_own_commits(
    git: SubprocessGit, origin: Path, base: Path, tmp_path: Path
) -> None:
    advance_origin(origin, tmp_path, "moved\n")
    git.fetch_base(base, BRANCH)
    run_git("update-ref", f"refs/heads/{BRANCH}", "HEAD~1", cwd=base)
    first = tmp_path / "wt-first"
    git.worktree_add(base, first, BRANCH, None)
    (first / SEED_FILE).write_text("local\n")
    run_git("commit", "--quiet", "--all", "--message", "local", cwd=first)
    local = run_git("rev-parse", "HEAD", cwd=first).strip()
    run_git("worktree", "remove", str(first), cwd=base)
    second = tmp_path / "wt-second"

    git.worktree_add(base, second, BRANCH, None)

    assert git.head_sha(second) == local
