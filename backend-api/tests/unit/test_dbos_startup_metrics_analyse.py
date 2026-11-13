"""Start-up wires the `metrics.analyse` kind, its analysis port and the scratch sweep (epic 5
story 4)."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.application.steps.metrics_analyse import KIND, MetricsAnalyseExecutor
from orchestrator.application.steps.registry import EXECUTORS
from orchestrator.infrastructure.analysis.wiring import build_analysis
from orchestrator.infrastructure.dbos import startup
from orchestrator.infrastructure.dbos.startup import launch_engine, serving, walker_deps
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


def test_importing_startup_registers_the_kind() -> None:
    assert isinstance(EXECUTORS[KIND], MetricsAnalyseExecutor)


def test_the_walker_and_the_calculation_are_handed_the_analysis(env: dict[str, str]) -> None:
    deps = walker_deps(Settings(), sessions(), FakeGit())

    assert deps.step_ports.analysis is not None
    assert isinstance(deps.calculation_writes, partial)
    assert callable(deps.calculation_writes.keywords["analysis"])


def test_the_two_forms_are_built_without_opening_a_session(env: dict[str, str]) -> None:
    pending, calculating = build_analysis(Settings(), sessions(), FakeGit(), FakeProcessRunner())

    assert callable(pending)
    assert callable(calculating)


class Engine:
    def __init__(self, events: list[str], work_dir: str) -> None:
        self.events = events
        self.walker_deps = SimpleNamespace(step_ports=SimpleNamespace(work_dir=work_dir))

    def launch(self) -> None:
        self.events.append("launch")


def test_the_scratch_is_swept_once_before_the_engine_launches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        startup, "sweep_analysis_scratch", lambda work_dir: events.append(f"sweep {work_dir}")
    )

    with serving(Engine(events, str(tmp_path))):  # type: ignore[arg-type]
        launch_engine()

    assert events == [f"sweep {tmp_path}", "launch"]
