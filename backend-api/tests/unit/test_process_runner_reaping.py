"""`kill_group` reaps its own child before it believes the group is gone (AD-14, AD-13).

`tests/unit/test_process_runner.py` is this adapter's acceptance suite. This file covers
the one thing that suite can only observe indirectly, and that a Mac cannot observe at all:
a child that has exited but has not been collected is a zombie, a zombie is still a member
of its process group, and on Linux `os.killpg(pgid, 0)` therefore answers *successfully*
for a group that is already dead. Darwin answers `EPERM` there, so every local gate read
"gone" while CI read "alive" — and in a container `kill_group` waited out the whole of
`GRACE_SECONDS` on every kill before `SIGKILL`ing a corpse.

Only the process that forked a child may reap it, so these are tests about the runner
doing that: prompt kills cost a poll rather than the grace, whichever `RealProcessRunner`
is asked — the walker's, built at start-up, or `cancel`'s, built per request — and the
exit code is still there for a later `wait` to report.
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

import pytest

from orchestrator.infrastructure.process import runner as runner_module
from orchestrator.infrastructure.process.runner import GRACE_SECONDS, RealProcessRunner

#: A group that leaves the moment it is asked must cost a poll or two. Half the grace is a
#: ceiling the defect could never have slipped under and the fix never approaches.
PROMPT_KILL_CEILING_SECONDS = GRACE_SECONDS / 2
#: The grace the `SIGKILL` scenario runs under, so it reaches the escalation in under a
#: second instead of spending ten to prove the same thing.
SHORT_GRACE_SECONDS = 0.5
#: What that scenario is then allowed to take, end to end.
SHORT_KILL_CEILING_SECONDS = 5.0
#: How long a started command is given to announce itself before a test gives up on it.
READY_DEADLINE_SECONDS = 10.0
#: What such a command echoes once it is in the state the test needs it to be in.
READY = "ready"


def test_kill_group_reaps_the_child_it_started_and_the_group_really_goes(tmp_path: Path) -> None:
    """The defect, stated positively: after `kill_group` there is no zombie left holding
    the group open, so the group answers `ESRCH` on Linux as it always did on Darwin."""
    runner = RealProcessRunner()
    handle = runner.start(
        ["sleep", "30"], cwd=None, env={}, timeout_min=5.0, log_path=tmp_path / "a.log"
    )

    runner.kill_group(handle.pgid)

    assert _reaped(handle.pid)
    with pytest.raises(ProcessLookupError):
        os.killpg(handle.pgid, 0)


def test_kill_group_on_a_group_that_leaves_at_once_costs_a_poll_not_the_grace(
    tmp_path: Path,
) -> None:
    """The production consequence: every timeout kill and every `cancel` in a container
    was ten seconds slower than designed, because the corpse still answered the probe."""
    runner = RealProcessRunner()
    handle = runner.start(
        ["sleep", "30"], cwd=None, env={}, timeout_min=5.0, log_path=tmp_path / "b.log"
    )

    start = time.monotonic()
    runner.kill_group(handle.pgid)
    elapsed = time.monotonic() - start

    assert elapsed < PROMPT_KILL_CEILING_SECONDS
    runner.wait(handle)


def test_a_second_runner_kills_a_group_the_first_one_started_just_as_promptly(
    tmp_path: Path,
) -> None:
    """The `cancel` shape (4.9): `api/providers.py` builds its own `RealProcessRunner` per
    request, and the child belongs to the walker's. Reaping is the process's, not the
    object's, so the canceller reaps it too."""
    walker_runner = RealProcessRunner()
    handle = walker_runner.start(
        ["sleep", "30"], cwd=None, env={}, timeout_min=5.0, log_path=tmp_path / "c.log"
    )

    start = time.monotonic()
    RealProcessRunner().kill_group(handle.pgid)
    elapsed = time.monotonic() - start

    assert elapsed < PROMPT_KILL_CEILING_SECONDS
    assert _reaped(handle.pid)
    walker_runner.wait(handle)


