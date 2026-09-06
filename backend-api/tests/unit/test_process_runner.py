"""`RealProcessRunner`: the one adapter that starts a process for this system (AD-14, FR-10).

Every scenario here is one of the story's acceptance criteria, run against the real
adapter rather than the fake — `tests/unit/fakes/process.py` is what a `shell` row's own
tests use, and this is what proves the fake's contract is one the real thing actually
keeps: a hard timeout that survives a process ignoring `SIGTERM`, `kill_group` idempotent
either way, and an environment that is built rather than inherited.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from orchestrator.domain.ports.process import Handle, ProcessRunner
from orchestrator.infrastructure.process.runner import RealProcessRunner

#: Well under the AC's own 12 s ceiling for a one-second timeout plus the ten-second grace.
TIMEOUT_DEADLINE_SECONDS = 12.0
#: How long `kill_group`'s own poll loop is allowed before the test gives up on it.
KILL_DEADLINE_SECONDS = 12.0


def test_the_adapter_satisfies_the_port() -> None:
    runner: ProcessRunner = RealProcessRunner()

    assert isinstance(runner, ProcessRunner)


def test_a_command_that_ignores_sigterm_is_killed_within_the_deadline(tmp_path: Path) -> None:
    """AC 1: `timeout_min` fractional, `wait` reports it, the group and the log both prove it."""
    runner = RealProcessRunner()
    log_path = tmp_path / "logs" / "001-1.log"

    start = time.monotonic()
    handle = runner.start(
        ["bash", "-c", "trap '' TERM; sleep 60"],
        cwd=None,
        env={},
        timeout_min=1 / 60,
        log_path=log_path,
    )
    outcome = runner.wait(handle)
    elapsed = time.monotonic() - start

    assert outcome.timed_out is True
    assert elapsed <= TIMEOUT_DEADLINE_SECONDS
    assert not _group_alive(handle.pgid)
    assert log_path.exists()


def test_a_command_that_exits_on_its_own_is_not_reported_as_timed_out(tmp_path: Path) -> None:
    runner = RealProcessRunner()
    log_path = tmp_path / "logs" / "002-1.log"

    handle = runner.start(["true"], cwd=None, env={}, timeout_min=1.0, log_path=log_path)
    outcome = runner.wait(handle)

    assert outcome == type(outcome)(exit_code=0, timed_out=False)


def test_kill_group_called_twice_both_return_without_error(tmp_path: Path) -> None:
    """AC 2: idempotent, whichever of a timeout and a `cancel` gets there first (AD-13)."""
    runner = RealProcessRunner()
    log_path = tmp_path / "logs" / "003-1.log"
    handle = runner.start(["sleep", "30"], cwd=None, env={}, timeout_min=5.0, log_path=log_path)

    runner.kill_group(handle.pgid)
    runner.kill_group(handle.pgid)

    deadline = time.monotonic() + KILL_DEADLINE_SECONDS
    while _group_alive(handle.pgid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _group_alive(handle.pgid)
    runner.wait(handle)  # reap it, so the test leaves no zombie behind


def test_kill_group_on_a_group_that_never_existed_is_a_no_op() -> None:
    """A pgid nothing started is exactly what a group already reaped looks like."""
    RealProcessRunner().kill_group(999_999)


def test_the_environment_is_the_callers_plus_the_five_names_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC 3: the caller's variables, `PATH`/`HOME`/`LANG`/`TERM`/`GIT_TERMINAL_PROMPT`,
    never a secret this process holds — proven by setting one of each kind first."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_should_never_appear")
    monkeypatch.setenv("LITELLM_SPEND_KEY", "sk-should-never-appear")
    monkeypatch.setenv("DATABASE_URL", "postgresql://should/never/appear")
    monkeypatch.setenv("ORCHESTRATOR_TOKEN", "orch-should-never-appear")
    runner = RealProcessRunner()
    log_path = tmp_path / "logs" / "004-1.log"

    handle = runner.start(
        "env", cwd=None, env={"MY_PROJECT_VAR": "hello"}, timeout_min=1.0, log_path=log_path
    )
    outcome = runner.wait(handle)

    assert outcome.exit_code == 0
    printed = dict(line.split("=", 1) for line in log_path.read_text().splitlines() if "=" in line)
    assert printed["MY_PROJECT_VAR"] == "hello"
    for name in ("PATH", "HOME", "LANG", "TERM", "GIT_TERMINAL_PROMPT"):
        assert name in printed
    assert printed["TERM"] == "dumb"
    assert printed["GIT_TERMINAL_PROMPT"] == "0"
    for secret in ("GITHUB_TOKEN", "LITELLM_SPEND_KEY", "DATABASE_URL", "ORCHESTRATOR_TOKEN"):
        assert secret not in printed


def test_stdout_and_stderr_both_land_in_the_log(tmp_path: Path) -> None:
    runner = RealProcessRunner()
    log_path = tmp_path / "logs" / "005-1.log"

    handle = runner.start(
        "echo out; echo err 1>&2", cwd=None, env={}, timeout_min=1.0, log_path=log_path
    )
    runner.wait(handle)

    text = log_path.read_text()
    assert "out" in text
    assert "err" in text


def test_the_command_runs_in_the_given_cwd(tmp_path: Path) -> None:
    runner = RealProcessRunner()
    log_path = tmp_path / "logs" / "006-1.log"
    workdir = tmp_path / "work"
    workdir.mkdir()

    handle = runner.start("pwd", cwd=workdir, env={}, timeout_min=1.0, log_path=log_path)
    runner.wait(handle)

    assert log_path.read_text().strip() == str(workdir)


def test_waiting_on_an_unknown_handle_answers_cleanly_rather_than_raising() -> None:
    """A `wait` this process never `start`ed — e.g. after a restart — is not a crash."""
    outcome = RealProcessRunner().wait(Handle(pid=123, pgid=123))

    assert outcome.exit_code is None
    assert outcome.timed_out is False


def _group_alive(pgid: int) -> bool:
    """Mirrors `runner._group_alive`: a zombie not yet reaped answers `0` with `EPERM` on
    Darwin, `ESRCH` once reaped — either one means there is nothing left to signal."""
    try:
        os.killpg(pgid, 0)
    except OSError:
        return False
    return True
