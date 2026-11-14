"""`GET /api/v1/metrics/catalogue` over ASGI (story 1, RM-2)."""

from __future__ import annotations

import httpx
from fastapi.routing import APIRoute

from orchestrator.api.routers.metrics_catalogue import catalogue_port, router
from orchestrator.domain.ports.catalogue import CatalogueMethod
from orchestrator.infrastructure.metrics_catalogue import PackageCatalogue
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.catalogue import FakeCatalogue, catalogue_entry

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
URL = "/api/v1/metrics/catalogue"
ENTRY_KEYS = {
    "id",
    "label",
    "group",
    "level",
    "scopes",
    "unit",
    "source",
    "component_of",
    "additive",
    "missing_words",
    "limits",
    "fingerprint_group",
    "methods",
}


def _client(env: dict[str, str], *, bearer: bool, fake: FakeCatalogue | None) -> httpx.AsyncClient:
    app = create_app(Settings())
    if fake is not None:
        app.dependency_overrides[catalogue_port] = lambda: fake
    headers = {"Authorization": f"Bearer {env['ORCHESTRATOR_TOKEN']}"} if bearer else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://backend-api", headers=headers
    )


def test_the_router_declares_exactly_the_one_operation() -> None:
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert [(route.path, sorted(route.methods)) for route in routes] == [
        ("/metrics/catalogue", ["GET"])
    ]
    assert routes[0].summary


async def test_the_page_carries_every_field_of_every_entry(env: dict[str, str]) -> None:
    entry = catalogue_entry(
        component_of="tokens.output",
        limits="Harness only.",
        methods=(CatalogueMethod(n=1, description="d", parameters={"min_gap_seconds": 60}),),
    )
    async with _client(env, bearer=True, fake=FakeCatalogue((entry,))) as client:
        response = await client.get(URL)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["next_cursor"] is None
    (item,) = body["items"]
    assert set(item) == ENTRY_KEYS
    assert item["id"] == "cost.gateway"
    assert item["scopes"] == ["run", "epic"]
    assert item["component_of"] == "tokens.output"
    assert item["additive"] == "within_scope_type"
    assert item["methods"] == [{"n": 1, "description": "d", "parameters": {"min_gap_seconds": 60}}]


async def test_without_the_bearer_the_answer_is_401(env: dict[str, str]) -> None:
    async with _client(env, bearer=False, fake=FakeCatalogue()) as client:
        response = await client.get(URL)
    assert response.status_code == HTTP_UNAUTHORIZED


async def test_without_an_override_every_shipped_entry_is_returned(env: dict[str, str]) -> None:
    async with _client(env, bearer=True, fake=None) as client:
        response = await client.get(URL)

    assert response.status_code == HTTP_OK
    assert [item["id"] for item in response.json()["items"]] == [
        e.id for e in PackageCatalogue().entries()
    ]
