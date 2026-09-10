"""`GET /api/v1/projects/{id}/trajectories.jsonl` (SPEC CAP-6, AD-19, FR-32 export) over an
ASGI transport.

A router of its own, on its own path, for the reason `api/routers/history.py` gives for
its own: `tests/unit/test_projects_router.py` pins `api/routers/projects.py` at exactly four
operations, so this route is a new module rather than a fifth operation on a frozen one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import FastAPI

from orchestrator.api.providers_trajectories import trajectory_export_ports
from orchestrator.api.routers import trajectories as router_module
from orchestrator.application.use_cases.trajectory_export import TrajectoryExportPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.trajectory import GateResults, Trajectory
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.projects import FakeProjectRepository
from tests.unit.fakes.trajectories import FakeTrajectoryRepository

HTTP_OK = 200
HTTP_NOT_FOUND = 404
NDJSON = "application/x-ndjson"
PROBLEM = "application/problem+json"
AT = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
THREE_TRAJECTORIES = 3
MANY_TRAJECTORIES = 150


def a_project(**overrides: object) -> Project:
    fields: dict[str, object] = {
        "id": new_id(),
        "slug": "my-website",
        "name": "My website",
        "context_text": "",
        "context_paths": (),
        "env_vars_enc": (),
        "log_prompt_content": False,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Project(**fields)  # type: ignore[arg-type]


def a_trajectory(**overrides: object) -> Trajectory:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "epic_index": 0,
        "frame": "stories[0]",
        "gate_results": GateResults(build="liveness", verify="done", commit_guard="done"),
        "recorded_at": AT,
    }
    fields.update(overrides)
    return Trajectory(**fields)  # type: ignore[arg-type]


def url(project_id: UUID) -> str:
    return f"/api/v1/projects/{project_id}/trajectories.jsonl"


class Api:
    def __init__(
        self,
        env: dict[str, str],
        *,
        projects: list[Project] | None = None,
        trajectories: list[Trajectory] | None = None,
    ) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.ports = TrajectoryExportPorts(
            projects=FakeProjectRepository(projects or []),
            trajectories=FakeTrajectoryRepository(trajectories or []),
            clock=FakeClock(AT),
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[trajectory_export_ports] = lambda: self.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


def test_the_router_declares_exactly_one_operation() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/projects/{project_id}/trajectories.jsonl")]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_an_unknown_project_is_a_404_problem_document(env: dict[str, str]) -> None:
    api = Api(env)

    async with api.client() as client:
        response = await client.get(url(new_id()))

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"] == PROBLEM


async def test_a_project_with_none_answers_200_and_an_empty_body(env: dict[str, str]) -> None:
    project = a_project()
    api = Api(env, projects=[project])

    async with api.client() as client:
        response = await client.get(url(project.id))

    assert response.status_code == HTTP_OK
    assert response.content == b""
    assert response.headers["content-type"].startswith(NDJSON)


async def test_three_trajectories_arrive_newest_first_as_ndjson(env: dict[str, str]) -> None:
    project = a_project()
    older = a_trajectory(project_id=project.id, recorded_at=datetime(2026, 9, 8, tzinfo=UTC))
    newer = a_trajectory(project_id=project.id, recorded_at=datetime(2026, 9, 9, tzinfo=UTC))
    newest = a_trajectory(project_id=project.id, recorded_at=datetime(2026, 9, 10, tzinfo=UTC))
    api = Api(env, projects=[project], trajectories=[older, newest, newer])

    async with api.client() as client:
        response = await client.get(url(project.id))

    lines = response.content.decode().splitlines()
    assert len(lines) == THREE_TRAJECTORIES
    parsed = [json.loads(line) for line in lines]
    assert [row["id"] for row in parsed] == [str(newest.id), str(newer.id), str(older.id)]


async def test_the_headers_carry_the_media_type_and_the_attachment_filename(
    env: dict[str, str],
) -> None:
    project = a_project(slug="acme-app")
    api = Api(env, projects=[project])

    async with api.client() as client:
        response = await client.get(url(project.id))

    assert response.headers["content-type"] == NDJSON
    disposition = response.headers["content-disposition"]
    expected_date = AT.date().isoformat()
    assert disposition == f'attachment; filename="trajectories-acme-app-{expected_date}.jsonl"'


async def test_more_than_one_page_still_streams_every_row(env: dict[str, str]) -> None:
    project = a_project()
    rows = [a_trajectory(project_id=project.id) for _ in range(MANY_TRAJECTORIES)]
    api = Api(env, projects=[project], trajectories=rows)

    async with api.client() as client:
        response = await client.get(url(project.id))

    assert len(response.content.decode().splitlines()) == MANY_TRAJECTORIES


async def test_the_route_needs_the_bearer(env: dict[str, str]) -> None:
    project = a_project()
    api = Api(env, projects=[project])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app, raise_app_exceptions=False),
        base_url="http://backend-api",
    ) as client:
        response = await client.get(url(project.id))

    assert response.status_code == httpx.codes.UNAUTHORIZED
