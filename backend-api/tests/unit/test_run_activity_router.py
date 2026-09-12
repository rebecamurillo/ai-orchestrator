"""`POST /api/v1/runs/{run_id}/activity` (SM-2, story 8-2) over an ASGI transport.

The pure accumulation logic is `tests/unit/application/test_record_activity.py`'s; this
module proves the route shape, the request-level refusals (422 for out-of-range
`focused_seconds`, 404 for unknown `run_id`, 401 for missing bearer), and the happy-path
body shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import activity_ports
from orchestrator.api.routers import run_activity as router_module
from orchestrator.application.use_cases.activity import ActivityPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.runs import FakeRunRepository

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 11, tzinfo=UTC)
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "repo-init",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "inputs": {"base_branch": "main"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository()
        self.uow = FakeUnitOfWork()
        self.ports = ActivityPorts(runs=self.runs, uow=self.uow)
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[activity_ports] = lambda: self.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def anonymous(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


def test_the_router_declares_exactly_the_expected_operations() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [
        (["POST"], "/runs/{run_id}/activity"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_happy_path_returns_updated_active_seconds(api: Api) -> None:
    run = a_run(active_seconds=0)
    api.runs.add(run)

    async with api.client() as client:
        response = await client.post(f"{RUNS}/{run.id}/activity", json={"focused_seconds": 45})

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body == {"active_seconds": 45}


async def test_accumulation_adds_to_existing(api: Api) -> None:
    run = a_run(active_seconds=45)
    api.runs.add(run)

    async with api.client() as client:
        response = await client.post(f"{RUNS}/{run.id}/activity", json={"focused_seconds": 45})

    assert response.status_code == HTTP_OK
    assert response.json() == {"active_seconds": 90}


async def test_focused_seconds_zero_is_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(f"{RUNS}/{UNKNOWN_ID}/activity", json={"focused_seconds": 0})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_focused_seconds_over_3600_is_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(
            f"{RUNS}/{UNKNOWN_ID}/activity", json={"focused_seconds": 3601}
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_unknown_run_id_is_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(f"{RUNS}/{UNKNOWN_ID}/activity", json={"focused_seconds": 30})

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_without_the_bearer_it_is_401(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.anonymous() as client:
        response = await client.post(f"{RUNS}/{run.id}/activity", json={"focused_seconds": 30})

    assert response.status_code == HTTP_UNAUTHORIZED
