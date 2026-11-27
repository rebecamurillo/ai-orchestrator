"""`initiative_read_ports` and `run_read_ports` wire what story 4 reads through (epic 7)."""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI

from orchestrator.api import providers, providers_run_reads
from orchestrator.api.errors import install_error_handlers
from orchestrator.api.providers_base import GIT, SESSION_FACTORY
from orchestrator.api.providers_initiatives import initiative_read_ports
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.application.use_cases.run_read_ports import RunReadPorts
from orchestrator.infrastructure.workspace.fs import FsWorkspace
from tests.unit.fakes.remote_branches import FakeRemoteGit
from tests.unit.test_api_providers import RecordingSessionFactory

HTTP_OK = 200


def probe_app(factory: Any, git: Any) -> tuple[FastAPI, list[Any]]:
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SESSION_FACTORY, factory)
    setattr(app.state, GIT, git)
    captured: list[Any] = []

    @app.get("/initiatives")
    def initiatives(ports: Annotated[InitiativeReadPorts, Depends(initiative_read_ports)]) -> bool:
        captured.append(ports)
        return True

    @app.get("/runs")
    def runs(ports: Annotated[RunReadPorts, Depends(providers.run_read_ports)]) -> bool:
        captured.append(ports)
        return True

    return app, captured


async def get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.get(path)


async def test_the_initiative_reads_sit_on_one_session() -> None:
    factory = RecordingSessionFactory()
    git = FakeRemoteGit()
    app, captured = probe_app(factory, git)

    assert (await get(app, "/initiatives")).status_code == HTTP_OK

    (ports,) = captured
    session = factory.sessions[0]
    for port in (
        ports.initiatives,
        ports.advances,
        ports.projects,
        ports.repositories,
        ports.runs,
        ports.steps,
        ports.attempts,
    ):
        assert port._session is session
    assert ports.runs is ports.initiative_runs
    assert ports.workspace is FsWorkspace
    assert ports.git is git


async def test_the_run_reads_wire_attempts_initiatives_templates_and_workspace() -> None:
    factory = RecordingSessionFactory()
    app, captured = probe_app(factory, FakeRemoteGit())

    assert (await get(app, "/runs")).status_code == HTTP_OK

    (ports,) = captured
    session = factory.sessions[0]
    for port in (ports.attempts, ports.initiatives, ports.templates, ports.steps):
        assert port._session is session
    assert ports.workspace is FsWorkspace


def test_run_read_ports_is_one_function_whichever_module_names_it() -> None:
    assert providers.run_read_ports is providers_run_reads.run_read_ports
