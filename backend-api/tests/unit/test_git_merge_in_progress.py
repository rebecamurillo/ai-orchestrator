"""`SubprocessGit.merge_in_progress`, against real `git` (story 8.4, 2026-11-25).

The merge executor is proven over `FakeGit`; what only a real process settles is that
`MERGE_HEAD` resolves in a *linked* worktree, which is where every tree this system merges in
lives.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.infrastructure.git.subprocess_git import SubprocessGit

TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
SHARED = "shared.txt"


def run_git(*arguments: str, cwd: Path, check: bool = True) -> None:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "e2e",
        "GIT_AUTHOR_EMAIL": "e2e@example.invalid",
        "GIT_COMMITTER_NAME": "e2e",
        "GIT_COMMITTER_EMAIL": "e2e@example.invalid",
    }
    subprocess.run(  # fixed argv, no shell
        ["git", *arguments], cwd=cwd, env=environment, capture_output=True, check=check
    )


def commit(tree: Path, text: str) -> None:
    (tree / SHARED).write_text(text)
    run_git("add", "--all", cwd=tree)
    run_git("commit", "--quiet", "--message", text, cwd=tree)


@pytest.fixture(autouse=True)
def git_binary() -> str:
    found = shutil.which("git")
    if found is None:
        pytest.fail("git is not on PATH: this module drives the real adapter, so install it.")
    return found


@pytest.fixture
def linked(tmp_path: Path) -> Path:
    """A linked worktree on `main` whose merge of `other` conflicts on `SHARED`."""
    base = tmp_path / "base"
    base.mkdir()
    run_git("init", "--quiet", "--initial-branch=main", ".", cwd=base)
    commit(base, "base\n")
    run_git("branch", "other", cwd=base)
    commit(base, "main side\n")
    run_git("checkout", "--quiet", "other", cwd=base)
    commit(base, "other side\n")
    run_git("checkout", "--quiet", "main", cwd=base)
    tree = tmp_path / "wt"
    run_git("worktree", "add", "--quiet", "--detach", str(tree), "main", cwd=base)
    return tree


def test_a_tree_with_no_merge_stopped_is_not_in_progress(linked: Path) -> None:
    assert SubprocessGit(TOKEN).merge_in_progress(linked) is False


def test_a_conflicted_merge_in_a_linked_worktree_is_in_progress(linked: Path) -> None:
    run_git("merge", "--no-ff", "other", cwd=linked, check=False)

    assert SubprocessGit(TOKEN).merge_in_progress(linked) is True


def test_a_merge_aborted_is_no_longer_in_progress(linked: Path) -> None:
    run_git("merge", "--no-ff", "other", cwd=linked, check=False)
    run_git("merge", "--abort", cwd=linked)

    assert SubprocessGit(TOKEN).merge_in_progress(linked) is False
