"""`open_advance_ports` wires the step and attempt repositories (epic 8 story 2)."""

from __future__ import annotations

from orchestrator.infrastructure.dbos.advance_ports import open_advance_ports
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.test_dbos_advance_ports import Factory


def test_the_ports_carry_steps_and_attempts(env: dict[str, str]) -> None:
    with open_advance_ports(Factory(), Settings(), FakeGit(), [FakeWorkflowEngine()]) as ports:  # type: ignore[arg-type]
        assert ports.steps is not None
        assert ports.attempts is not None
