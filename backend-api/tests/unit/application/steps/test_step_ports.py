"""`StepPorts` lives in `step_ports.py` and is still importable from `context.py`."""

from __future__ import annotations

from orchestrator.application.steps import step_ports
from orchestrator.application.steps.context import StepPorts
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit


def test_both_imports_are_one_class() -> None:
    assert step_ports.StepPorts is StepPorts


def test_step_log_defaults_to_none() -> None:
    ports = StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work")

    assert ports.step_log is None
