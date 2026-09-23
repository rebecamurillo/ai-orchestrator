"""`infrastructure/git/worktrees.py::merge`, against real `git` (AD-14, amended 2026-09-23).

The executor is proven over `FakeGit`; what only a real process settles is that these
commands exist, take the flags they are given, and answer in the shapes the port promises —
a sha for a merge made, `None` for a ref the branch already holds, a `GitError` naming the
conflicted files, and a merge left in progress that the *next* call aborts instead of
tripping over.

The remote is a bare repository under `tmp_path`, addressed by `file://`, so nothing here
needs the network or a credential; the credential rule itself is
`tests/unit/test_subprocess_git.py`'s, and every command below runs through the same `_run`.

Two facts this module is the only place to establish:

- **The abort is guarded, not attempted-and-ignored.** `git merge --abort` fails outright
  when no merge is in progress, so a clean merge succeeding at all is the proof that the
  adapter asks `rev-parse MERGE_HEAD` first. That probe rather than `.git/MERGE_HEAD`:
  a linked worktree's `.git` is a *file*, and its `MERGE_HEAD` lives in the base clone's
  `worktrees/{name}/` directory, so the filesystem check would be looking in the wrong place
  for every worktree this system makes.
- **A conflicted merge is left in the worktree.** That is what the Operator opens; the park
  is not a rollback. The next `merge` — AD-13's `retry`, which re-runs the row whole — is
  what clears it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import GitError
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit

TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
BASE_BRANCH = "main"
INTEGRATION = "develop"
FROM_BRANCH = "feat/epic-1"
SEED_FILE = "README.md"
SHARED_FILE = "shared.txt"
BROUGHT_FILE = "epic.txt"


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
    """A bare repository holding `main`, an integration branch, and one epic branch."""
    bare = tmp_path / "origin.git"
    run_git("init", "--quiet", "--bare", str(bare), cwd=tmp_path)
    seed = tmp_path / "seed"
    seed.mkdir()
    run_git("init", "--quiet", f"--initial-branch={BASE_BRANCH}", ".", cwd=seed)
    (seed / SEED_FILE).write_text("seed\n")
    (seed / SHARED_FILE).write_text("base\n")
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "seed", cwd=seed)
    run_git("branch", INTEGRATION, cwd=seed)
    run_git("checkout", "--quiet", "-b", FROM_BRANCH, cwd=seed)
    (seed / BROUGHT_FILE).write_text("from the epic\n")
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "epic work", cwd=seed)
    run_git(
        "push",
        "--quiet",
        f"file://{bare}",
        f"{BASE_BRANCH}:{BASE_BRANCH}",
        f"{INTEGRATION}:{INTEGRATION}",
        f"{FROM_BRANCH}:{FROM_BRANCH}",
        cwd=seed,
    )
    run_git("symbolic-ref", "HEAD", f"refs/heads/{BASE_BRANCH}", cwd=bare)
    return bare


@pytest.fixture
def git() -> SubprocessGit:
    return SubprocessGit(TOKEN)


@pytest.fixture
def base(git: SubprocessGit, origin: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "work" / "acme" / "widgets" / "base"
    git.clone_base(f"file://{origin}", destination)
    git.fetch_base(destination, INTEGRATION)
    return destination


@pytest.fixture
def worktree(git: SubprocessGit, base: Path, tmp_path: Path) -> Path:
    """The integration branch, attached by its exact name — a merge Run's own worktree."""
    path = tmp_path / "work" / "acme" / "widgets" / "wt" / INTEGRATION
    git.worktree_add(base, path, INTEGRATION, None)
    return path


def clone_branch(origin: Path, into: Path, tmp_path: Path) -> None:
    """Someone else's clone of the epic branch — how a branch moves behind this Run's back."""
    run_git(
        "clone", "--quiet", f"file://{origin}", "--branch", FROM_BRANCH, str(into), cwd=tmp_path
    )


def conflicting_push(origin: Path, tmp_path: Path) -> None:
    """The epic branch edits the shared file, so a merge cannot resolve it by itself."""
    theirs = tmp_path / "theirs"
    clone_branch(origin, theirs, tmp_path)
    (theirs / SHARED_FILE).write_text("from the epic\n")
    run_git("add", "--all", cwd=theirs)
    run_git("commit", "--quiet", "--message", "epic edits the shared file", cwd=theirs)
    run_git("push", "--quiet", "origin", FROM_BRANCH, cwd=theirs)


def diverge(worktree: Path) -> None:
    """The integration branch edits the same file the other way."""
    (worktree / SHARED_FILE).write_text("from the integration branch\n")
    run_git("add", "--all", cwd=worktree)
    run_git("commit", "--quiet", "--message", "integration edits the shared file", cwd=worktree)


# ── a merge that goes through ───────────────────────────────────────────────


