"""`GET /api/v1/harnesses` over an ASGI transport (SPEC CAP-3, AD-10)."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import harness_ports
from orchestrator.api.routers import harnesses as router_module
from orchestrator.api.schemas.harnesses import HarnessOut
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.domain.entities.harness import Harness
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.harnesses import FakeHarnessRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"
HARNESSES = "/api/v1/harnesses"


class Api:
    """One application, one fake repository, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.harnesses = FakeHarnessRepository()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[harness_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> HarnessPorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return HarnessPorts(uow=self.uow, harnesses=self.harnesses)

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


async def test_lists_every_seeded_harness(api: Api) -> None:
    api.harnesses.add(Harness(name="claude", enabled=True, version_pin="2.1.258"))
    api.harnesses.add(Harness(name="codex", version_pin="0.152.1"))

    async with api.client() as client:
        response = await client.get(HARNESSES)

    assert response.status_code == HTTP_OK
    items = response.json()["items"]
    assert {item["name"]: item["enabled"] for item in items} == {"claude": True, "codex": False}


async def test_answers_an_empty_list_before_any_seed(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(HARNESSES)

    assert response.status_code == HTTP_OK
    assert response.json() == {"items": [], "next_cursor": None}


async def test_without_the_bearer_is_a_401(api: Api) -> None:
    async with api.anonymous() as client:
        response = await client.get(HARNESSES)

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_the_path_publishes_a_get(api: Api) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "get" in document["paths"][HARNESSES]


def test_the_router_declares_exactly_one_route_with_no_dependency_of_its_own() -> None:
    """The bearer comes from the mount (AD-4), never from a route."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/harnesses")]
    for route in router_module.router.routes:
        assert route.dependencies == []


def test_harness_out_of_renders_every_field() -> None:
    out = HarnessOut.of(
        Harness(name="claude", enabled=True, failing_check=None, version_pin="2.1.258")
    )

    assert out.model_dump() == {
        "name": "claude",
        "enabled": True,
        "last_readiness_at": None,
        "failing_check": None,
        "version_pin": "2.1.258",
    }
