"""`open_advance_ports`: one session's worth of `AdvancePorts` for the advance workflow
(epic 8 story 1)."""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.dbos.advance_ports import open_advance_ports
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit


class Session:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class Factory:
    def __init__(self) -> None:
        self.sessions: list[Session] = []

    def __call__(self) -> Session:
        self.sessions.append(Session())
        return self.sessions[-1]


def test_one_session_is_opened_and_closed_after_the_block(env: dict[str, str]) -> None:
    factory = Factory()

    with open_advance_ports(factory, Settings(), FakeGit(), [FakeWorkflowEngine()]) as ports:  # type: ignore[arg-type]
        assert len(factory.sessions) == 1
        assert factory.sessions[0].closed == 0
        assert ports.create_run.uow is ports.uow

    assert factory.sessions[0].closed == 1


def test_the_session_is_closed_when_the_block_raises(env: dict[str, str]) -> None:
    factory = Factory()

    with (
        pytest.raises(RuntimeError, match="boom"),
        open_advance_ports(factory, Settings(), FakeGit(), [FakeWorkflowEngine()]),  # type: ignore[arg-type]
    ):
        raise RuntimeError("boom")

    assert factory.sessions[0].closed == 1


def test_the_create_run_ports_hold_the_engine_and_the_initiative_runs(env: dict[str, str]) -> None:
    engine = FakeWorkflowEngine()

    with open_advance_ports(Factory(), Settings(), FakeGit(), [engine]) as ports:  # type: ignore[arg-type]
        assert ports.create_run.engine is engine
        assert ports.create_run.initiative_runs is not None


def test_redact_replaces_a_settings_secret(env: dict[str, str]) -> None:
    settings = Settings()
    secret = settings.orchestrator_token.get_secret_value()

    with open_advance_ports(Factory(), settings, FakeGit(), [FakeWorkflowEngine()]) as ports:  # type: ignore[arg-type]
        assert ports.redact(f"leaked {secret} here") == "leaked *** here"
        assert ports.redact("nothing") == "nothing"


def test_an_engine_not_yet_built_is_refused(env: dict[str, str]) -> None:
    factory = Factory()

    with (
        pytest.raises(RuntimeError, match="engine"),
        open_advance_ports(factory, Settings(), FakeGit(), []),  # type: ignore[arg-type]
    ):
        pass

    assert factory.sessions == [] or factory.sessions[0].closed == 1
