"""`Git.diff_changes`: a bounded commit range, and *how* each path in it changed (AD-17).

`diff_names` answers "what is different between a commit and the worktree as it stands",
which is the question the commit-guard asks. AD-17's other call site asks a different one:
what did *this attempt* do, between the SHA recorded before the harness started and the SHA
recorded after it exited — and whether each path was added, modified or deleted, because a
deleted anchor is a hit and a file the agent created inside the frame is not.

Everything here runs the real `git`, for the reason `test_subprocess_git_worktrees.py` does:
only a process settles that `--name-status -z` exists, takes those flags, and separates its
fields the way the adapter reads them. The rule that turns these values into a park is
`tests/unit/application/test_protected_paths_rule.py`'s, over no process at all.

The last section is `status`, for the same reason. AD-17's other input is the uncommitted
tree, and two of porcelain's defaults quietly hide an anchor from the rule: an untracked
*directory* is collapsed to one entry, and a path with non-ASCII bytes is C-quoted into a
string that equals no anchor. Only a real `git` can prove the flags that fix both.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.application.rules import protected_paths
from orchestrator.domain.ports.git import Change, Git
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from tests.unit.fakes.git import FakeGit

TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
BRANCH = "main"
SEED_FILE = "README.md"
ANCHOR = "AGENTS.md"


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
def git() -> SubprocessGit:
    return SubprocessGit(TOKEN)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """A worktree with one commit, standing in for the one a Run works in."""
    path = tmp_path / "wt"
    path.mkdir()
    run_git("init", "--quiet", f"--initial-branch={BRANCH}", ".", cwd=path)
    (path / SEED_FILE).write_text("seed\n")
    (path / ANCHOR).write_text("rules\n")
    run_git("add", "--all", cwd=path)
    run_git("commit", "--quiet", "--message", "seed", cwd=path)
    return path


def commit(path: Path, message: str) -> None:
    run_git("add", "--all", cwd=path)
    run_git("commit", "--quiet", "--message", message, cwd=path)


def head(git: SubprocessGit, path: Path) -> str:
    sha = git.head_sha(path)
    assert sha is not None
    return sha


def test_the_fake_and_the_adapter_both_still_satisfy_the_port() -> None:
    """The port grew a method: a fake that had not grown with it would fail here first."""
    assert isinstance(SubprocessGit(TOKEN), Git)
    assert isinstance(FakeGit(), Git)


def test_a_modified_file_is_reported_as_modified(git: SubprocessGit, repository: Path) -> None:
    start = head(git, repository)
    (repository / SEED_FILE).write_text("changed\n")
    commit(repository, "edit")

    assert git.diff_changes(repository, start, head(git, repository)) == (
        Change(path=SEED_FILE, kind="modified"),
    )


def test_a_new_file_is_reported_as_added(git: SubprocessGit, repository: Path) -> None:
    start = head(git, repository)
    (repository / "web-client").mkdir()
    (repository / "web-client" / ANCHOR).write_text("rules\n")
    commit(repository, "add")

    assert git.diff_changes(repository, start, head(git, repository)) == (
        Change(path=f"web-client/{ANCHOR}", kind="added"),
    )


def test_a_removed_file_is_reported_as_deleted(git: SubprocessGit, repository: Path) -> None:
    start = head(git, repository)
    (repository / ANCHOR).unlink()
    commit(repository, "remove")

    assert git.diff_changes(repository, start, head(git, repository)) == (
        Change(path=ANCHOR, kind="deleted"),
    )


def test_a_rename_reads_as_the_deletion_of_the_old_path_and_the_addition_of_the_new(
    git: SubprocessGit, repository: Path
) -> None:
    """AD-17: moving a protected file away is losing it, whatever git calls the operation."""
    start = head(git, repository)
    (repository / ANCHOR).rename(repository / "MOVED.md")
    commit(repository, "rename")

    changes = git.diff_changes(repository, start, head(git, repository))

    assert Change(path=ANCHOR, kind="deleted") in changes
    assert Change(path="MOVED.md", kind="added") in changes


def test_a_range_that_committed_nothing_is_empty(git: SubprocessGit, repository: Path) -> None:
    start = head(git, repository)

    assert git.diff_changes(repository, start, start) == ()


def test_a_commit_outside_the_range_is_not_in_it(git: SubprocessGit, repository: Path) -> None:
    """The operator edit AD-17 must never attribute to an agent: a commit before the range."""
    (repository / ANCHOR).write_text("operator\n")
    commit(repository, "spec: operator edit (orchestrator)")
    start = head(git, repository)
    (repository / SEED_FILE).write_text("agent\n")
    commit(repository, "agent")

    assert git.diff_changes(repository, start, head(git, repository)) == (
        Change(path=SEED_FILE, kind="modified"),
    )


def test_a_ref_the_repository_does_not_hold_answers_nothing(
    git: SubprocessGit, repository: Path
) -> None:
    """The port's second convention: "not there" is an ordinary answer, not a `GitError`."""
    assert git.diff_changes(repository, "0" * 40, head(git, repository)) == ()


def test_the_fake_scripts_the_answer_and_logs_the_call() -> None:
    changes = (Change(path=ANCHOR, kind="modified"),)
    fake = FakeGit(diff_changes=[changes])

    assert fake.diff_changes(Path("/wt"), "a" * 40, "b" * 40) == changes
    assert fake.called("diff_changes") == [(Path("/wt"), "a" * 40, "b" * 40)]


def test_the_fake_answers_nothing_when_a_test_scripted_nothing() -> None:
    assert FakeGit().diff_changes(Path("/wt"), "a" * 40, "b" * 40) == ()


# ── status, as AD-17's rule has to read it ──────────────────────────────────


def test_an_anchor_inside_an_untracked_directory_is_named_by_status(
    git: SubprocessGit, repository: Path
) -> None:
    """Plain porcelain collapses a wholly untracked folder to one `?? dir/` entry, and the
    frozen-anchor rule cannot see a file that was never named — AD-17's headline case."""
    nested = repository / "web-client" / "docs"
    nested.mkdir(parents=True)
    (nested / ANCHOR).write_text("rules\n")

    changed = protected_paths.uncommitted(git.status(repository))

    assert Change(path=f"web-client/docs/{ANCHOR}", kind="added") in changed


def test_a_path_with_non_ascii_bytes_is_reported_unquoted(
    git: SubprocessGit, repository: Path
) -> None:
    """Porcelain C-quotes such a path by default, and a quoted string is a different string
    from the anchor it is compared against — and from the `AGENTS.md` basename."""
    folder = repository / "spécs"
    folder.mkdir()
    (folder / "SPEC.md").write_text("spec\n")

    changed = protected_paths.uncommitted(git.status(repository))

    assert Change(path="spécs/SPEC.md", kind="added") in changed


def test_the_untracked_anchor_is_a_hit_the_rule_can_actually_report(
    git: SubprocessGit, repository: Path
) -> None:
    """The two fixes above, end to end: a nested untracked `AGENTS.md` parks the Run."""
    nested = repository / "web-client"
    nested.mkdir()
    (nested / ANCHOR).write_text("rules\n")

    hits = protected_paths.check(
        protected_paths.uncommitted(git.status(repository)), frozenset(), ()
    )

    assert [hit.path for hit in hits] == [f"web-client/{ANCHOR}"]
