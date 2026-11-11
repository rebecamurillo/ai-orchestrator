"""`GET /api/v1/instance/activity` (SPEC CAP-3, AD-30) over an ASGI transport."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers_instance import activity_ports
from orchestrator.api.routers import instance as router_module
from orchestrator.api.schemas.instance import InstanceActivityOut
from orchestrator.application.use_cases.instance_activity import (
    ActivityPorts,
    HoldView,
    InstanceActivity,
)
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

ACTIVITY = "/api/v1/instance/activity"
NOW = datetime(2026, 11, 11, tzinfo=UTC)


class Api:
    def __init__(self, env: dict[str, str], version: str = "1") -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.ports = ActivityPorts(
            queue=QueuePorts(
                engine=FakeWorkflowEngine(),
                runs=FakeRunRepository(),
                steps=FakeStepRunRepository(),
                clock=FakeClock(NOW),
                max_active_runs=2,
            ),
            attempts=FakeAttemptRepository(),
            dbos_application_version=version,
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[activity_ports] = lambda: self.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self, *, bearer: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if bearer else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, "2")


def test_the_router_declares_exactly_one_operation() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/instance/activity")]


async def test_no_runs_answers_the_four_keys(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(ACTIVITY)

    assert response.status_code == 200  # noqa: PLR2004
    assert response.json() == {
        "working": [],
        "in_engine": [],
        "hold": None,
        "dbos_application_version": "2",
    }


async def test_a_request_without_the_bearer_is_refused(api: Api) -> None:
    async with api.client(bearer=False) as client:
        response = await client.get(ACTIVITY)

    assert response.status_code == 401  # noqa: PLR2004


def test_a_hold_renders_with_utc_timestamps() -> None:
    hold = HoldView(held_at=NOW, expires_at=NOW.replace(hour=1), reason="upgrade")

    out = InstanceActivityOut.of(
        InstanceActivity(working=[], in_engine=[], hold=hold, dbos_application_version="1")
    )

    assert out.model_dump(mode="json")["hold"] == {
        "held_at": "2026-11-11T00:00:00Z",
        "expires_at": "2026-11-11T01:00:00Z",
        "reason": "upgrade",
    }