def test_a_kill_leaves_the_exit_code_for_the_wait_that_follows_it(tmp_path: Path) -> None:
    """Reaping is not forgetting: the walker is blocked in `wait` while `cancel` kills, and
    it must still report what the process left rather than the `None` of an unknown handle."""
    runner = RealProcessRunner()
    handle = runner.start(
        ["sleep", "30"], cwd=None, env={}, timeout_min=5.0, log_path=tmp_path / "d.log"
    )

    RealProcessRunner().kill_group(handle.pgid)
    outcome = runner.wait(handle)

    assert outcome.exit_code == -signal.SIGTERM
    assert outcome.timed_out is False


def test_a_group_that_ignores_sigterm_is_killed_and_reaped_by_kill_group_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cancel` is a `kill_group` with no `wait` behind it, so the escalation reaps too —
    otherwise the corpse would keep the group alive and the next kill would pay the grace
    all over again. The grace is shortened here; the sequence under test is not."""
    monkeypatch.setattr(runner_module, "GRACE_SECONDS", SHORT_GRACE_SECONDS)
    runner = RealProcessRunner()
    log_path = tmp_path / "e.log"
    handle = runner.start(
        ["bash", "-c", f"trap '' TERM; echo {READY}; sleep 30"],
        cwd=None,
        env={},
        timeout_min=5.0,
        log_path=log_path,
    )
    _await_ready(log_path)

    start = time.monotonic()
    runner.kill_group(handle.pgid)
    elapsed = time.monotonic() - start

    # at least the grace, because `SIGTERM` alone could not have ended it, and not much
    # more, because the reap that follows `SIGKILL` is the kernel's own latency
    assert SHORT_GRACE_SECONDS <= elapsed < SHORT_KILL_CEILING_SECONDS
    assert _reaped(handle.pid)
    runner.wait(handle)


def test_killing_a_group_this_process_already_waited_on_is_a_prompt_no_op(
    tmp_path: Path,
) -> None:
    """The post-restart shape, reached the short way: a `pgid` whose child this runner no
    longer holds must not stall — it has nothing to reap and nothing to signal."""
    runner = RealProcessRunner()
    handle = runner.start(["true"], cwd=None, env={}, timeout_min=5.0, log_path=tmp_path / "f.log")
    runner.wait(handle)

    start = time.monotonic()
    runner.kill_group(handle.pgid)
    elapsed = time.monotonic() - start

    assert elapsed < PROMPT_KILL_CEILING_SECONDS


def test_a_group_whose_child_this_process_no_longer_holds_is_still_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The post-restart shape at full size: the group is running and nothing here holds its
    `Popen`, which is what `cancel` meets when the backend restarted while a step was
    running (4.9). Only the process that forked a child may reap it, so this is the one
    case with nothing to collect — and it must still end the group rather than stall."""
    runner = RealProcessRunner()
    handle = runner.start(
        ["sleep", "30"], cwd=None, env={}, timeout_min=5.0, log_path=tmp_path / "g.log"
    )
    monkeypatch.setattr(runner_module, "GRACE_SECONDS", SHORT_GRACE_SECONDS)
    monkeypatch.setattr(runner_module, "_CHILDREN", {})

    start = time.monotonic()
    runner.kill_group(handle.pgid)
    elapsed = time.monotonic() - start

    assert elapsed < SHORT_KILL_CEILING_SECONDS
    monkeypatch.undo()  # the registry the walker still holds, so the child is reaped here
    outcome = runner.wait(handle)
    assert outcome.exit_code in (-signal.SIGTERM, -signal.SIGKILL)


def _await_ready(log_path: Path) -> None:
    """Block until the started command has said it reached the state under test.

    A command's `trap` is installed some moment *after* `start` returns, and a `SIGTERM`
    that arrives first is handled by the default disposition — which would make the
    scenario below pass for the wrong reason. Reading the command's own log is how the
    test learns the state is real, rather than sleeping and hoping.
    """
    deadline = time.monotonic() + READY_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if log_path.exists() and READY in log_path.read_text():
            return
        time.sleep(0.02)
    raise AssertionError(f"the command never wrote {READY!r} to {log_path}")


def _reaped(pid: int) -> bool:
    """Whether this process has collected `pid`, asked of the operating system directly.

    `waitpid(WNOHANG)` returns an unreaped zombie and `(0, 0)` for one still running;
    `ECHILD` — `ChildProcessError` — is the answer only a reaped child gives.
    """
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return True
    return False
