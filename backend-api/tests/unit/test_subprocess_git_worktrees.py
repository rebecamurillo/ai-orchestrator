"""`infrastructure/git/worktrees.py`: the worktree half of the adapter, against real `git`.

Everything in this module runs commands. That is the point: the executors are proven over
`FakeGit`, and what only a real process settles is that these commands exist, take the flags
they are given, and answer in the shapes the port promises — `""` for a clean worktree,
`None` for a branch with no upstream, a `GitError` for a push the remote refused.

The remote is a bare repository under `tmp_path`, addressed by `file://`, so nothing here
needs the network or a credential — the credential rule itself is
`tests/unit/test_subprocess_git.py`'s, and every command below runs through the same `_run`
it checks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import Git, GitError
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from orchestrator.infrastructure.git.worktrees import AUTHOR, NO_HOOKS

TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
BRANCH = "main"
FEATURE = "chore/bmad-init"
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
    """A base clone of the origin, as `git.worktree` makes one."""
    destination = tmp_path / "work" / "acme" / "widgets" / "base"
    git.clone_base(f"file://{origin}", destination)
    git.fetch_base(destination, BRANCH)
    return destination


@pytest.fixture
def worktree(git: SubprocessGit, base: Path, tmp_path: Path) -> Path:
    """A worktree on a branch this "Run" created, exactly as the executor creates one."""
    path = tmp_path / "work" / "acme" / "widgets" / "wt" / FEATURE
    git.worktree_add(base, path, FEATURE, f"origin/{BRANCH}")
    return path


def clone_of(origin: Path, into: Path, tmp_path: Path) -> None:
    """Someone else's clone of the same branch — what "the remote moved" is made of."""
    run_git("clone", "--quiet", f"file://{origin}", "--branch", FEATURE, str(into), cwd=tmp_path)


def test_the_adapter_still_satisfies_the_whole_port() -> None:
    assert isinstance(SubprocessGit(TOKEN), Git)


def test_every_writing_command_disables_the_repositorys_own_hooks() -> None:
    """A cloned repository's hooks are not code this system agreed to run."""
    assert NO_HOOKS == ("-c", "core.hooksPath=/dev/null")
    assert AUTHOR[1].endswith("orchestrator")
    assert AUTHOR[3].endswith("orchestrator@local")


# ── worktree_add ────────────────────────────────────────────────────────────


def test_a_new_branch_is_created_at_the_start_point_and_checked_out(worktree: Path) -> None:
    assert (worktree / SEED_FILE).read_text() == "seed\n"


def test_a_branch_the_origin_holds_is_checked_out_without_a_start_point(
    git: SubprocessGit, base: Path, tmp_path: Path
) -> None:
    path = tmp_path / "wt-main"

    git.worktree_add(base, path, BRANCH, None)

    assert (path / SEED_FILE).is_file()
    assert git.head_sha(path) is not None


def test_the_parent_directories_of_a_nested_branch_path_are_made(worktree: Path) -> None:
    """`chore/bmad-init` is two directory levels under `wt/` (AD-14)."""
    assert worktree.parent.name == "chore"


# ── status, stage, commit ───────────────────────────────────────────────────


def test_a_clean_worktree_reports_nothing_at_all(git: SubprocessGit, worktree: Path) -> None:
    assert git.status(worktree) == ""


def test_an_untracked_file_is_reported_and_staged_and_committed(
    git: SubprocessGit, worktree: Path
) -> None:
    (worktree / "new.txt").write_text("hello\n")
    assert "new.txt" in git.status(worktree)

    git.stage(worktree)
    sha = git.commit(worktree, "chore: initialise BMAD method (orchestrator)")

    assert git.status(worktree) == ""
    assert sha == git.head_sha(worktree)
    assert "orchestrator" in run_git("log", "-1", "--format=%an <%ae>", cwd=worktree)


def test_staging_one_pathspec_leaves_everything_outside_it_alone(
    git: SubprocessGit, worktree: Path
) -> None:
    (worktree / "spec").mkdir()
    (worktree / "spec" / "SPEC.md").write_text("spec\n")
    (worktree / "other.txt").write_text("other\n")

    git.stage(worktree, "spec")

    staged = run_git("diff", "--cached", "--name-only", cwd=worktree).split()
    assert staged == ["spec/SPEC.md"]


