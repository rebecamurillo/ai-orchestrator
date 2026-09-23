"""`Git.push_branch` against a real `git` (multi-repo initiative S6, AD-14, 2026-09-23).

AD-14's own words: "`push origin {ref}:refs/heads/{branch}`, the one Git write that precedes
every worktree: initiative dispatch (AD-12) calls it to ensure a repository's integration
branch exists, adopting the remote branch at its head when the remote already holds it and
creating it from the base head otherwise, and it touches no worktree".

Three properties only a real process settles: the refspec creates a branch with no local
branch of that name existing; a second call is a no-op rather than a reset; and the command
runs in the base clone, leaving the worktree directory untouched. A separate module from
`test_subprocess_git_worktrees.py` because that one is an anchor — this method was not in
the port when it was written.

The remote is a bare repository under `tmp_path`, addressed by `file://`, so nothing here
needs the network or a credential.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit

TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
BRANCH = "main"
INTEGRATION = "develop-web"
SEED_FILE = "README.md"


@pytest.fixture(autouse=True)
def git_binary() -> str:
    """`git` is a requirement of this suite, not a condition on running it (AD-18)."""
    found = shutil.which("git")
    if found is None:
        pytest.fail("git is not on PATH: this module drives the real adapter, so install it.")
    return found


def run_git(*arguments: str, cwd: Path) -> str:
    """Set up a fixture repository. The adapter is what is under test, not this."""
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "e2e",
        "GIT_AUTHOR_EMAIL": "e2e@example.invalid",
        "GIT_COMMITTER_NAME": "e2e",
        "GIT_COMMITTER_EMAIL": "e2e@example.invalid",
    }
    return subprocess.run(  # fixed argv, no shell
        ["git", *arguments], cwd=cwd, env=environment, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A bare repository with one commit on `main`."""
    bare = tmp_path / "origin.git"
    run_git("init", "--quiet", "--bare", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    seed.mkdir()
    run_git("init", "--quiet", f"--initial-branch={BRANCH}", ".", cwd=seed)
    (seed / SEED_FILE).write_text("seed\n")
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "seed", cwd=seed)
    run_git("push", "--quiet", f"file://{bare}", f"{BRANCH}:{BRANCH}", cwd=seed)
    run_git("symbolic-ref", "HEAD", f"refs/heads/{BRANCH}", cwd=bare)
    return bare


@pytest.fixture
def git() -> SubprocessGit:
    return SubprocessGit(TOKEN)


@pytest.fixture
def base(git: SubprocessGit, origin: Path, tmp_path: Path) -> Path:
    """A base clone of the origin, as every Run of that repository shares one."""
    destination = tmp_path / "work" / "acme" / "widgets" / "base"
    git.clone_base(f"file://{origin}", destination)
    git.fetch_base(destination, BRANCH)
    return destination


def head_of(origin: Path, branch: str) -> str:
    return run_git("rev-parse", branch, cwd=origin).strip()


def test_the_adapter_still_satisfies_the_whole_port() -> None:
    assert isinstance(SubprocessGit(TOKEN), Git)


def test_a_branch_the_origin_does_not_hold_is_created_at_the_ref_given(
    git: SubprocessGit, base: Path, origin: Path
) -> None:
    at = head_of(origin, BRANCH)

    answer = git.push_branch(base, INTEGRATION, at)

    assert answer is not None
    assert head_of(origin, INTEGRATION) == at


def test_no_local_branch_of_that_name_has_to_exist_for_the_refspec_to_work(
    git: SubprocessGit, base: Path, origin: Path
) -> None:
    """The base clone is detached and carries no branches of its own (AD-14)."""
    git.push_branch(base, INTEGRATION, head_of(origin, BRANCH))

    assert INTEGRATION not in run_git("branch", "--list", INTEGRATION, cwd=base)


def test_a_branch_the_origin_already_holds_is_adopted_and_nothing_is_written(
    git: SubprocessGit, base: Path, origin: Path, tmp_path: Path
) -> None:
    """Adopt is a no-op, not a reset: the branch may already carry merged epics."""
    git.push_branch(base, INTEGRATION, head_of(origin, BRANCH))
    theirs = tmp_path / "theirs"
    run_git(
        "clone", "--quiet", f"file://{origin}", "--branch", INTEGRATION, str(theirs), cwd=tmp_path
    )
    (theirs / "theirs.txt").write_text("theirs\n")
    run_git("add", "--all", cwd=theirs)
    run_git("commit", "--quiet", "--message", "an epic merged", cwd=theirs)
    run_git("push", "--quiet", "origin", INTEGRATION, cwd=theirs)
    moved = head_of(origin, INTEGRATION)

    answer = git.push_branch(base, INTEGRATION, head_of(origin, BRANCH))

    assert answer is None
    assert head_of(origin, INTEGRATION) == moved


def test_calling_it_twice_in_a_row_leaves_the_branch_where_the_first_call_put_it(
    git: SubprocessGit, base: Path, origin: Path
) -> None:
    """Idempotent, which is what lets a re-dispatch run the push phase again safely."""
    at = head_of(origin, BRANCH)
    git.push_branch(base, INTEGRATION, at)

    assert git.push_branch(base, INTEGRATION, at) is None
    assert head_of(origin, INTEGRATION) == at


def test_it_touches_no_worktree_at_all(
    git: SubprocessGit, base: Path, origin: Path, tmp_path: Path
) -> None:
    """AD-13's "only worktree writes outside an engine step" still stands with this method."""
    worktree_root = tmp_path / "work" / "acme" / "widgets" / "wt"

    git.push_branch(base, INTEGRATION, head_of(origin, BRANCH))

    assert not worktree_root.exists()
    assert run_git("worktree", "list", "--porcelain", cwd=base).count("worktree ") == 1
