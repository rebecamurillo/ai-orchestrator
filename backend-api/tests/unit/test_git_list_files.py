"""`Git.list_files`: the port's fourth read, its fake, and the adapter behind it.

The planner asks one question of a tree it never checks out — *which story files are in
`{spec_folder}/stories/` at this commit?* — and `read_file` cannot answer it. The method is
here rather than folded into `read_file` because it is a listing and not a read: a folder
with nothing in it is `()`, exactly as a file that is not there is `None`, which is the
port's second convention.

The adapter half runs against a real repository this test makes in `tmp_path`, the way
`test_subprocess_git.py` builds one: a listing is what `git ls-tree` says it is, and a fake
that agreed with a hand-written expectation instead would be a fake nothing checked.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import Git, GitError
from orchestrator.infrastructure.git.subprocess_git import SubprocessGit
from tests.unit.fakes.git import FakeGit

TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
BRANCH = "main"
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
BASE = Path("/work/my-project/my-repo/base")

STORIES = "docs/epic-1/stories"
FIRST = f"{STORIES}/4-1-first.md"
SECOND = f"{STORIES}/4-2-second.md"
ELSEWHERE = "docs/epic-1/SPEC.md"
#: A story file whose name git would quote and octal-escape without `-z`. A Story is named
#: by an Operator, so this is an ordinary file name and not a hostile one.
ACCENTED = f"{STORIES}/4-3-caf\u00e9-story.md"


@pytest.fixture(autouse=True)
def git_binary() -> str:
    """`git` is a requirement of this module, not a condition on running it."""
    found = shutil.which("git")
    if found is None:
        pytest.fail("git is not on PATH: this module drives the real adapter")
    return found


def run_git(*arguments: str, cwd: Path) -> str:
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


# --- the port and its fake ---------------------------------------------------------------


def test_the_fake_still_satisfies_the_port_with_the_new_method() -> None:
    git: Git = FakeGit()

    assert isinstance(git, Git)


def test_the_fake_answers_the_paths_scripted_for_that_ref_and_prefix() -> None:
    git = FakeGit(listings={(SHA, STORIES): [FIRST, SECOND]})

    assert git.list_files(BASE, SHA, STORIES) == (FIRST, SECOND)


def test_the_fake_answers_nothing_for_a_prefix_it_was_given_no_paths_for() -> None:
    git = FakeGit(listings={})

    assert git.list_files(BASE, SHA, STORIES) == ()


def test_the_fake_records_the_listing_like_every_other_call() -> None:
    git = FakeGit(listings={})

    git.list_files(BASE, SHA, STORIES)

    assert git.called("list_files") == [(BASE, SHA, STORIES)]


def test_the_fake_without_a_listings_mapping_falls_back_to_the_sequential_script() -> None:
    """Every caller that predates the mapping keywords keeps the behaviour it had."""
    git = FakeGit(list_files=[(FIRST,)])

    assert git.list_files(BASE, SHA, STORIES) == (FIRST,)


def test_the_fake_lists_nothing_by_default() -> None:
    assert FakeGit().list_files(BASE, SHA, STORIES) == ()


# --- the adapter -------------------------------------------------------------------------


@pytest.fixture
def base(tmp_path: Path) -> Path:
    """A base clone of a repository holding two story files and one file beside them."""
    origin = tmp_path / "origin.git"
    run_git("init", "--quiet", "--bare", str(origin), cwd=tmp_path)

    seed = tmp_path / "seed"
    seed.mkdir()
    run_git("init", "--quiet", f"--initial-branch={BRANCH}", ".", cwd=seed)
    for path in (FIRST, SECOND, ACCENTED, ELSEWHERE):
        target = seed / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path)
    run_git("add", "--all", cwd=seed)
    run_git("commit", "--quiet", "--message", "seed", cwd=seed)
    run_git("push", "--quiet", f"file://{origin}", f"{BRANCH}:{BRANCH}", cwd=seed)

    clone = tmp_path / "base"
    SubprocessGit(TOKEN).clone_base(f"file://{origin}", clone)
    return clone


@pytest.fixture
def git() -> SubprocessGit:
    return SubprocessGit(TOKEN)


def test_the_adapter_lists_every_path_under_the_prefix(git: SubprocessGit, base: Path) -> None:
    assert set(git.list_files(base, BRANCH, STORIES)) == {FIRST, SECOND, ACCENTED}


def test_a_path_git_would_quote_comes_back_as_the_path_the_tree_holds(
    git: SubprocessGit, base: Path
) -> None:
    """Without `-z` this is `"docs/…/4-3-caf\303\251-story.md"`, and `{id}-*.md` never
    matches it — so a finished Story would be planned and dispatched all over again."""
    listed = git.list_files(base, BRANCH, STORIES)

    assert ACCENTED in listed
    assert not any(path.startswith('"') for path in listed)


def test_the_adapter_lists_nothing_beside_the_prefix(git: SubprocessGit, base: Path) -> None:
    assert ELSEWHERE not in git.list_files(base, BRANCH, STORIES)


def test_the_adapter_reads_the_remote_tracking_ref_a_base_clone_actually_holds(
    git: SubprocessGit, base: Path
) -> None:
    """A base clone is never checked out, so `origin/main` is what it has."""
    assert set(git.list_files(base, f"origin/{BRANCH}", STORIES)) == {FIRST, SECOND, ACCENTED}


def test_a_prefix_the_tree_does_not_hold_lists_nothing(git: SubprocessGit, base: Path) -> None:
    assert git.list_files(base, BRANCH, "docs/nothing") == ()


def test_a_ref_that_does_not_exist_lists_nothing(git: SubprocessGit, base: Path) -> None:
    assert git.list_files(base, "no-such-branch", STORIES) == ()


def test_a_listing_that_outlives_its_timeout_is_a_failure_and_never_an_empty_folder(
    base: Path,
) -> None:
    """A command that never finished says nothing about what is in the tree."""
    impatient = SubprocessGit(TOKEN, timeout_seconds=0)

    with pytest.raises(GitError) as raised:
        impatient.list_files(base, BRANCH, STORIES)

    assert "timeout" in raised.value.output
