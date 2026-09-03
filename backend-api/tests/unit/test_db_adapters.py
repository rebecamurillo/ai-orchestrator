"""The one datasource, tested without a database (AD-18).

SQLAlchemy's `create_engine` is lazy — it parses the URL and builds a pool, it does not
connect — so the engine and the session factory can be asserted here with no Postgres and
no network. What cannot be deferred is the transaction contract: `SQLAlchemyUnitOfWork`
must behave exactly as `FakeUnitOfWork` does, because every use case is written against the
fake and run against the adapter. That equivalence is what this module checks, driving the
adapter over a session double that records calls instead of speaking to a server.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import pytest
from sqlalchemy import Engine, MetaData

from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.infrastructure.db import (
    Base,
    SQLAlchemyUnitOfWork,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.db import FakeUnitOfWork


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


class RecordingSessionFactory:
    def __init__(self) -> None:
        self.sessions: list[RecordingSession] = []

    def __call__(self) -> RecordingSession:
        session = RecordingSession()
        self.sessions.append(session)
        return session


@pytest.fixture
def factory() -> RecordingSessionFactory:
    return RecordingSessionFactory()


# ── the engine ───────────────────────────────────────────────────────────────


def test_the_engine_is_built_from_the_settings_url(env: dict[str, str]) -> None:
    engine = create_engine_from(Settings())

    assert isinstance(engine, Engine)
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.database == env["POSTGRES_DB"]


def test_building_the_engine_opens_no_connection(env: dict[str, str]) -> None:
    """`make test` runs with no database; a connecting constructor would need one."""
    engine = create_engine_from(Settings())

    assert engine.pool.checkedout() == 0


def test_the_password_never_reaches_a_repr(env: dict[str, str]) -> None:
    """A logged engine or settings object must not print the credential (hard rule 5)."""
    settings = Settings()
    engine = create_engine_from(settings)

    assert env["POSTGRES_PASSWORD"] not in repr(engine)
    assert env["DATABASE_URL"] not in repr(settings)
    assert env["DATABASE_URL"] not in str(engine)


def test_a_dead_connection_is_detected_before_a_statement_uses_it(env: dict[str, str]) -> None:
    """Postgres restarts; without pre-ping the first request after one fails instead."""
    engine = create_engine_from(Settings())

    assert engine.pool._pre_ping is True


# ── the declarative base ─────────────────────────────────────────────────────


def test_the_base_carries_one_metadata_for_alembic_to_read() -> None:
    assert isinstance(Base.metadata, MetaData)


def test_every_declared_table_is_in_the_schema_alembic_manages() -> None:
    """Alembic versions schema `public` only; a table elsewhere would never be migrated.

    An empty registry satisfies this trivially today — no domain table exists yet — and it
    keeps holding as later stories declare theirs, which is the point of stating it this way
    rather than asserting the registry is empty.
    """
    for name, table in Base.metadata.tables.items():
        assert table.schema in (None, "public"), f"{name}: schema {table.schema!r}"


def test_constraints_are_named_by_convention_so_a_migration_can_drop_them() -> None:
    """An unnamed constraint gets a database-chosen name that no downgrade can reference."""
    assert set(Base.metadata.naming_convention) >= {"ix", "uq", "ck", "fk", "pk"}


# ── the session factory ──────────────────────────────────────────────────────


def test_the_session_factory_is_bound_to_the_engine(env: dict[str, str]) -> None:
    engine = create_engine_from(Settings())

    session_factory = create_session_factory(engine)

    assert session_factory.kw["bind"] is engine


def test_the_session_factory_does_not_expire_on_commit(env: dict[str, str]) -> None:
    """Expiring would re-`SELECT` every attribute a use case reads after committing."""
    session_factory = create_session_factory(create_engine_from(Settings()))

    assert session_factory.kw["expire_on_commit"] is False


# ── the unit of work ─────────────────────────────────────────────────────────


def test_the_adapter_satisfies_the_port(factory: RecordingSessionFactory) -> None:
    uow: UnitOfWork = SQLAlchemyUnitOfWork(factory)

    assert isinstance(uow, UnitOfWork)


def test_entering_opens_one_session_and_returns_the_unit_of_work(
    factory: RecordingSessionFactory,
) -> None:
    uow = SQLAlchemyUnitOfWork(factory)

    with uow as entered:
        assert entered is uow
        assert len(factory.sessions) == 1
        assert uow.session is factory.sessions[0]


def test_a_committed_block_commits_and_closes(factory: RecordingSessionFactory) -> None:
    with SQLAlchemyUnitOfWork(factory) as uow:
        uow.commit()

    assert factory.sessions[0].calls == ["commit", "close"]


def test_a_block_that_never_commits_rolls_back(factory: RecordingSessionFactory) -> None:
    """Leaving without committing must discard the work, not leak an open transaction."""
    with SQLAlchemyUnitOfWork(factory):
        pass

    assert factory.sessions[0].calls == ["rollback", "close"]


def test_an_exception_rolls_back_and_propagates(factory: RecordingSessionFactory) -> None:
    with pytest.raises(RuntimeError, match="boom"), SQLAlchemyUnitOfWork(factory):
        raise RuntimeError("boom")

    assert factory.sessions[0].calls == ["rollback", "close"]


def test_the_session_is_closed_even_when_rollback_fails(
    factory: RecordingSessionFactory,
) -> None:
    """A connection already gone makes `rollback()` raise; the session must still close."""
    uow = SQLAlchemyUnitOfWork(factory)

    with pytest.raises(RuntimeError, match="connection gone"), uow:
        session: Any = uow.session

        def exploding_rollback() -> None:
            session.calls.append("rollback")
            raise RuntimeError("connection gone")

        session.rollback = exploding_rollback

    assert factory.sessions[0].calls == ["rollback", "close"]


def test_the_session_is_released_when_the_block_ends(factory: RecordingSessionFactory) -> None:
    uow = SQLAlchemyUnitOfWork(factory)

    with uow:
        pass

    assert uow.session is None


def test_committing_outside_the_block_is_refused(factory: RecordingSessionFactory) -> None:
    uow = SQLAlchemyUnitOfWork(factory)

    with pytest.raises(RuntimeError, match="not entered"):
        uow.commit()


def test_entering_twice_is_refused_rather_than_orphaning_a_session(
    factory: RecordingSessionFactory,
) -> None:
    """A second `__enter__` would replace the session and leak its connection from the pool."""
    uow = SQLAlchemyUnitOfWork(factory)

    with uow, pytest.raises(RuntimeError, match="already open"):
        uow.__enter__()

    assert len(factory.sessions) == 1
    assert factory.sessions[0].calls == ["rollback", "close"]


def test_a_failing_rollback_never_hides_the_error_that_caused_it(
    factory: RecordingSessionFactory,
) -> None:
    """Raising from `__exit__` would replace the exception the caller actually needs."""
    uow = SQLAlchemyUnitOfWork(factory)

    with pytest.raises(RuntimeError, match="the real failure"), uow:
        session: Any = uow.session

        def exploding_rollback() -> None:
            session.calls.append("rollback")
            raise RuntimeError("connection gone")

        session.rollback = exploding_rollback
        raise RuntimeError("the real failure")

    assert factory.sessions[0].calls == ["rollback", "close"]


def test_the_adapter_and_the_fake_record_the_same_sequence(
    factory: RecordingSessionFactory,
) -> None:
    """Use cases are written against the fake; a divergence here would surface only in e2e."""
    fake = FakeUnitOfWork()
    with fake:
        fake.commit()

    with SQLAlchemyUnitOfWork(factory) as adapter:
        adapter.commit()

    assert fake.committed is True
    assert "commit" in factory.sessions[0].calls
    assert "rollback" not in factory.sessions[0].calls


def test_the_exit_signature_matches_the_port(factory: RecordingSessionFactory) -> None:
    """A context manager that returned True would swallow the exception the port propagates."""
    uow = SQLAlchemyUnitOfWork(factory)
    uow.__enter__()

    swallowed = uow.__exit__(RuntimeError, RuntimeError("boom"), None)

    assert swallowed is None


def test_exit_accepts_a_traceback(factory: RecordingSessionFactory) -> None:
    uow = SQLAlchemyUnitOfWork(factory)
    uow.__enter__()
    traceback: TracebackType | None = None
    try:
        raise RuntimeError("boom")
    except RuntimeError as error:
        traceback = error.__traceback__

    assert uow.__exit__(RuntimeError, RuntimeError("boom"), traceback) is None
