"""The analysis half of the `Git` port and its fake (story 5.1)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.ports.git_analysis import AnalysisGit, NameStatus, NumstatEntry
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript

DEST = Path("/scratch/root")


def test_the_fake_satisfies_the_port_and_its_analysis_half() -> None:
    fake = FakeGit()
    port: Git = fake
    half: AnalysisGit = fake
    assert port is half


def test_unscripted_answers_are_the_ports_not_there() -> None:
    fake = FakeGit()
    fake.fetch("url", ("main",), DEST)
    assert fake.merge_base(DEST, "a", "b") is None
    assert fake.diff_numstat(DEST, "a", "b") == ()
    assert fake.diff_name_status(DEST, "a", "b") == ()
    assert fake.diff_text(DEST, "a", "b", ()) == ""
    assert fake.commits_between(DEST, "a", "b") == ()


def test_scripted_answers_and_the_call_log() -> None:
    entry = NumstatEntry(path="a.py", added=1, removed=2, binary=False)
    status = NameStatus(status="R", path="b.py", old_path="a.py")
    fake = FakeGit(
        analysis=AnalysisScript(
            merge_bases={("x", "y"): "m0"},
            numstat={("m0", "h1"): (entry,)},
            name_status={("m0", "h1"): (status,)},
            diff_text={("m0", "h1"): "@@"},
            commits={("m0", "h1"): ("c1", "c2")},
        )
    )
    assert fake.merge_base(DEST, "y", "x") == "m0"
    assert fake.merge_base(DEST, "x", "y") == "m0"
    assert fake.diff_numstat(DEST, "m0", "h1") == (entry,)
    assert fake.diff_name_status(DEST, "m0", "h1") == (status,)
    assert fake.diff_text(DEST, "m0", "h1", ("a.py",)) == "@@"
    assert fake.commits_between(DEST, "m0", "h1") == ("c1", "c2")
    assert [name for name, _ in fake.calls] == [
        "merge_base",
        "merge_base",
        "diff_numstat",
        "diff_name_status",
        "diff_text",
        "commits_between",
    ]


def test_a_scripted_fetch_failure_raises_for_that_ref_only() -> None:
    error = GitError(command="git fetch", exit_code=128, output="not our ref h9")
    fake = FakeGit(analysis=AnalysisScript(fetch={"h9": error}))
    fake.fetch("url", ("main",), DEST)
    with pytest.raises(GitError):
        fake.fetch("url", ("h9",), DEST)
    assert fake.calls[-1] == ("fetch", ("url", ("h9",), DEST))


def test_the_value_types_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        NumstatEntry(path="a", added=0, removed=0, binary=True).added = 1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        NameStatus(status="A", path="a", old_path=None).path = "b"  # type: ignore[misc]
