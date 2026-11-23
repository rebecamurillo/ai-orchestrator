"""`SubprocessGitHistory` against real `git` in `tmp_path` (story 5, AC9)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.git_history import FileStat, GitHistory
from orchestrator.infrastructure.git.git_history import SubprocessGitHistory

DUMMY = "not-a-token"
IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.test")


@pytest.fixture(autouse=True)
def git_binary() -> str:
    found = shutil.which("git")
    if found is None:
        pytest.fail("git is not on PATH: this module drives the real adapter.")
    return found


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
    (root / "a.txt").write_text("1\n2\n3\n4\n")
    (root / "old.txt").write_text("rename me\nsecond line\nthird\n")
    return root


def test_the_adapter_satisfies_the_port() -> None:
    assert isinstance(SubprocessGitHistory(), GitHistory)


def test_diff_stat_reads_text_counts_and_binary_as_none(repo: Path) -> None:
    first = commit(repo, "first")
    (repo / "a.txt").write_text("1\n2\nX\nY\nZ\n")
    (repo / "b.bin").write_bytes(b"\x00\x01\x02\x00")
    second = commit(repo, "second")

    stats = SubprocessGitHistory().diff_stat(repo, first, second)

    assert stats == (
        FileStat(path="a.txt", added=3, removed=2),
        FileStat(path="b.bin", added=None, removed=None),
    )


def test_diff_stat_reports_a_rename_under_its_new_path(repo: Path) -> None:
    first = commit(repo, "first")
    (repo / "old.txt").rename(repo / "new.txt")
    second = commit(repo, "second")

    stats = SubprocessGitHistory().diff_stat(repo, first, second)

    assert [s.path for s in stats] == ["new.txt"]
    assert (stats[0].added, stats[0].removed) == (0, 0)


def test_diff_stat_of_a_commit_against_its_parent(repo: Path) -> None:
    first = commit(repo, "first")
    (repo / "c.txt").write_text("c\n")
    second = commit(repo, "second")

    assert SubprocessGitHistory().diff_stat(repo, f"{second}~1", second) == (
        FileStat(path="c.txt", added=1, removed=0),
    )
    assert first


def test_commit_subject(repo: Path) -> None:
    commit(repo, "story 1: x (orchestrator)")
    head = git(repo, "rev-parse", "HEAD")

    assert SubprocessGitHistory().commit_subject(repo, head) == "story 1: x (orchestrator)"


def test_commit_subject_is_none_when_empty(repo: Path) -> None:
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "--allow-empty-message", "-m", "")
    head = git(repo, "rev-parse", "HEAD")

    assert SubprocessGitHistory().commit_subject(repo, head) is None


def test_an_unknown_sha_raises_git_error(repo: Path) -> None:
    commit(repo, "first")

    with pytest.raises(GitError) as raised:
        SubprocessGitHistory().commit_subject(repo, "0" * 40)
    assert raised.value.exit_code != 0
    with pytest.raises(GitError):
        SubprocessGitHistory().diff_stat(repo, "0" * 40, "1" * 40)


def test_a_timeout_is_a_git_error_with_exit_minus_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def hang(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(subprocess, "run", hang)

    with pytest.raises(GitError) as raised:
        SubprocessGitHistory().commit_subject(tmp_path, "abc1234")
    assert raised.value.exit_code == -1
    assert "timeout after" in raised.value.output


def test_the_environment_is_built_and_holds_no_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in ("GITHUB_TOKEN", "ORCHESTRATOR_GIT_TOKEN", "DATABASE_URL"):
        monkeypatch.setenv(name, DUMMY)
    seen: dict[str, Any] = {}

    def capture(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen["command"] = command
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout="subject\n", stderr="")

    monkeypatch.setattr(subprocess, "run", capture)

    assert SubprocessGitHistory().commit_subject(tmp_path, "abc1234") == "subject"

    assert set(seen["env"]) <= {"PATH", "HOME", "GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT"}
    assert DUMMY not in seen["env"].values()
    assert "credential.helper=" in seen["command"]
    assert seen["command"][-2:] == ["abc1234", "--"]
    assert os.environ["GITHUB_TOKEN"] == DUMMY


def test_a_non_zero_exit_with_no_output_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kw: subprocess.CompletedProcess(command, 3, stdout="", stderr=""),
    )

    with pytest.raises(GitError) as raised:
        SubprocessGitHistory().commit_subject(tmp_path, "abc1234")
    assert raised.value.output == "no output"
