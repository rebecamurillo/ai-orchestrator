"""`infrastructure/db/writers.py::open_spend_ports` (5.7): one session's worth of
`SpendPorts`, the same shape `test_writer_ports_scope.py` (frozen) proves for
`open_writer_ports` — its own scope because `attempt_writes`'s `WriterPorts` may reach only
`.attempts` (AD-8), and the budget read needs `runs`/`steps` too.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.domain.ports.gateway import AttemptSpend
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.infrastructure.db.writers import open_spend_ports


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


class RecordingFactory:
    def __init__(self) -> None:
        self.sessions: list[RecordingSession] = []

    def __call__(self) -> Any:
        session = RecordingSession()
        self.sessions.append(session)
        return session


class StubGateway:
    def spend_for_attempt(self, run_id: UUID, attempt_id: UUID) -> AttemptSpend:
        return AttemptSpend(
            usd=Decimal("0"), tokens_in=0, tokens_out=0, by_model=(), calls=0, provisional=True
        )


@pytest.fixture
def factory() -> RecordingFactory:
    return RecordingFactory()


def test_the_scope_yields_the_gateway_and_the_three_repositories(factory: RecordingFactory) -> None:
    gateway = StubGateway()

    with open_spend_ports(factory, gateway) as ports:
        assert isinstance(ports, SpendPorts)
        assert ports.gateway is gateway
        assert isinstance(ports.runs, RunRepository)
        assert isinstance(ports.steps, StepRunRepository)
        assert isinstance(ports.attempts, AttemptRepository)
        assert isinstance(ports.uow, UnitOfWork)


def test_the_session_is_closed_even_when_the_caller_raises(factory: RecordingFactory) -> None:
    with pytest.raises(RuntimeError, match="gone"):
        with open_spend_ports(factory, StubGateway()):
            raise RuntimeError("gone")

    assert factory.sessions[0].calls == ["close"]


def test_every_call_gets_a_session_of_its_own(factory: RecordingFactory) -> None:
    with open_spend_ports(factory, StubGateway()):
        pass
    with open_spend_ports(factory, StubGateway()):
        pass

    assert len(factory.sessions) == 2  # noqa: PLR2004 — two scopes, two sessions
