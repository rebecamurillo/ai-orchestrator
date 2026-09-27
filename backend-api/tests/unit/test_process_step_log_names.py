"""The kinds that start a process name the file that process wrote.

Revised 2026-09-27 (Operator decision: `install_command` is a declared template row, not a
`git.worktree` side effect): the `git.worktree` section is gone with the process it ran —
the install now goes through the `shell` rows asserted below — and
`test_git_worktree_executor.py` pins that the kind starts no process at all.

A row whose command fails is the one row an Operator most needs to read, and the only thing
that can tell them why is the file `ProcessRunner.start` appended stdout and stderr into.
The spine's field list puts `log_path` on `attempt` — "one per execution of *any* row" — and
`run_views._latest_attempt` builds `latest.log_tail` from exactly that column, so a kind that
writes a log without naming it leaves the Run detail showing an empty tail beside its own
failure. `output_ref` cannot stand in: `git.commit` puts a sha there and `pr.link` a URL, so
nothing downstream may read it as a path.

This module asserts the naming only — what `apply_step_result` does with the name is
`tests/unit/application/test_attempt_log_path.py`'s.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.steps.bmad_install import KIND as BMAD_KIND
from orchestrator.application.steps.bmad_install import BmadInstallExecutor
from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.shell import KIND as SHELL_KIND
from orchestrator.application.steps.shell import ShellExecutor
from orchestrator.domain.ports.process import Outcome
from orchestrator.domain.values import StepResult
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.workspace import FakeWorkspace
from tests.unit.step_fixtures import (
    BMAD_VERSION,
    a_context,
    a_row,
    an_environment,
)

#: The two ways a command can end badly, and the one way it ends well.
NOT_FOUND = Outcome(exit_code=127, timed_out=False)
CLEAN = Outcome(exit_code=0, timed_out=False)
KILLED = Outcome(exit_code=None, timed_out=True)

#: The verify command a `shell` row runs, and the exit that sends the Run back.
VERIFY = "make test"
FAILED = Outcome(exit_code=1, timed_out=False)


def a_bmad_context(outcome: Outcome) -> StepContext:
    """A `bmad.install` row, whose command the executor builds from the pinned version."""
    row = a_row(kind=BMAD_KIND, with_resolved={"timeout_min": 30}, path="install")
    return a_context(
        row,
        env=an_environment(bmad_version=BMAD_VERSION),
        process=FakeProcessRunner(default=outcome),
        workspace=FakeWorkspace(),
    )


def a_shell_context(outcome: Outcome, **resolved: object) -> StepContext:
    """A `shell` row — the kind `verify` is planned as."""
    row = a_row(
        kind=SHELL_KIND,
        with_resolved={"command": VERIFY, "timeout_min": 30, **resolved},
        path="verify",
    )
    return a_context(row, process=FakeProcessRunner(outcomes={VERIFY: outcome}))


def the_log_of(ctx: StepContext) -> str:
    """The path `log_path` computes for this row — what the runner was handed."""
    return str(log_path(ctx))


def started_with(ctx: StepContext) -> Path:
    """The `log_path` the executor actually handed `ProcessRunner.start`."""
    process = ctx.ports.process
    assert isinstance(process, FakeProcessRunner)
    started = process.called("start")
    assert started, "the executor started no process"
    path = started[0]["log_path"]
    assert isinstance(path, Path)
    return path


def assert_names_its_log(result: StepResult, ctx: StepContext) -> None:
    """The result names the same file the runner was told to append into."""
    assert result.log_path == the_log_of(ctx)
    assert result.log_path == str(started_with(ctx))


# ── bmad.install ────────────────────────────────────────────────────────────


def test_a_failed_bmad_install_names_the_log_it_wrote() -> None:
    ctx = a_bmad_context(NOT_FOUND)

    result = BmadInstallExecutor().execute(ctx)

    assert result.status == "error"
    assert_names_its_log(result, ctx)


def test_a_bmad_install_that_worked_names_its_log_too() -> None:
    ctx = a_bmad_context(CLEAN)

    result = BmadInstallExecutor().execute(ctx)

    assert result.status == "done"
    assert_names_its_log(result, ctx)


# ── shell: every route a non-zero exit can take ─────────────────────────────


def test_a_shell_row_that_worked_names_its_log() -> None:
    ctx = a_shell_context(CLEAN)

    result = ShellExecutor().execute(ctx)

    assert result.status == "done"
    assert_names_its_log(result, ctx)


def test_a_timed_out_shell_row_names_its_log() -> None:
    ctx = a_shell_context(KILLED)

    result = ShellExecutor().execute(ctx)

    assert result.status == "error"
    assert_names_its_log(result, ctx)


def test_an_escalating_shell_row_names_its_log() -> None:
    """The `verify` row's own default: it parks the Run, and the tail is the evidence."""
    ctx = a_shell_context(FAILED)

    result = ShellExecutor().execute(ctx)

    assert result.park is not None
    assert_names_its_log(result, ctx)


def test_a_failing_shell_row_names_its_log() -> None:
    ctx = a_shell_context(FAILED, on_fail="fail")

    result = ShellExecutor().execute(ctx)

    assert result.status == "error"
    assert_names_its_log(result, ctx)


def test_a_continuing_shell_row_names_its_log() -> None:
    ctx = a_shell_context(FAILED, on_fail="continue")

    result = ShellExecutor().execute(ctx)

    assert result.status == "done"
    assert_names_its_log(result, ctx)


def test_a_redispatching_shell_row_names_its_log() -> None:
    """`walk._verify_failure` reads this attempt's `log_path` back to build the tail the
    story's next attempt is told about — the one place the column is already read."""
    ctx = a_shell_context(FAILED, on_fail={"target_seq": 3, "max": 2})

    result = ShellExecutor().execute(ctx)

    assert result.redispatch is not None
    assert_names_its_log(result, ctx)
