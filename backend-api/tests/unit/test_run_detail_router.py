"""`GET /api/v1/runs/{run_id}/detail` (4.12, SPEC CAP-12) over an ASGI transport.

The pure join is `tests/unit/application/test_run_views.py`'s; this module proves the route
shape, that `GET /runs/{run_id}` (the minimal read model, `api/routers/run.py`) is untouched
by this story, and the request-level refusals (404, 422, 401).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_view_ports
from orchestrator.api.routers import run_detail as router_module
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 7, tzinfo=UTC)
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
        self.ports = RunViewPorts(
            runs=self.runs,
            steps=FakeStepRunRepository(),
            attempts=FakeAttemptRepository(),
            gate_records=FakeGateRecordRepository(),
            projects=FakeProjectRepository(),
            repositories=FakeRepositoryRepository(),
            logs=FakeLogReader(),
            clock=FakeClock(NOW),
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[run_view_ports] = lambda: self.ports
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


def test_the_router_declares_exactly_one_operation() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/runs/{run_id}/detail")]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_a_known_run_answers_every_section(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/detail")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["run"]["id"] == str(run.id)
    assert set(body) == {
        "run",
        "header",
        "alert",
        "steps",
        "stories",
        "cost",
        "gate_record",
        "admitted_signals",
        "summary",
    }


async def test_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{UNKNOWN_ID}/detail")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_malformed_id_is_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/not-a-uuid/detail")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_without_the_bearer_it_is_a_401(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.anonymous() as client:
        response = await client.get(f"{RUNS}/{run.id}/detail")

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_get_run_stays_the_minimal_read_model(api: Api) -> None:
    """`GET /runs/{id}` (no `/detail`) is `run.py`'s own route — this story never touches
    it. Reached through the SAME app, but a different dependency (`run_read_ports`, not
    overridden here), so an unwired call 500s rather than silently answering the full
    model — proof the two routes are genuinely different code paths."""
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}")

    assert response.status_code != HTTP_OK
