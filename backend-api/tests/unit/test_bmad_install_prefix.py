"""`bmad.install` prefers the image's `/opt/bmad` installer, else `npx` (AD-16 amended)."""

from __future__ import annotations

from orchestrator.application.steps.bmad_install import KIND, BmadInstallExecutor
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.step_fixtures import WORKTREE, a_context, a_row, an_environment

BIN = "/opt/bmad/bin/bmad-method"
TAIL = [
    "install",
    "--yes",
    "--modules",
    "bmm",
    "--tools",
    "claude-code,codex,opencode",
    "--directory",
    WORKTREE,
]


def _argv(runner: FakeProcessRunner) -> list[str]:
    [call] = runner.called("start")
    return list(call["cmd"])


def test_a_known_bmad_bin_is_the_executable_with_the_same_arguments() -> None:
    runner = FakeProcessRunner()
    row = a_row(kind=KIND, with_resolved={"timeout_min": 30}, path="install")

    BmadInstallExecutor().execute(a_context(row, process=runner, env=an_environment(bmad_bin=BIN)))

    assert _argv(runner) == [BIN, *TAIL]


def test_no_bmad_bin_falls_back_to_npx_with_the_pinned_version() -> None:
    runner = FakeProcessRunner()
    row = a_row(kind=KIND, with_resolved={"timeout_min": 30}, path="install")

    BmadInstallExecutor().execute(a_context(row, process=runner, env=an_environment()))

    assert _argv(runner) == ["npx", "--yes", "bmad-method@6.11.0", *TAIL]
