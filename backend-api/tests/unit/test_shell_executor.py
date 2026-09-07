"""`application/steps/shell.py`: the `shell` kind's whole behaviour (AD-9, AD-14, FR-10).

Every scenario the story's own acceptance criteria name, run over `FakeProcessRunner`
rather than a real one — `tests/unit/test_process_runner.py` is what proves the real
adapter keeps the contract this module is written against.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps.context import StepContext, StepExecutor, StepPorts
from orchestrator.application.steps.shell import NO_RUNNER, ShellExecutor
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.process import Outcome
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

WORK_DIR = "/work"
COMMAND = "./quality-gate.sh"
TIMEOUT_MIN = 30
TARGET_SEQ = 2


def a_row(*, with_resolved: dict[str, object], seq: int = 5) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=seq,
        path="baseline",
        label="baseline",
        kind="shell",
        gate="deterministic",
        status="running",
        with_resolved=with_resolved,
    )


def a_context(
    row: StepRun, *, process: FakeProcessRunner | None, cwd: str | None = "/wt"
) -> StepContext:
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=cwd,
        frame_start_sha=None,
        previous_attempt=None,
        attempt=Attempt(id=new_id(), run_id=row.run_id, step_run_id=row.id, n=2, status="running"),
        resume_signal=None,
        ports=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR, process=process),
    )


def test_the_executor_satisfies_the_protocol() -> None:
    assert isinstance(ShellExecutor(), StepExecutor)


def test_a_clean_exit_is_done_with_the_log_as_output_ref() -> None:
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 30})
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=0, timed_out=False)})

    result = ShellExecutor().execute(a_context(row, process=runner))

    assert result.status == "done"
    assert result.gate == "deterministic"
    assert result.park is None
    assert result.output_ref is not None
    assert str(row.run_id) in result.output_ref
    assert f"{row.seq:03d}-2.log" in result.output_ref


def test_the_command_and_cwd_reach_the_runner_verbatim() -> None:
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 30})
    runner = FakeProcessRunner()

    ShellExecutor().execute(a_context(row, process=runner, cwd="/work/wt/main"))

    [call] = runner.called("start")
    assert call["cmd"] == COMMAND
    assert str(call["cwd"]) == "/work/wt/main"
    assert call["timeout_min"] == TIMEOUT_MIN


def test_a_row_with_no_worktree_yet_passes_no_cwd() -> None:
    """A `shell` row with no `git.worktree` before it: `ctx.cwd` is `None` (4.8)."""
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 30})
    runner = FakeProcessRunner()

    ShellExecutor().execute(a_context(row, process=runner, cwd=None))

    [call] = runner.called("start")
    assert call["cwd"] is None


def test_a_timeout_parks_timeout_with_the_row_and_the_minutes_in_the_reason() -> None:
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 5})
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=None, timed_out=True)})

    result = ShellExecutor().execute(a_context(row, process=runner))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "timeout"
    assert result.park.reason == "timeout baseline after 5 min"
    assert result.reason == "timeout baseline after 5 min"


def test_on_fail_escalate_by_default_parks_verify_failed() -> None:
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 30})
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=2, timed_out=False)})

    result = ShellExecutor().execute(a_context(row, process=runner))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "verify_failed"
    assert result.park.reason == "baseline exit 2"
    assert result.reason == "baseline exit 2"


def test_on_fail_escalate_named_explicitly_is_the_same_as_absent() -> None:
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 30, "on_fail": "escalate"})
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=2, timed_out=False)})

    result = ShellExecutor().execute(a_context(row, process=runner))

    assert result.park is not None
    assert result.park.kind == "verify_failed"


def test_on_fail_fail_is_an_error_with_no_park() -> None:
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 30, "on_fail": "fail"})
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=2, timed_out=False)})

    result = ShellExecutor().execute(a_context(row, process=runner))

    assert result.status == "error"
    assert result.park is None
    assert result.reason == "baseline exit 2"


def test_on_fail_continue_is_done_with_the_exit_code_in_the_reason() -> None:
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 30, "on_fail": "continue"})
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=2, timed_out=False)})

    result = ShellExecutor().execute(a_context(row, process=runner))

    assert result.status == "done"
    assert result.park is None
    assert result.reason == "exit 2 (continued)"


def test_on_fail_redispatch_carries_the_planners_resolved_target() -> None:
    row = a_row(
        with_resolved={
            "command": COMMAND,
            "timeout_min": 30,
            "on_fail": {"target_seq": TARGET_SEQ, "max": 1},
        }
    )
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=2, timed_out=False)})

    result = ShellExecutor().execute(a_context(row, process=runner))

    assert result.status == "error"
    assert result.park is None
    assert result.reason == "exit 2"
    assert result.redispatch is not None
    assert result.redispatch.target_seq == TARGET_SEQ
    assert result.redispatch.max == 1


def test_with_no_process_runner_wired_the_executor_refuses_rather_than_hangs() -> None:
    row = a_row(with_resolved={"command": COMMAND, "timeout_min": 30})

    with pytest.raises(RuntimeError, match=NO_RUNNER):
        ShellExecutor().execute(a_context(row, process=None))
