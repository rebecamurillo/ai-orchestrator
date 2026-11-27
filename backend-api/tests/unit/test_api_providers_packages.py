"""`package_ports` builds every port on the unit of work's session (story 3 of epic 6)."""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI

from orchestrator.api.errors import install_error_handlers
from orchestrator.api.providers_base import GIT, SESSION_FACTORY, SETTINGS
from orchestrator.api.providers_packages import package_ports
from orchestrator.application.use_cases.packages import PackagePorts
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit
from tests.unit.test_api_providers import RecordingSessionFactory

HTTP_OK = 200
HTTP_SERVER_ERROR = 500


def probe_app(*, git: Any, factory: Any, settings: Any) -> tuple[FastAPI, list[Any]]:
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SESSION_FACTORY, factory)
    setattr(app.state, SETTINGS, settings)
    if git is not None:
        setattr(app.state, GIT, git)
    captured: list[Any] = []

    @app.get("/probe")
    def probe(ports: Annotated[PackagePorts, Depends(package_ports)]) -> dict[str, bool]:
        captured.append(ports)
        return {"ok": True}

    return app, captured


async def get(app: FastAPI) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.get("/probe")


async def test_every_port_sits_on_the_one_session(env: dict[str, str]) -> None:
    factory = RecordingSessionFactory()
    settings = Settings()
    git = FakeGit()
    app, captured = probe_app(git=git, factory=factory, settings=settings)

    assert (await get(app)).status_code == HTTP_OK

    (ports,) = captured
    session = factory.sessions[0]
    for port in (ports.projects, ports.repositories, ports.packages, ports.templates):
        assert port._session is session
    assert ports.git is git
    assert ports.work_dir == settings.work_dir


async def test_an_application_without_git_answers_a_500_naming_the_port(
    env: dict[str, str],
) -> None:
    app, _ = probe_app(git=None, factory=RecordingSessionFactory(), settings=Settings())

    assert (await get(app)).status_code == HTTP_SERVER_ERROR
