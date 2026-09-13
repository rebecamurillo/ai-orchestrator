"""What `activity_ports` hands `record_activity` (8.2).

`test_run_activity_router.py` overrides the dependency and `test_record_activity.py` builds
`ActivityPorts` by hand, so neither exercises the real provider. The seam between them is
where story 8-2 went wrong: this provider enters the unit of work before yielding — every
provider in `api/providers.py` must, since the repository is built around `uow.session` —
so `record_activity` has to `commit()` that scope, not re-enter it. It re-entered, which
`SQLAlchemyUnitOfWork.__enter__` refuses, and the route answered 500 to every request
including the happy path; the Schemathesis gate caught it as a server error on
`POST /runs/{run_id}/activity`.

Three claims, all about the provider and none about the accumulation arithmetic: the scope
is already open when the use case receives it, the repository sits on the session that
scope will commit, and the session is closed whether or not anything committed. The
`RecordingSession` stand-in is `test_api_providers.py`'s — it records, it does not connect.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI

from orchestrator.api.errors import install_error_handlers
from orchestrator.api.providers import SESSION_FACTORY, activity_ports
from orchestrator.application.use_cases.activity import ActivityPorts
from orchestrator.infrastructure.db import SQLAlchemyRunRepository

HTTP_OK = 200


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


def probe_app(session_factory: Any) -> tuple[FastAPI, list[ActivityPorts]]:
    """A one-route application whose only job is to receive the ports and report them."""
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SESSION_FACTORY, session_factory)
    captured: list[ActivityPorts] = []

    @app.get("/probe")
    def probe(ports: Annotated[ActivityPorts, Depends(activity_ports)]) -> dict[str, bool]:
        captured.append(ports)
        return {"ok": True}

    @app.get("/probe-commit")
    def probe_commit(ports: Annotated[ActivityPorts, Depends(activity_ports)]) -> dict[str, bool]:
        # what `record_activity` does on the happy path: commit, without entering first
        ports.uow.commit()
        return {"ok": True}

    @app.get("/probe-reenter")
    def probe_reenter(ports: Annotated[ActivityPorts, Depends(activity_ports)]) -> dict[str, bool]:
        # asked in-request, because the scope is closed again by the time the route returns
        try:
            ports.uow.__enter__()
        except RuntimeError:
            return {"refused": True}
        return {"refused": False}

    return app, captured


async def call(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.get(path)


@pytest.fixture
def factory() -> RecordingSessionFactory:
    return RecordingSessionFactory()


async def test_the_use_case_commits_without_entering_the_scope_itself(
    factory: RecordingSessionFactory,
) -> None:
    """The regression: `record_activity` re-entered this scope and every request was a 500."""
    app, _ = probe_app(factory)

    response = await call(app, "/probe-commit")

    assert response.status_code == HTTP_OK
    assert factory.sessions[0].calls == ["commit", "close"]


async def test_the_scope_the_provider_yields_refuses_a_second_entry(
    factory: RecordingSessionFactory,
) -> None:
    """Why the use case may not re-enter: the scope it receives is already open."""
    app, _ = probe_app(factory)

    response = await call(app, "/probe-reenter")

    assert response.json() == {"refused": True}


async def test_the_repository_sits_on_the_session_the_scope_commits(
    factory: RecordingSessionFactory,
) -> None:
    """A repository on any other session would write outside the use case's transaction."""
    app, captured = probe_app(factory)

    response = await call(app, "/probe")

    assert response.status_code == HTTP_OK
    (ports,) = captured
    assert isinstance(ports.runs, SQLAlchemyRunRepository)
    assert ports.runs._session is factory.sessions[0]


async def test_nothing_committed_rolls_back_and_closes(
    factory: RecordingSessionFactory,
) -> None:
    """The path `record_activity` takes for a 404: no write persists, the connection returns."""
    app, _ = probe_app(factory)

    await call(app, "/probe")

    assert factory.sessions[0].calls == ["rollback", "close"]