def test_a_commit_message_is_kept_verbatim(git: SubprocessGit, worktree: Path) -> None:
    (worktree / "new.txt").write_text("hello\n")
    git.stage(worktree)

    git.commit(worktree, "story 4-8: git step kinds (orchestrator)")

    assert (
        run_git("log", "-1", "--format=%s", cwd=worktree).strip()
        == "story 4-8: git step kinds (orchestrator)"
    )


# ── diff_names ──────────────────────────────────────────────────────────────


def test_diff_names_unions_the_committed_change_and_the_untracked_file(
    git: SubprocessGit, worktree: Path
) -> None:
    start = git.head_sha(worktree)
    assert start is not None
    (worktree / SEED_FILE).write_text("changed\n")
    git.stage(worktree)
    git.commit(worktree, "wip")
    (worktree / "untracked.txt").write_text("later\n")

    assert set(git.diff_names(worktree, start)) == {SEED_FILE, "untracked.txt"}


# ── sync ────────────────────────────────────────────────────────────────────


def test_a_branch_with_no_upstream_answers_none(git: SubprocessGit, worktree: Path) -> None:
    """AD-14: a branch this Run created and never pushed is a recorded no-op, not a failure."""
    assert git.sync(worktree, FEATURE) is None


def test_a_pushed_branch_fast_forwards_onto_what_the_remote_holds(
    git: SubprocessGit, worktree: Path
) -> None:
    git.push(worktree, FEATURE, True)

    assert git.sync(worktree, FEATURE) is not None


def test_a_diverged_branch_raises_rather_than_merging(
    git: SubprocessGit, worktree: Path, origin: Path, tmp_path: Path
) -> None:
    git.push(worktree, FEATURE, True)
    elsewhere = tmp_path / "elsewhere"
    clone_of(origin, elsewhere, tmp_path)
    (elsewhere / "theirs.txt").write_text("theirs\n")
    run_git("add", "--all", cwd=elsewhere)
    run_git("commit", "--quiet", "--message", "theirs", cwd=elsewhere)
    run_git("push", "--quiet", "origin", FEATURE, cwd=elsewhere)
    (worktree / "ours.txt").write_text("ours\n")
    git.stage(worktree)
    git.commit(worktree, "ours")

    with pytest.raises(GitError):
        git.sync(worktree, FEATURE)


# ── push ────────────────────────────────────────────────────────────────────


def test_a_first_push_lands_the_branch_on_the_origin(
    git: SubprocessGit, worktree: Path, origin: Path
) -> None:
    git.push(worktree, FEATURE, True)

    assert FEATURE in run_git("branch", "--list", FEATURE, cwd=origin)


def test_a_push_the_remote_refuses_is_a_git_error(
    git: SubprocessGit, worktree: Path, origin: Path, tmp_path: Path
) -> None:
    git.push(worktree, FEATURE, True)
    elsewhere = tmp_path / "theirs"
    clone_of(origin, elsewhere, tmp_path)
    (elsewhere / "theirs.txt").write_text("theirs\n")
    run_git("add", "--all", cwd=elsewhere)
    run_git("commit", "--quiet", "--message", "theirs", cwd=elsewhere)
    run_git("push", "--quiet", "origin", FEATURE, cwd=elsewhere)
    (worktree / "ours.txt").write_text("ours\n")
    git.stage(worktree)
    git.commit(worktree, "ours")

    with pytest.raises(GitError):
        git.push(worktree, FEATURE, False)


# ── head_sha, remove_worktree, delete_branch ────────────────────────────────


def test_a_repository_with_no_commit_yet_has_no_head(git: SubprocessGit, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    run_git("init", "--quiet", ".", cwd=empty)

    assert git.head_sha(empty) is None


def test_a_worktree_is_removed_and_its_branch_deleted(
    git: SubprocessGit, base: Path, worktree: Path
) -> None:
    """What `cancel` does to a Run that created a branch it never pushed (AD-13)."""
    git.remove_worktree(base, worktree)
    git.delete_branch(base, FEATURE)

    assert not worktree.exists()
    assert FEATURE not in run_git("branch", "--list", FEATURE, cwd=base)


def test_a_dirty_worktree_is_still_removed(git: SubprocessGit, base: Path, worktree: Path) -> None:
    (worktree / "left-behind.txt").write_text("uncommitted\n")

    git.remove_worktree(base, worktree)

    assert not worktree.exists()


def test_removing_something_already_gone_is_not_a_failure(
    git: SubprocessGit, base: Path, tmp_path: Path
) -> None:
    """`cancel` calls both on a Run whose rows may never have created either (AD-13)."""
    git.remove_worktree(base, tmp_path / "never-made")
    git.delete_branch(base, "never/made")
