"""`open_initiative_ports` and `create_run_ports` (epic 9 story 3)."""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.dbos import advance_ports
from orchestrator.infrastructure.dbos.advance_ports import open_advance_ports
from orchestrator.infrastructure.dbos.initiative_ports import open_initiative_ports
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.test_dbos_advance_ports import Factory


def test_one_session_holds_the_repositories_and_closes_after_the_block(
    env: dict[str, str],
) -> None:
    factory = Factory()
    engine = FakeWorkflowEngine()

    with open_initiative_ports(factory, Settings(), FakeGit(), engine) as ports:  # type: ignore[arg-type]
        assert ports.create_run.uow is ports.uow
        assert ports.create_run.engine is engine
        assert ports.signals.signal.engine is engine
        assert ports.work_dir == Settings().work_dir
        assert factory.sessions[0].closed == 0

    assert all(session.closed == 1 for session in factory.sessions)


def test_the_sessions_are_closed_when_the_block_raises(env: dict[str, str]) -> None:
    factory = Factory()

    with (
        pytest.raises(RuntimeError, match="boom"),
        open_initiative_ports(factory, Settings(), FakeGit(), FakeWorkflowEngine()),  # type: ignore[arg-type]
    ):
        raise RuntimeError("boom")

    assert factory.sessions
    assert all(session.closed == 1 for session in factory.sessions)


def test_the_advance_ports_build_their_create_run_through_the_shared_function(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[object] = []
    real = advance_ports.create_run_ports

    def spy(*args: object) -> object:
        seen.append(args[1])
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(advance_ports, "create_run_ports", spy)

    with open_advance_ports(Factory(), Settings(), FakeGit(), [FakeWorkflowEngine()]) as ports:  # type: ignore[arg-type]
        assert seen == [ports.uow]
