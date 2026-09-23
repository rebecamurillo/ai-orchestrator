"""The four initiative routes over an ASGI transport (multi-repo initiative S6/S8, AD-12,
AD-13).

The rules are asserted in `tests/unit/application/initiatives/`; what only a request can
show is here: the route shape, the status each operation answers with, the payload each
result becomes, and the problem document each refusal becomes.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers_initiatives import (
    dispatch_ports,
    initiative_preflight_ports,
    initiative_read_ports,
    initiative_signal_ports,
)
from orchestrator.api.routers import initiatives as router_module
from orchestrator.api.schemas import initiatives as schema_module
from orchestrator.application.use_cases.dispatch_initiative import DispatchPorts
from orchestrator.application.use_cases.initiative_view import InitiativeReadPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.initiatives import fixtures as fx

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
PROBLEM_MEDIA_TYPE = "application/problem+json"

INITIATIVES = "/api/v1/initiatives"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


class Api:
    """One application, one dispatch harness, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str], **harness: object) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.harness = fx.Harness(**harness)  # type: ignore[arg-type]
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[initiative_preflight_ports] = self._read
        self.app.dependency_overrides[dispatch_ports] = self._dispatch
        self.app.dependency_overrides[initiative_read_ports] = self._view
        self.app.dependency_overrides[initiative_signal_ports] = self._signal
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _read(self) -> PreflightPorts:
        yield self.harness.preflight

    def _dispatch(self) -> DispatchPorts:
        with self.harness.uow:
            yield self.harness.ports

    def _view(self) -> InitiativeReadPorts:
        yield InitiativeReadPorts(runs=self.harness.runs, repositories=self.harness.repositories)

    def _signal(self) -> SignalPorts:
        yield SignalPorts(writers=self.harness.writers, engine=self.harness.engine)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


def body(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project_id": str(fx.PROJECT_ID),
        "repository_id": str(fx.HUB_ID),
        "base_branch": fx.MAIN,
        "initiative_folder": fx.INITIATIVE_FOLDER,
        "epic_template": fx.EPIC_TEMPLATE,
        "merge_template": fx.MERGE_TEMPLATE,
        "golive_template": fx.GOLIVE_TEMPLATE,
        "budget_usd_per_epic": "25",
    }
    payload.update(overrides)
    return payload


# ── the route shape ───────────────────────────────────────────────────────────


