"""`Harness.start_resume` (story 2-5, AD-10 and AD-14 as amended 2026-11-02): a resumed
process hands its group back before anything waits on it, so a session turn records its
`pgid` first. `resume` is exactly `wait(start_resume(...))`, with the argv unchanged."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from orchestrator.domain.ports.harness import Harness
from orchestrator.infrastructure.harness import ClaudeHarness
from orchestrator.infrastructure.harness.codex.adapter import CodexHarness
from orchestrator.infrastructure.harness.opencode.adapter import LocalHarness
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.harness import DEFAULT_PGID, FakeHarness
from tests.unit.fakes.process import FakeProcessRunner

SESSION_ID = "s-7f3c"
WORKTREE = Path("/work/acme/widgets/wt/feat-x")
FIRST_GROUP = 1

Build = Callable[[FakeProcessRunner, Settings], Any]
ADAPTERS: list[Build] = [ClaudeHarness, CodexHarness, LocalHarness]


@pytest.fixture
def settings(env: dict[str, str], tmp_path: Path) -> Settings:
    return Settings(agent_home=tmp_path / "agent")


def kwargs(log_path: Path) -> dict[str, Any]:
    return {
        "cwd": WORKTREE,
        "session_id": SESSION_ID,
        "message": "And the v1 route?",
        "env": {"ORCH_RUN_ID": "r-1"},
        "timeout_min": None,
        "log_path": log_path,
        "stall_min": 30,
        "model": "m-1",
        "budget_usd_remaining": Decimal("4.5"),
        "add_dirs": (Path("/work/hub"),),
    }


def test_the_port_declares_start_resume_beside_resume() -> None:
    assert "start_resume" in Harness.__protocol_attrs__


@pytest.mark.parametrize("build", ADAPTERS, ids=lambda b: b.__name__)
def test_start_resume_starts_the_process_and_waits_for_nothing(
    build: Build, settings: Settings, tmp_path: Path
) -> None:
    runner = FakeProcessRunner()
    harness = build(runner, settings)

    handle = harness.start_resume(**kwargs(tmp_path / "a.log"))

    assert [call["method"] for call in runner.calls] == ["start"]
    assert (handle.pid, handle.pgid) == (FIRST_GROUP, FIRST_GROUP)
    assert handle.session_id == SESSION_ID
    assert handle.log_path == tmp_path / "a.log"
    assert Path(f"{tmp_path / 'a.log'}.prompt").read_text() == "And the v1 route?"
    assert isinstance(harness, Harness)


@pytest.mark.parametrize("build", ADAPTERS, ids=lambda b: b.__name__)
def test_resume_is_start_resume_then_wait_with_the_same_argv(
    build: Build, settings: Settings, tmp_path: Path
) -> None:
    split, whole = FakeProcessRunner(), FakeProcessRunner()
    halves = build(split, settings)
    single = build(whole, settings)

    waited = halves.wait(halves.start_resume(**kwargs(tmp_path / "a.log")))
    resumed = single.resume(**kwargs(tmp_path / "b.log"))

    assert split.called("start")[0]["cmd"] == whole.called("start")[0]["cmd"]
    assert [call["method"] for call in whole.calls] == ["start", "wait"]
    assert (waited.session_id, waited.exit_code) == (resumed.session_id, resumed.exit_code)
    assert waited.pgid == resumed.pgid == FIRST_GROUP


def test_the_fake_records_start_resume_and_hands_back_its_group() -> None:
    harness = FakeHarness()

    handle = harness.start_resume(**kwargs(Path("/work/logs/a.log")))
    result = harness.wait(handle)

    (call,) = harness.called("start_resume")
    assert (call["session_id"], call["message"], call["model"]) == (
        SESSION_ID,
        "And the v1 route?",
        "m-1",
    )
    assert call["add_dirs"] == (Path("/work/hub"),)
    assert (handle.pgid, result.session_id) == (DEFAULT_PGID, SESSION_ID)
    assert [entry["method"] for entry in harness.calls] == ["start_resume", "wait"]
