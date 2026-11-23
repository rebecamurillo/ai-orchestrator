"""`GitHistory.diff_path` on the real adapter and on the fake (story 7, AC7)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.git_history import GitHistory
from orchestrator.infrastructure.git.git_history import SubprocessGitHistory
from tests.unit.fakes.git_history import FakeGitHistory

IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.test")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *IDENTITY, "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "r"
    root.mkdir()
    git(root, "init", "--quiet", "--initial-branch=main")
    (root / "a.txt").write_text("1\n2\n")
    (root / "b.txt").write_text("x\n")
    return root


def test_diff_path_names_only_the_asked_path(repo: Path) -> None:
    first = commit(repo, "first")
    (repo / "a.txt").write_text("1\n2\n3\n")
    (repo / "b.txt").write_text("y\n")
    second = commit(repo, "second")

    diff = SubprocessGitHistory().diff_path(repo, first, second, "a.txt")

    assert "a.txt" in diff
    assert "+3" in diff
    assert "b.txt" not in diff


def test_diff_path_with_an_unknown_sha_raises_git_error(repo: Path) -> None:
    commit(repo, "first")

    with pytest.raises(GitError):
        SubprocessGitHistory().diff_path(repo, "0" * 40, "1" * 40, "a.txt")


def test_the_adapter_and_the_fake_satisfy_the_port() -> None:
    assert isinstance(SubprocessGitHistory(), GitHistory)
    assert isinstance(FakeGitHistory(), GitHistory)


def test_the_fake_answers_from_its_dict_and_records_the_call() -> None:
    fake = FakeGitHistory(diffs={("/r", "a", "b", "p"): "DIFF"})

    assert fake.diff_path(Path("/r"), "a", "b", "p") == "DIFF"
    assert fake.diff_path(Path("/r"), "a", "b", "other") == ""
    assert fake.calls[0] == ("diff_path", "/r", "a", "b", "p")


def test_the_fake_raises_its_error() -> None:
    error = GitError(command="git diff", exit_code=1, output="boom")

    with pytest.raises(GitError):
        FakeGitHistory(error=error).diff_path(Path("/r"), "a", "b", "p")


def test_diff_path_reads_a_glob_character_as_a_literal_name(repo: Path) -> None:
    (repo / "[ab].txt").write_text("q\n")
    first = commit(repo, "first")
    (repo / "a.txt").write_text("changed\n")
    (repo / "[ab].txt").write_text("r\n")
    second = commit(repo, "second")

    diff = SubprocessGitHistory().diff_path(repo, first, second, "[ab].txt")

    assert "[ab].txt" in diff
    assert "a/a.txt" not in diff


def test_diff_path_of_a_file_that_is_not_utf8_answers_text(repo: Path) -> None:
    first = commit(repo, "first")
    (repo / "a.txt").write_bytes("caf\xe9\n".encode("latin-1"))
    second = commit(repo, "second")

    diff = SubprocessGitHistory().diff_path(repo, first, second, "a.txt")

    assert "caf�" in diff
