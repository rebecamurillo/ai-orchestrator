"""`application/steps/bmad_install.py`: the method into a target repository (AD-16, FR-30).

The command is asserted as an argv rather than as a string, because that is what it is: a
repository directory with a space in it must not become two arguments. The `.gitignore` half
is asserted through the `Workspace` fake, in both directions — the two lines appended when
they are missing, and nothing rewritten when they are already there.
"""

from __future__ import annotations

import pytest

from orchestrator.application.steps.bmad_install import (
    ALREADY_IGNORED,
    GITIGNORE,
    IGNORED,
    INSTALL_FAILED,
    KIND,
    TIMED_OUT,
    BmadInstallExecutor,
)
from orchestrator.application.steps.context import (
    NO_ENVIRONMENT,
    NO_RUNNER,
    NO_WORKTREE,
    StepExecutor,
)
from orchestrator.application.steps.registry import executor_for
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.process import Outcome
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.workspace import FakeWorkspace
from tests.unit.step_fixtures import (
    BMAD_VERSION,
    WORKTREE,
    a_context,
    a_row,
    without,
)

EXPECTED = [
    "npx",
    "--yes",
    f"bmad-method@{BMAD_VERSION}",
    "install",
    "--yes",
    "--modules",
    "bmm",
    "--tools",
    "claude-code,codex,opencode",
    "--directory",
    WORKTREE,
]
COMMAND = " ".join(EXPECTED)


def an_install_row() -> StepRun:
    return a_row(kind=KIND, with_resolved={"timeout_min": 30}, path="install")


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(BmadInstallExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), BmadInstallExecutor)


def test_the_pinned_version_and_all_three_tool_folders_reach_npx_as_one_argv() -> None:
    runner = FakeProcessRunner()

    result = BmadInstallExecutor().execute(a_context(an_install_row(), process=runner))

    [call] = runner.called("start")
    assert call["cmd"] == EXPECTED
    assert str(call["cwd"]) == WORKTREE
    assert call["timeout_min"] == 30  # noqa: PLR2004 — the Template's own declared value
    assert call["env"] == {}
    assert result.status == "done"
    assert result.output_ref == str(call["log_path"])


def test_a_row_with_no_resolved_timeout_falls_back_to_the_kinds_own() -> None:
    runner = FakeProcessRunner()
    row = a_row(kind=KIND, with_resolved={}, path="install")

    BmadInstallExecutor().execute(a_context(row, process=runner))

    assert runner.called("start")[0]["timeout_min"] == 30  # noqa: PLR2004 — the kind's default


def test_the_two_skill_folders_are_ignored_so_the_next_commit_never_sees_them() -> None:
    workspace = FakeWorkspace()

    BmadInstallExecutor().execute(
        a_context(an_install_row(), process=FakeProcessRunner(), workspace=workspace)
    )

    assert workspace.read(GITIGNORE) == "\n".join(IGNORED) + "\n"


def test_an_existing_gitignore_keeps_what_it_already_ignored() -> None:
    workspace = FakeWorkspace(files={GITIGNORE: ".venv/\nnode_modules/\n"})

    BmadInstallExecutor().execute(
        a_context(an_install_row(), process=FakeProcessRunner(), workspace=workspace)
    )

    assert workspace.read(GITIGNORE) == "\n".join([".venv/", "node_modules/", *IGNORED]) + "\n"


def test_running_the_row_twice_adds_the_lines_once() -> None:
    workspace = FakeWorkspace(files={GITIGNORE: "\n".join(IGNORED) + "\n"})

    result = BmadInstallExecutor().execute(
        a_context(an_install_row(), process=FakeProcessRunner(), workspace=workspace)
    )

    assert workspace.read(GITIGNORE) == "\n".join(IGNORED) + "\n"
    assert result.reason == ALREADY_IGNORED


def test_a_failing_install_parks_misconfigured_with_the_exit_code() -> None:
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=7, timed_out=False)})

    result = BmadInstallExecutor().execute(a_context(an_install_row(), process=runner))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == INSTALL_FAILED.format(code=7)


def test_an_install_the_runner_killed_parks_timeout() -> None:
    runner = FakeProcessRunner(outcomes={COMMAND: Outcome(exit_code=None, timed_out=True)})

    result = BmadInstallExecutor().execute(a_context(an_install_row(), process=runner))

    assert result.park is not None
    assert result.park.kind == "timeout"
    assert result.park.reason == TIMED_OUT.format(path="install", n=30)


def test_a_row_reached_before_any_worktree_exists_refuses() -> None:
    context = a_context(an_install_row(), process=FakeProcessRunner(), cwd=None)

    with pytest.raises(RuntimeError, match=NO_WORKTREE.format(path="install")):
        BmadInstallExecutor().execute(context)


def test_without_a_process_runner_the_executor_refuses_rather_than_hangs() -> None:
    with pytest.raises(RuntimeError, match=NO_RUNNER):
        BmadInstallExecutor().execute(a_context(an_install_row(), process=None))


def test_without_an_environment_the_executor_refuses() -> None:
    context = without(a_context(an_install_row(), process=FakeProcessRunner()), run_env=None)

    with pytest.raises(RuntimeError, match=NO_ENVIRONMENT):
        BmadInstallExecutor().execute(context)
