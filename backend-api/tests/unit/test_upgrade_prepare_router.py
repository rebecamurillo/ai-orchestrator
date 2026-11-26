"""`POST /api/v1/instance/upgrade-prepare` over an ASGI transport (epic 9 story 3, AC1-AC3, AC8)."""

from __future__ import annotations

import inspect
from collections.abc import Iterator

import httpx
from fastapi import FastAPI

from orchestrator.api import providers_instance
from orchestrator.api.providers_instance import upgrade_ports
from orchestrator.application.use_cases.upgrade_prepare import NO_HOLD, UpgradePorts
from orchestrator.infrastructure.mcp.tools import ALLOWED_OPERATION_IDS
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.initiative_transition_world import TransitionWorld
from tests.unit.application.test_upgrade_prepare import hold_for, parked_at
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository

URL = "/api/v1/instance/upgrade-prepare"
CONFLICT = 409


class Api:
    def __init__(self, env: dict[str, str], *, held: bool) -> None:
        self.world = TransitionWorld()
        self.run = parked_at(self.world, "ux")
        holds = hold_for(self.world) if held else FakeInstanceHoldRepository()
        self.ports = UpgradePorts(initiative=self.world.ports, holds=holds)
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[upgrade_ports] = self.provide
        self.token = env["ORCHESTRATOR_TOKEN"]

    def provide(self) -> Iterator[UpgradePorts]:
        with self.world.uow:
            yield self.ports

    def client(self, *, bearer: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if bearer else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )


async def test_a_hold_and_a_parked_conversation_answer_200_with_the_list(
    env: dict[str, str],
) -> None:
    api = Api(env, held=True)

    async with api.client() as client:
        response = await client.post(URL)

    assert response.status_code == 200  # noqa: PLR2004
    assert response.json() == {
        "cancelled": [
            {
                "run_id": str(api.run.id),
                "initiative_id": str(api.world.initiative_row.id),
                "step": "ux",
            }
        ]
    }


async def test_no_hold_answers_409_problem_json(env: dict[str, str]) -> None:
    api = Api(env, held=False)

    async with api.client() as client:
        response = await client.post(URL)

    assert response.status_code == CONFLICT
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == NO_HOLD
    assert api.world.runs.runs[api.run.id].status == "needs_you"


async def test_a_refusal_answers_409_problem_json(env: dict[str, str]) -> None:
    api = Api(env, held=True)
    api.world.ended_run(1, status="needs_you", park_kind="merge_conflict")

    async with api.client() as client:
        response = await client.post(URL)

    assert response.status_code == CONFLICT
    assert response.json()["detail"].startswith("upgrade-prepare refused:")
    assert api.world.runs.runs[api.run.id].status == "needs_you"


async def test_a_request_without_the_bearer_is_refused(env: dict[str, str]) -> None:
    async with Api(env, held=True).client(bearer=False) as client:
        assert (await client.post(URL)).status_code == 401  # noqa: PLR2004


def test_the_provider_is_a_generator_function() -> None:
    assert inspect.isgeneratorfunction(providers_instance.upgrade_ports)


def test_the_operation_publishes_its_responses(env: dict[str, str]) -> None:
    api = Api(env, held=True)

    responses = api.app.openapi()["paths"][URL]["post"]["responses"]

    assert {"200", "401", "409", "422"} <= set(responses)


def test_it_is_not_an_mcp_tool() -> None:
    assert not any("upgrade" in op for op in ALLOWED_OPERATION_IDS)
