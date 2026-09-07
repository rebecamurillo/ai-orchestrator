"""`GET /api/v1/queue` (SPEC CAP-11, FR-13, FR-25) over an ASGI transport.

The join itself is `tests/unit/application/test_queue.py`'s; this module proves the route
shape, the response envelope (`{items, next_cursor, max_active_runs}`), and that the one
credential guards it like every other feature route (AD-4 is swept structurally by
`test_bearer_auth.py`; this is the request-level proof for this path specifically).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import queue_ports
from orchestrator.api.routers import queue as router_module
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.engine import QueueEntry
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
QUEUE = "/api/v1/queue"
NOW = datetime(2026, 9, 7, tzinfo=UTC)


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": 0,
        "inputs": {"branch": "feat/x"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Api:
    def __init__(self, env: dict[str, str], *, runs: list[Run] | None = None) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository(runs or [])
        self.engine = FakeWorkflowEngine()
        self.ports = QueuePorts(
            engine=self.engine,
            runs=self.runs,
            steps=FakeStepRunRepository(),
            clock=FakeClock(NOW),
            max_active_runs=2,
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[queue_ports] = lambda: self.ports
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

    assert routes == [(["GET"], "/queue")]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_an_empty_queue_answers_the_envelope_with_no_items(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(QUEUE)

    assert response.status_code == HTTP_OK
    assert response.json() == {"items": [], "next_cursor": None, "max_active_runs": 2}


async def test_a_running_run_reads_the_fixed_reason_and_the_run_summary(api: Api) -> None:
    run = a_run()
    api.runs.add(run)
    api.engine.queue[run.id] = QueueEntry(
        run_id=run.id, engine_state="pending", position=None, enqueued_at=NOW
    )

    async with api.client() as client:
        response = await client.get(QUEUE)

    body = response.json()
    assert response.status_code == HTTP_OK
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["reason"] == "running"
    assert item["position"] is None
    assert item["run"]["id"] == str(run.id)
    assert item["waiting_since"] == "2026-09-07T00:00:00Z"


async def test_an_unauthenticated_request_is_refused(api: Api) -> None:
    async with api.anonymous() as client:
        response = await client.get(QUEUE)

    assert response.status_code == HTTP_UNAUTHORIZED
