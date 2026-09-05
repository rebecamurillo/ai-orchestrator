"""The `Git` port, its three frozen values, and the fake every use-case test injects (AD-18).

Nothing here runs `git`. What is asserted is the shape a use case is entitled to assume:
the port is structural, so `FakeGit` and `SubprocessGit` are interchangeable without either
inheriting from anything; `GitError` carries the three fields a failed line is rendered
from; and the fake behaves like a repository would — scripted answers in order, a recorded
call log, and a `Clock` that moves by the time each command is said to have taken, which is
what makes a line's `seconds` assertable without a real process.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.domain.ports.git import CloneResult, Git, GitError, RemoteRef
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.git import FakeGit

BASE = Path("/work/my-project/my-repo/base")
URL = "https://github.com/org/my-repo.git"
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"

#: How long every scripted command is said to take, when a test gives the fake a clock.
COMMAND_SECONDS = 2.0


def test_the_fake_satisfies_the_port() -> None:
    git: Git = FakeGit()

    assert isinstance(git, Git)


def test_a_remote_ref_carries_the_ref_and_the_sha_it_resolves_to() -> None:
    ref = RemoteRef(ref="refs/heads/main", sha=SHA)

    assert (ref.ref, ref.sha) == ("refs/heads/main", SHA)


def test_a_remote_ref_is_frozen() -> None:
    ref = RemoteRef(ref="refs/heads/main", sha=SHA)

    with pytest.raises(AttributeError):
        ref.sha = "other"  # type: ignore[misc]


def test_a_clone_result_carries_what_the_adapter_measured() -> None:
    result = CloneResult(seconds=1.5, bytes=4096)

    assert (result.seconds, result.bytes) == (1.5, 4096)


def test_a_clone_result_is_frozen() -> None:
    result = CloneResult(seconds=1.5, bytes=4096)

    with pytest.raises(AttributeError):
        result.bytes = 0  # type: ignore[misc]


def test_a_git_error_carries_the_command_the_code_and_the_output() -> None:
    error = GitError(command="git ls-remote", exit_code=128, output="fatal: nope")

    assert (error.command, error.exit_code, error.output) == ("git ls-remote", 128, "fatal: nope")


def test_a_git_error_says_what_failed_when_it_is_printed() -> None:
    """A raised error that stringified to nothing would make a traceback useless."""
    error = GitError(command="git ls-remote", exit_code=128, output="fatal: nope")

    assert "git ls-remote" in str(error)
    assert "128" in str(error)


def test_a_git_error_is_an_exception_a_use_case_can_catch() -> None:
    with pytest.raises(GitError):
        raise GitError(command="git clone", exit_code=1, output="")


# ── the fake ─────────────────────────────────────────────────────────────────


def test_the_fake_answers_the_scripted_value() -> None:
    ref = RemoteRef(ref="HEAD", sha=SHA)
    git = FakeGit(ls_remote=[ref])

    assert git.ls_remote(URL) is ref


def test_the_fake_raises_the_scripted_error() -> None:
    git = FakeGit(ls_remote=[GitError(command="git ls-remote", exit_code=128, output="fatal")])

    with pytest.raises(GitError):
        git.ls_remote(URL)


def test_the_fake_answers_each_scripted_value_in_turn() -> None:
    first = RemoteRef(ref="HEAD", sha=SHA)
    second = RemoteRef(ref="refs/heads/main", sha=SHA)
    git = FakeGit(ls_remote=[first, second])

    assert (git.ls_remote(URL), git.ls_remote(URL, "main")) == (first, second)


def test_the_fake_repeats_its_last_answer_once_the_script_runs_out() -> None:
    """A test that scripted one answer is asserting that answer, not the length of a list."""
    git = FakeGit(base_exists=[False])

    assert (git.base_exists(BASE), git.base_exists(BASE)) == (False, False)


def test_the_fake_records_every_call_with_its_arguments() -> None:
    git = FakeGit(ls_remote=[None], base_exists=[True])
    git.ls_remote(URL, "main")
    git.base_exists(BASE)

    assert git.calls == [("ls_remote", (URL, "main")), ("base_exists", (BASE,))]


def test_the_fake_defaults_are_the_reachable_repository() -> None:
    """The ok path is the one most tests want; only the failing rows script anything."""
    git = FakeGit()

    assert git.ls_remote(URL) is not None
    assert git.base_exists(BASE) is False
    assert git.clone_base(URL, BASE).bytes > 0
    assert git.fetch_base(BASE, "main") is None
    assert git.branch_exists(BASE, "main") is True
    assert git.read_file(BASE, "main", "x.yaml") is None


def test_the_fake_moves_the_clock_it_was_given_by_one_command_duration() -> None:
    """`FakeClock` only moves when something moves it; this is what a line's `seconds` is."""
    clock = FakeClock()
    start = clock.now()
    git = FakeGit(clock=clock, seconds=COMMAND_SECONDS)

    git.ls_remote(URL)

    assert (clock.now() - start).total_seconds() == COMMAND_SECONDS


def test_the_fake_without_a_clock_moves_nothing() -> None:
    git = FakeGit()

    assert git.clock is None
