"""The `GitHistory` port and its one fake (story 5)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.git_history import FileStat, GitHistory
from tests.unit.fakes.git_history import FakeGitHistory

REPO = Path("/work/r")
STAT = FileStat(path="a.py", added=1, removed=2)


def test_the_fake_satisfies_the_port() -> None:
    assert isinstance(FakeGitHistory(), GitHistory)


def test_file_stat_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        STAT.added = 5  # type: ignore[misc]


def test_the_fake_answers_from_its_dicts_and_records_calls() -> None:
    fake = FakeGitHistory(
        stats={(str(REPO), "a", "b"): (STAT,)}, subjects={(str(REPO), "b"): "subject"}
    )

    assert fake.diff_stat(REPO, "a", "b") == (STAT,)
    assert fake.commit_subject(REPO, "b") == "subject"
    assert fake.calls == [("diff_stat", str(REPO), "a", "b"), ("commit_subject", str(REPO), "b")]


def test_an_unknown_key_answers_empty() -> None:
    fake = FakeGitHistory()

    assert fake.diff_stat(REPO, "x", "y") == ()
    assert fake.commit_subject(REPO, "x") is None


def test_the_fake_raises_the_error_it_is_given() -> None:
    error = GitError(command="git", exit_code=1, output="bad")
    fake = FakeGitHistory(error=error)

    with pytest.raises(GitError):
        fake.diff_stat(REPO, "a", "b")
    with pytest.raises(GitError):
        fake.commit_subject(REPO, "a")