def test_the_router_declares_exactly_the_four_operations() -> None:
    """Revised for multi-repo initiative S8, 2026-09-23: `POST /initiatives/{slug}/signals`
    (AD-13's spine amendment — "the only signal surface above a single Run") is the fourth
    operation this router now declares, exactly where S6's own module docstring said it
    would land ("`POST /initiatives/{slug}/signals` is the fourth and belongs to a later
    story"). The assertion widens from three routes to four; every other row is unchanged."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [
        (["POST"], "/initiatives/preflight"),
        (["POST"], "/initiatives"),
        (["GET"], "/initiatives/{slug}"),
        (["POST"], "/initiatives/{slug}/signals"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


def test_the_literal_preflight_path_is_registered_before_the_slug_one() -> None:
    """Starlette matches in registration order; `run.py` is the precedent for the rule."""
    paths = [route.path for route in router_module.router.routes]

    assert paths.index("/initiatives/preflight") < paths.index("/initiatives/{slug}")


# ── pre-flight ────────────────────────────────────────────────────────────────


async def test_pre_flight_answers_the_lines_the_repo_table_and_the_order(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(f"{INITIATIVES}/preflight", json=body())

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert payload["slug"] == fx.SLUG
    assert payload["start_allowed"] is True
    assert payload["order"] == ["web-1", "api-1"]
    assert [row["repository"] for row in payload["repos"]] == ["web", "api"]
    assert [epic["epic_id"] for epic in payload["epics"]] == ["web-1", "api-1"]
    assert payload["epics"][0]["lines"]


async def test_pre_flight_reports_a_refusal_as_data_rather_than_a_status(
    env: dict[str, str],
) -> None:
    """A pre-flight that refuses is still a 200 (NFR-2): the lines are what it is for."""
    refusing = Api(env, specs=(fx.WEB_SPEC,))

    async with refusing.client() as client:
        response = await client.post(f"{INITIATIVES}/preflight", json=body())

    assert response.status_code == HTTP_OK
    assert response.json()["start_allowed"] is False


async def test_pre_flight_writes_nothing(api: Api) -> None:
    async with api.client() as client:
        await client.post(f"{INITIATIVES}/preflight", json=body())

    assert api.harness.runs.runs == {}


# ── dispatch ──────────────────────────────────────────────────────────────────


async def test_a_dispatch_answers_201_with_every_member_run(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(INITIATIVES, json=body())

    assert response.status_code == HTTP_CREATED
    payload = response.json()
    assert payload["slug"] == fx.SLUG
    assert [(m["role"], m["epic_id"]) for m in payload["members"]] == [
        ("epic", "web-1"),
        ("merge", "web-1"),
        ("epic", "api-1"),
        ("merge", "api-1"),
        ("golive", None),
    ]
    assert payload["started"] == ["web-1"]
    assert payload["members"][1]["after_run_ids"] == [payload["members"][0]["run_id"]]


async def test_a_refused_dispatch_is_a_problem_document_naming_the_line(
    env: dict[str, str],
) -> None:
    refusing = Api(env, specs=(fx.WEB_SPEC,))

    async with refusing.client() as client:
        response = await client.post(INITIATIVES, json=body())

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert "spec folder" in response.json()["detail"]


async def test_a_project_nothing_is_stored_under_is_a_404_problem(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(INITIATIVES, json=body(project_id=UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── the read model ────────────────────────────────────────────────────────────


async def test_the_read_answers_one_object_with_the_repos_and_the_members(api: Api) -> None:
    async with api.client() as client:
        await client.post(INITIATIVES, json=body())
        response = await client.get(f"{INITIATIVES}/{fx.SLUG}")

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert set(payload) == {"slug", "repos", "members"}
    assert [m["role"] for m in payload["members"]] == [
        "epic",
        "merge",
        "epic",
        "merge",
        "golive",
    ]
    assert payload["members"][0]["park_kind"] is None
    assert [row["repository"] for row in payload["repos"]] == ["web", "api", "hub"]


async def test_a_slug_nothing_was_dispatched_under_is_a_404_problem(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{INITIATIVES}/never-dispatched")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── initiative-wide cancel (S8, AD-13) ───────────────────────────────────────────


async def test_a_cancel_signals_every_member_the_dispatch_created(api: Api) -> None:
    async with api.client() as client:
        dispatched = (await client.post(INITIATIVES, json=body())).json()
        response = await client.post(f"{INITIATIVES}/{fx.SLUG}/signals", json={"kind": "cancel"})

    assert response.status_code == HTTP_OK
    payload = response.json()
    assert set(payload["signalled"]) == {m["run_id"] for m in dispatched["members"]}
    assert payload["skipped"] == []
    for run_id in payload["signalled"]:
        assert api.harness.runs.runs[UUID(run_id)].status == "cancelled"


async def test_a_kind_other_than_cancel_is_a_422_problem(api: Api) -> None:
    async with api.client() as client:
        await client.post(INITIATIVES, json=body())
        response = await client.post(f"{INITIATIVES}/{fx.SLUG}/signals", json={"kind": "retry"})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_slug_nothing_was_dispatched_under_refuses_the_signal_as_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(
            f"{INITIATIVES}/never-dispatched/signals", json={"kind": "cancel"}
        )

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── the contract ──────────────────────────────────────────────────────────────


def test_the_body_defaults_the_three_template_names(env: dict[str, str]) -> None:
    payload = schema_module.InitiativeIn(
        project_id=fx.PROJECT_ID,
        repository_id=fx.HUB_ID,
        base_branch=fx.MAIN,
        initiative_folder=fx.INITIATIVE_FOLDER,
    )

    assert payload.as_request().templates == ("epic", "merge", "golive")


async def test_every_published_operation_declares_the_problem_media_type(api: Api) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    paths = (
        f"{INITIATIVES}/preflight",
        INITIATIVES,
        INITIATIVES + "/{slug}",
        INITIATIVES + "/{slug}/signals",
    )
    for path in paths:
        operations = document["paths"][path]
        for operation in operations.values():
            assert "401" in operation["responses"], path
