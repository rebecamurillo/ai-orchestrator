"""What `run_event_reader` hands `GET /runs/{id}/events`, and why it is a callable.

`test_run_events_router.py` overrides this dependency and `test_run_events_use_case.py` builds
the ports by hand, so neither exercises the provider itself — and the provider is where the
long-poll's one real hazard lives. Every other read provider yields ports over one session held
open for the whole request; this one must not, because a held session answers every poll from
the identity map it filled on the first one, and a Run that parks mid-wait would look unchanged
until the connection closed.

So the claim here is narrow and exact: **one call, one transaction, closed before it returns,
and a second call opens another.** The session stand-in records, it does not connect.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from orchestrator.api.providers_base import SESSION_FACTORY
from orchestrator.api.providers_run_events import run_event_reader
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import RunRow
from orchestrator.infrastructure.db.repositories.runs import row_values

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-00000000b0f1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-00000000b0f2")

TWO_CALLS = 2


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        template_name="repo-init",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        spend_usd=Decimal("0.5"),
        inputs={"base_branch": "main"},
        created_at=NOW,
    )


class Scalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect."""

    def __init__(self, rows: dict[UUID, Any]) -> None:
        self._rows = rows
        self.calls: list[str] = []

    def get(self, model: Any, key: UUID) -> Any:
        self.calls.append("get")
        return self._rows.get(key)

    def scalars(self, statement: Any) -> Scalars:
        self.calls.append("scalars")
        return Scalars([])

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


class RecordingSessionFactory:
    def __init__(self, rows: dict[UUID, Any]) -> None:
        self._rows = rows
        self.sessions: list[RecordingSession] = []

    def __call__(self) -> RecordingSession:
        session = RecordingSession(self._rows)
        self.sessions.append(session)
        return session


def reader_over(factory: RecordingSessionFactory) -> Any:
    """The provider, called with the only thing it reads off the request."""
    state = SimpleNamespace(**{SESSION_FACTORY: factory})
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    return run_event_reader(request)  # type: ignore[arg-type]


def test_the_reader_answers_the_stored_run() -> None:
    run = a_run()
    factory = RecordingSessionFactory({run.id: RunRow(**row_values(run))})

    event = reader_over(factory)(run.id)

    assert (event.run_id, event.status, event.spend_usd) == (run.id, "running", Decimal("0.5"))


def test_each_call_opens_and_closes_a_transaction_of_its_own() -> None:
    """A session held across polls would hide the very change the wait exists to see."""
    run = a_run()
    factory = RecordingSessionFactory({run.id: RunRow(**row_values(run))})
    read = reader_over(factory)

    read(run.id)
    read(run.id)

    assert len(factory.sessions) == TWO_CALLS
    for session in factory.sessions:
        assert session.calls[-1] == "close"
        assert "commit" not in session.calls


def test_an_unknown_id_is_not_found_and_still_closes_the_session() -> None:
    factory = RecordingSessionFactory({})

    with pytest.raises(NotFound):
        reader_over(factory)(new_id())

    assert factory.sessions[0].calls[-1] == "close"
