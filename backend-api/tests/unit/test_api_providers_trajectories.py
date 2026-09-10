"""`api/providers_trajectories.py` — the two dependencies the trajectory-reading routes use.

`trajectory_repository` is read tolerantly, the way `api/providers.py::git_adapter` reads
its own adapter: `test_projects_router.py`'s frozen harness overrides only `project_ports`
and builds its application with no `session_factory` at all, so `GET /projects/{id}` would
otherwise 500 on a capability that test predates. `trajectory_export_ports` is not — nothing
un-overridden reaches the new `/trajectories.jsonl` route, so it fails loudly like every
other required provider (`test_api_providers.py`'s own claim, generalised).
"""

from __future__ import annotations

from typing import Annotated

import httpx
import pytest
from fastapi import Depends, FastAPI

from orchestrator.api.errors import PROBLEM_MEDIA_TYPE, install_error_handlers
from orchestrator.api.providers import SESSION_FACTORY
from orchestrator.api.providers_trajectories import (
    trajectory_export_ports,
    trajectory_repository,
)
from orchestrator.application.use_cases.trajectory_export import TrajectoryExportPorts
from orchestrator.domain.ports.trajectories import TrajectoryRepository
from orchestrator.infrastructure.db import SQLAlchemyTrajectoryRepository

HTTP_OK = 200
HTTP_SERVER_ERROR = 500


class RecordingSession:
    def close(self) -> None:
        pass


def _session_factory() -> RecordingSession:
    return RecordingSession()


def _probe_app() -> tuple[FastAPI, list[object]]:
    app = FastAPI()
    install_error_handlers(app)
    captured: list[object] = []

    @app.get("/repo")
    def repo(
        trajectories: Annotated[TrajectoryRepository | None, Depends(trajectory_repository)],
    ) -> dict[str, bool]:
        captured.append(trajectories)
        return {"ok": True}

    @app.get("/export")
    def export(
        ports: Annotated[TrajectoryExportPorts, Depends(trajectory_export_ports)],
    ) -> dict[str, bool]:
        captured.append(ports)
        return {"ok": True}

    return app, captured


@pytest.fixture
def probe() -> tuple[FastAPI, list[object]]:
    return _probe_app()


async def test_the_repository_is_none_without_a_session_factory(
    probe: tuple[FastAPI, list[object]],
) -> None:
    app, captured = probe
    setattr(app.state, SESSION_FACTORY, None)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        response = await client.get("/repo")

    assert response.status_code == HTTP_OK
    assert captured == [None]


async def test_the_repository_is_real_with_a_session_factory(
    probe: tuple[FastAPI, list[object]],
) -> None:
    app, captured = probe
    setattr(app.state, SESSION_FACTORY, _session_factory)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        response = await client.get("/repo")

    assert response.status_code == HTTP_OK
    assert isinstance(captured[0], SQLAlchemyTrajectoryRepository)


async def test_the_export_ports_answer_a_500_without_a_session_factory(
    probe: tuple[FastAPI, list[object]],
) -> None:
    """Unlike `trajectory_repository`, this one is required: nothing un-overridden reaches
    the new export route, so it fails loudly rather than serving an empty export."""
    app, _captured = probe
    setattr(app.state, SESSION_FACTORY, None)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        response = await client.get("/export")

    assert response.status_code == HTTP_SERVER_ERROR
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


async def test_the_export_ports_are_real_with_a_session_factory(
    probe: tuple[FastAPI, list[object]],
) -> None:
    app, captured = probe
    setattr(app.state, SESSION_FACTORY, _session_factory)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        response = await client.get("/export")

    assert response.status_code == HTTP_OK
    assert isinstance(captured[0], TrajectoryExportPorts)
