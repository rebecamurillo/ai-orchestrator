"""`open_initiative_ports` and the `records`/`history` wiring of `initiative_read_ports`
(story 6, epic 7; AC5)."""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI

from orchestrator.api.errors import install_error_handlers
from orchestrator.api.providers_base import GIT, SESSION_FACTORY
from orchestrator.api.providers_initiatives import initiative_read_ports, open_initiative_ports
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.application.use_cases.open_initiative import OpenInitiativePorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import SQLAlchemyUnitOfWork
from orchestrator.infrastructure.git.git_history import SubprocessGitHistory
from tests.unit.fakes.remote_branches import FakeRemoteGit
from tests.unit.test_api_providers import RecordingSessionFactory

HTTP_OK = 200


def probe_app(factory: Any) -> tuple[FastAPI, list[Any]]:
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SESSION_FACTORY, factory)
    setattr(app.state, GIT, FakeRemoteGit())
    captured: list[Any] = []

    @app.get("/open")
    def opened(
        ports: Annotated[OpenInitiativePorts | None, Depends(open_initiative_ports)],
    ) -> bool:
        captured.append(ports)
        return True

    @app.get("/read")
    def read(ports: Annotated[InitiativeReadPorts, Depends(initiative_read_ports)]) -> bool:
        captured.append(ports)
        return True

    return app, captured


async def get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.get(path)


async def test_a_plain_read_opens_no_session() -> None:
    factory = RecordingSessionFactory()
    app, captured = probe_app(factory)

    assert (await get(app, "/open")).status_code == HTTP_OK

    assert captured == [None]
    assert factory.sessions == []


async def test_opened_wires_the_initiatives_and_the_unit_of_work_on_one_session() -> None:
    factory = RecordingSessionFactory()
    app, captured = probe_app(factory)

    assert (await get(app, "/open?opened=true")).status_code == HTTP_OK

    (ports,) = captured
    assert ports.initiatives._session is factory.sessions[0]
    assert isinstance(ports.uow, SQLAlchemyUnitOfWork)
    assert isinstance(ports.clock, SystemClock)


async def test_the_read_ports_carry_the_gate_records_and_the_git_history() -> None:
    factory = RecordingSessionFactory()
    app, captured = probe_app(factory)

    assert (await get(app, "/read")).status_code == HTTP_OK

    (ports,) = captured
    assert ports.records._session is factory.sessions[0]
    assert isinstance(ports.history, SubprocessGitHistory)
