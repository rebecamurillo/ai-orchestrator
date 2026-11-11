"""`POST` and `DELETE /api/v1/instance/hold` over an ASGI transport (SPEC CAP-4, AD-30)."""

from __future__ import annotations

import inspect

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api import providers_instance
from orchestrator.api.providers_instance import hold_ports
from orchestrator.application.use_cases.instance_hold import HoldPorts
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.writer_fixtures import World, a_world, an_attempt
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository

HOLD = "/api/v1/instance/hold"
CREATED = 201
CONFLICT = 409
INVALID = 422


class Api:
    def __init__(self, env: dict[str, str], world: World) -> None:
        self.world = world
        self.holds = FakeInstanceHoldRepository()
        self.uow = FakeUnitOfWork()
        self.ports = HoldPorts(
            runs=world.ports.runs,
            steps=world.ports.steps,
            attempts=world.ports.attempts,
            holds=self.holds,
            uow=self.uow,
            clock=world.clock,
        )
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[hold_ports] = lambda: self.ports
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
    return Api(env, a_world("running", statuses={}))


async def test_a_free_instance_answers_201_with_the_hold(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(HOLD, json={"ttl_seconds": 600, "reason": "upgrade"})

    assert response.status_code == CREATED
    assert response.json() == {
        "held_at": "2026-01-01T00:00:00Z",
        "expires_at": "2026-01-01T00:10:00Z",
        "reason": "upgrade",
    }
    assert api.holds.hold is not None
    assert api.uow.committed is True


async def test_working_steps_answer_409_problem_json_and_write_nothing(env: dict[str, str]) -> None:
    world = a_world("running", statuses={"baseline": "running"})
    an_attempt(world, "plan", role="session")
    api = Api(env, world)

    async with api.client() as client:
        response = await client.post(HOLD, json={"ttl_seconds": 600, "reason": "upgrade"})

    assert response.status_code == CONFLICT
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert (body["type"], body["title"], body["status"]) == ("about:blank", "Conflict", CONFLICT)
    assert "2 working steps" in body["detail"]
    assert len(body["errors"]) == 2  # noqa: PLR2004
    for entry in body["errors"]:
        assert set(entry) == {"run_id", "run_label", "path", "kind", "started_at"}
    assert {entry["started_at"] for entry in body["errors"]} == {"2026-01-01T00:00:00Z", None}
    assert "put" not in api.holds.calls
    assert api.uow.committed is False


@pytest.mark.parametrize(
    "payload",
    [
        {"ttl_seconds": 0, "reason": "x"},
        {"ttl_seconds": 3601, "reason": "x"},
        {"ttl_seconds": 60, "reason": "r" * 201},
        {"ttl_seconds": 60},
    ],
)
async def test_an_invalid_body_answers_422_and_writes_nothing(
    api: Api, payload: dict[str, object]
) -> None:
    async with api.client() as client:
        response = await client.post(HOLD, json=payload)

    assert response.status_code == INVALID
    assert api.holds.calls == []


async def test_delete_answers_204_with_or_without_a_hold(api: Api) -> None:
    async with api.client() as client:
        await client.post(HOLD, json={"ttl_seconds": 60, "reason": "x"})
        first = await client.delete(HOLD)
        second = await client.delete(HOLD)

    assert (first.status_code, second.status_code) == (204, 204)
    assert api.holds.hold is None


async def test_both_routes_refuse_a_request_without_the_bearer(api: Api) -> None:
    async with api.client(bearer=False) as client:
        post = await client.post(HOLD, json={"ttl_seconds": 60, "reason": "x"})
        delete = await client.delete(HOLD)

    assert (post.status_code, delete.status_code) == (401, 401)


def test_the_hold_provider_is_a_generator_function() -> None:
    assert inspect.isgeneratorfunction(providers_instance.hold_ports)


def test_the_409_documents_its_schema_under_the_media_type_it_answers_with(api: Api) -> None:
    conflict = api.app.openapi()["paths"][HOLD]["post"]["responses"]["409"]

    assert conflict["content"]["application/problem+json"] == {
        "schema": {"$ref": "#/components/schemas/HoldConflictOut"}
    }
