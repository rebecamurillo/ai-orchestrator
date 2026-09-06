"""`infrastructure/db/writers.py`: one session's worth of `WriterPorts`, per durable step.

The three status writers open their own transaction (`with ports.uow: … commit()`) and
`SQLAlchemyUnitOfWork` refuses a second entry, so something has to own the session *around*
them. That is what this module is, and what is asserted here is the pair of semantics that
makes it safe: the writer's own block commits or discards, and the session it borrowed is
closed on every path — including the one where the writer raised.

The session is recorded rather than real; that the four repositories build the SQL they claim
is `tests/unit/test_run_repository_adapter.py`'s, and that the schema matches is the e2e
suite's.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.infrastructure.db.writers import SessionUnitOfWork, open_writer_ports


class RecordingSession:
    """A session that records the three calls this module can make on it."""

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


@pytest.fixture
def factory() -> RecordingFactory:
    return RecordingFactory()


def test_the_scope_yields_the_four_repositories_every_writer_takes(
    factory: RecordingFactory,
) -> None:
    with open_writer_ports(factory) as ports:
        assert isinstance(ports, WriterPorts)
        assert isinstance(ports.runs, RunRepository)
        assert isinstance(ports.steps, StepRunRepository)
        assert isinstance(ports.attempts, AttemptRepository)
        assert isinstance(ports.records, GateRecordRepository)
        assert isinstance(ports.uow, UnitOfWork)


def test_the_writers_own_block_commits_through_the_session(factory: RecordingFactory) -> None:
    with open_writer_ports(factory) as ports, ports.uow:
        ports.uow.commit()

    assert factory.sessions[0].calls == ["commit", "close"]


def test_a_block_that_never_commits_discards_its_work(factory: RecordingFactory) -> None:
    with open_writer_ports(factory) as ports, ports.uow:
        pass

    assert factory.sessions[0].calls == ["rollback", "close"]


def test_the_session_is_closed_even_when_the_writer_raises(factory: RecordingFactory) -> None:
    with pytest.raises(RuntimeError, match="the row was gone"):
        with open_writer_ports(factory) as ports, ports.uow:
            raise RuntimeError("the row was gone")

    assert factory.sessions[0].calls == ["rollback", "close"]


def test_two_writers_in_one_scope_each_get_their_own_transaction(
    factory: RecordingFactory,
) -> None:
    """A durable step calls `start_attempt` and then the executor; both enter the same uow."""
    with open_writer_ports(factory) as ports:
        with ports.uow:
            ports.uow.commit()
        with ports.uow:
            ports.uow.commit()

    assert factory.sessions[0].calls == ["commit", "commit", "close"]


def test_a_rollback_asked_for_by_name_is_passed_through() -> None:
    session = RecordingSession()

    SessionUnitOfWork(session).rollback()

    assert session.calls == ["rollback"]


def test_every_step_gets_a_session_of_its_own(factory: RecordingFactory) -> None:
    """A row that runs for forty minutes must not hold a connection while it does."""
    with open_writer_ports(factory):
        pass
    with open_writer_ports(factory):
        pass

    assert len(factory.sessions) == 2  # noqa: PLR2004 — two scopes, two sessions
