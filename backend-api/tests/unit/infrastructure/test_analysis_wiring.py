"""`build_analysis` hands Tier 2 a runner, the timeout and the Project env (epic 6 story 1)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

from orchestrator.application.analysis import run_analysis
from orchestrator.infrastructure.analysis import wiring
from orchestrator.infrastructure.settings import Settings

TIMEOUT = 5


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: the reader is replaced
        raise AssertionError("no session is opened")

    return factory


def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_analyse(deps: Any, writes: Any, run_id: UUID, calculation_id: Any) -> tuple[()]:
        seen["deps"] = deps
        return ()

    monkeypatch.setattr(wiring, "analyse_run", fake_analyse)
    return seen


def test_the_deps_carry_the_runner_the_timeout_and_the_project_env(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANALYSIS_COMMAND_TIMEOUT_MIN", str(TIMEOUT))
    runner = FakeProcessRunner()
    asked: list[tuple[Any, ...]] = []

    def read(factory: Any, bmad: str, run_id: UUID, *, crypto: Any) -> Any:
        asked.append((bmad, run_id, callable(crypto)))
        return SimpleNamespace(project=SimpleNamespace(env_vars={"NODE_ENV": "test"}))

    monkeypatch.setattr(wiring, "read_run_environment", read)
    seen = captured(monkeypatch)
    pending, _ = wiring.build_analysis(Settings(), sessions(), FakeGit(), runner)
    pending(UUID(int=7))
    deps: run_analysis.AnalysisDeps = seen["deps"]
    assert deps.runner is runner
    assert deps.command_timeout_min == TIMEOUT
    assert deps.project_env(UUID(int=7)) == {"NODE_ENV": "test"}
    assert asked == [(Settings().bmad_version, UUID(int=7), True)]


def test_an_unknown_run_has_no_project_env(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wiring, "read_run_environment", lambda *a, **k: None)
    seen = captured(monkeypatch)
    _, calculating = wiring.build_analysis(Settings(), sessions(), FakeGit(), FakeProcessRunner())
    calculating(UUID(int=7), UUID(int=8))
    assert seen["deps"].project_env(UUID(int=7)) == {}
