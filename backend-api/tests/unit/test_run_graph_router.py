"""`GET /api/v1/runs/{run_id}/graph` (4.12, SPEC CAP-12, AD-15) over an ASGI transport.

The pure build is `tests/unit/application/test_run_graph.py`'s; this module proves the
route is served alongside the template graph on the same router (`api/routers/graph.py`,
whose own frozen test — `test_graph_router.py` — is containment, not an exact list, exactly
so this route could land here), and the request-level refusals.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_view_ports
from orchestrator.api.routers import graph as router_module
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
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
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(run: Run, path: str, *, seq: int, status: str = "planned") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=seq,
        path=path,
        label=path,
        kind="shell",
        gate="deterministic",
        status=status,  # type: ignore[arg-type]
    )


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.ports = RunViewPorts(
            runs=self.runs,
            steps=self.steps,
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


def test_the_run_graph_is_served_as_a_get_beside_the_template_graph() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert (["GET"], "/runs/{run_id}/graph") in routes
    for methods, _path in routes:
        assert "GET" in methods


async def test_a_known_run_answers_its_graph(api: Api) -> None:
    run = a_run()
    api.runs.add(run)
    api.steps.add_many(
        [a_row(run, "checkout", seq=1, status="done"), a_row(run, "build", seq=2, status="running")]
    )

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/graph")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == ["root", "checkout", "build"]
    assert body["edges"] == [
        {"from": "root", "to": "checkout"},
        {"from": "checkout", "to": "build"},
    ]


async def test_the_running_row_is_current(api: Api) -> None:
    run = a_run()
    api.runs.add(run)
    api.steps.add_many([a_row(run, "build", seq=1, status="running")])

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/graph")

    build = next(node for node in response.json()["nodes"] if node["id"] == "build")
    assert build["current"] is True
    assert build["token"] == "RUN"


async def test_a_cancelled_run_roots_at_can(api: Api) -> None:
    run = a_run(status="cancelled")
    api.runs.add(run)
    api.steps.add_many([a_row(run, "build", seq=1, status="error")])

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/graph")

    root = next(node for node in response.json()["nodes"] if node["id"] == "root")
    assert root["token"] == "CAN"


async def test_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{UNKNOWN_ID}/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_malformed_id_is_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/not-a-uuid/graph")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_without_the_bearer_it_is_a_401(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.anonymous() as client:
        response = await client.get(f"{RUNS}/{run.id}/graph")

    assert response.status_code == HTTP_UNAUTHORIZED
