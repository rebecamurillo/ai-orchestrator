"""`open_advance_ports` hands the git adapter over as the remote-branch port (epic 8 story 3)."""

from __future__ import annotations

from orchestrator.infrastructure.dbos.advance_ports import open_advance_ports
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.remote_branches import FakeRemoteGit
from tests.unit.test_dbos_advance_ports import Factory


def test_the_ports_carry_the_git_adapter_as_the_branch_port(env: dict[str, str]) -> None:
    git = FakeRemoteGit()

    with open_advance_ports(Factory(), Settings(), git, [FakeWorkflowEngine()]) as ports:  # type: ignore[arg-type]
        assert ports.branches is git