def test_a_merge_answers_the_commit_it_made_and_brings_the_work_in(
    git: SubprocessGit, worktree: Path
) -> None:
    """Also the proof that the abort is guarded: `git merge --abort` fails outright when no
    merge is in progress, so an unguarded one would fail this before anything was merged."""
    sha = git.merge(worktree, FROM_BRANCH)

    assert sha == git.head_sha(worktree)
    assert (worktree / BROUGHT_FILE).read_text() == "from the epic\n"


def test_the_merge_is_never_fast_forwarded_away(git: SubprocessGit, worktree: Path) -> None:
    """`--no-ff`: the integration branch records that this epic landed, as its own commit."""
    git.merge(worktree, FROM_BRANCH)

    parents = run_git("rev-list", "--parents", "-n", "1", "HEAD", cwd=worktree).split()

    assert len(parents) == 3  # noqa: PLR2004 — the commit and its two parents


def test_the_merge_commit_is_authored_by_the_orchestrator(
    git: SubprocessGit, worktree: Path
) -> None:
    """`HOME` is a private empty directory, so an identity that was not stated per command
    would leave git with nothing to guess from."""
    git.merge(worktree, FROM_BRANCH)

    author = run_git("log", "-1", "--format=%an <%ae>", cwd=worktree).strip()

    assert author == "orchestrator <orchestrator@local>"


# ── a ref the branch already holds ──────────────────────────────────────────


def test_a_second_merge_of_the_same_branch_answers_none(git: SubprocessGit, worktree: Path) -> None:
    git.merge(worktree, FROM_BRANCH)
    before = git.head_sha(worktree)

    assert git.merge(worktree, FROM_BRANCH) is None
    assert git.head_sha(worktree) == before


def test_a_merge_the_operator_completed_out_of_band_answers_none(
    git: SubprocessGit, worktree: Path, origin: Path, tmp_path: Path
) -> None:
    """AD-13's amended retry row: the Operator resolved the conflict and pushed, so the
    re-run of the row finds the work already contained rather than merging it twice."""
    conflicting_push(origin, tmp_path)
    diverge(worktree)
    with pytest.raises(GitError):
        git.merge(worktree, FROM_BRANCH)
    (worktree / SHARED_FILE).write_text("resolved by the operator\n")
    run_git("add", "--all", cwd=worktree)
    run_git("commit", "--quiet", "--no-edit", cwd=worktree)

    assert git.merge(worktree, FROM_BRANCH) is None


# ── a conflict ──────────────────────────────────────────────────────────────


def test_a_conflict_is_a_git_error_naming_the_files_that_conflicted(
    git: SubprocessGit, worktree: Path, origin: Path, tmp_path: Path
) -> None:
    conflicting_push(origin, tmp_path)
    diverge(worktree)

    with pytest.raises(GitError) as raised:
        git.merge(worktree, FROM_BRANCH)

    assert SHARED_FILE in raised.value.output
    assert "CONFLICT" in raised.value.output


def test_a_conflicted_merge_is_left_in_the_worktree_for_the_operator(
    git: SubprocessGit, worktree: Path, origin: Path, tmp_path: Path
) -> None:
    conflicting_push(origin, tmp_path)
    diverge(worktree)

    with pytest.raises(GitError):
        git.merge(worktree, FROM_BRANCH)

    assert run_git("rev-parse", "--verify", "MERGE_HEAD", cwd=worktree).strip()


def test_the_next_merge_aborts_the_one_left_in_progress_rather_than_refusing(
    git: SubprocessGit, worktree: Path, origin: Path, tmp_path: Path
) -> None:
    """AD-13's amended retry row: the row re-runs whole. Without the abort git would refuse
    with "you have not concluded your merge" and the Operator would be stuck on the park."""
    conflicting_push(origin, tmp_path)
    diverge(worktree)
    with pytest.raises(GitError):
        git.merge(worktree, FROM_BRANCH)

    with pytest.raises(GitError) as raised:
        git.merge(worktree, FROM_BRANCH)

    assert "CONFLICT" in raised.value.output
    assert "not concluded" not in raised.value.output


def test_a_retry_after_the_operator_fixed_the_epic_branch_merges_cleanly(
    git: SubprocessGit, worktree: Path, origin: Path, tmp_path: Path
) -> None:
    """The whole point of aborting first: the row that parked can run again and succeed."""
    conflicting_push(origin, tmp_path)
    diverge(worktree)
    with pytest.raises(GitError):
        git.merge(worktree, FROM_BRANCH)
    fixed = tmp_path / "fixed"
    clone_branch(origin, fixed, tmp_path)
    (fixed / SHARED_FILE).write_text("from the integration branch\n")
    run_git("add", "--all", cwd=fixed)
    run_git("commit", "--quiet", "--message", "epic takes the integration text", cwd=fixed)
    run_git("push", "--quiet", "origin", FROM_BRANCH, cwd=fixed)

    sha = git.merge(worktree, FROM_BRANCH)

    assert sha == git.head_sha(worktree)
