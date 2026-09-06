"""`api/providers.py::template_ports` — the ports a Template use case runs on.

`test_api_providers.py` proves the transaction pattern generically over `project_ports`;
this module is where `template_ports`'s own wiring is exercised for real, since every
router test in `test_templates_router.py` replaces this dependency entirely through
`dependency_overrides` and never runs its actual body.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI

from orchestrator.api.errors import install_error_handlers
from orchestrator.api.providers import SESSION_FACTORY, template_ports
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import SQLAlchemyTemplateVersionRepository

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


def probe_app(*, session_factory: Any) -> tuple[FastAPI, list[TemplatePorts]]:
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SESSION_FACTORY, session_factory)
    captured: list[TemplatePorts] = []

    @app.get("/probe")
    def probe(ports: Annotated[TemplatePorts, Depends(template_ports)]) -> dict[str, bool]:
        captured.append(ports)
        return {"ok": True}

    @app.get("/probe-commit")
    def probe_commit(ports: Annotated[TemplatePorts, Depends(template_ports)]) -> dict[str, bool]:
        ports.uow.commit()
        return {"ok": True}

    return app, captured


async def call(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.get(path)


@pytest.fixture
def factory() -> RecordingSessionFactory:
    return RecordingSessionFactory()


async def test_the_repository_sits_on_the_session_the_unit_of_work_opened(
    factory: RecordingSessionFactory,
) -> None:
    app, captured = probe_app(session_factory=factory)

    response = await call(app, "/probe")

    assert response.status_code == HTTP_OK
    (ports,) = captured
    assert isinstance(ports.templates, SQLAlchemyTemplateVersionRepository)
    assert ports.templates._session is factory.sessions[0]


async def test_the_clock_is_the_wall_clock_adapter(factory: RecordingSessionFactory) -> None:
    app, captured = probe_app(session_factory=factory)

    await call(app, "/probe")

    assert isinstance(captured[0].clock, SystemClock)


async def test_a_request_that_never_commits_rolls_its_session_back(
    factory: RecordingSessionFactory,
) -> None:
    app, _ = probe_app(session_factory=factory)

    await call(app, "/probe")

    assert factory.sessions[0].calls == ["rollback", "close"]


async def test_a_request_that_commits_keeps_its_work(factory: RecordingSessionFactory) -> None:
    app, _ = probe_app(session_factory=factory)

    await call(app, "/probe-commit")

    assert factory.sessions[0].calls == ["commit", "close"]
