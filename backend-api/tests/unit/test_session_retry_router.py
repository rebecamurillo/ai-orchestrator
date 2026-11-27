"""`POST /api/v1/runs/{run_id}/session/retry` (epic 4 story 6, AC5, AC6)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import signal_effect_ports
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.mcp.tools import ALLOWED_OPERATION_IDS
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.session_fixtures import BUILD
from tests.unit.application.session_turn_fixtures import TurnWorld, a_turn_world

HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
HTTP_SERVER_ERROR = 500
PROBLEM = "application/problem+json"
RUNS = "/api/v1/runs"
PATH = "/api/v1/runs/{run_id}/session/retry"


class Api:
    def __init__(self, env: dict[str, str], world: TurnWorld) -> None:
        self.world = world
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[signal_effect_ports] = self._effect_ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _effect_ports(self) -> Iterator[SignalEffectPorts]:
        yield self.world.session.ports

    @property
    def retry(self) -> str:
        return f"{RUNS}/{self.world.session.world.run.id}/session/retry"

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


def failed(world: TurnWorld) -> TurnWorld:
    world.session.turn(1, session_id="s-1", message="one")
    world.session.turn(2, session_id="s-1", message="two", status="error")
    return world


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, failed(a_turn_world()))


async def test_a_retry_answers_201_with_the_queued_turn(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(api.retry)

    assert response.status_code == HTTP_CREATED, response.text
    body = response.json()
    assert (body["turn"], body["status"], body["message"]) == (3, "queued", "two")
    newest = max(api.world.session.world.attempts_of(BUILD), key=lambda a: a.n)
    assert body["attempt_id"] == str(newest.id)


@pytest.mark.parametrize("case", ["done", "open", "none", "no_session"])
async def test_each_refusal_is_a_409_problem(env: dict[str, str], case: str) -> None:
    world = a_turn_world()
    if case == "done":
        world.session.turn(1, message="one")
    if case == "open":
        world.session.turn(1, status="running", ended_at=None)
    if case == "no_session":
        failed(world)
        run = world.session.world.stored_run()
        world.session.world.ports.runs.update(run.model_copy(update={"senior_session": False}))
    api = Api(env, world)

    async with api.client() as client:
        response = await client.post(api.retry)

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_an_unknown_run_is_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(f"{RUNS}/{new_id()}/session/retry")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_a_non_uuid_id_is_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(f"{RUNS}/nope/session/retry")

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_an_enqueue_failure_is_500_and_the_turn_is_closed_error(api: Api) -> None:
    api.world.session.world.engine.session_turn_error = RuntimeError("queue unavailable")

    async with api.client() as client:
        response = await client.post(api.retry)

    assert response.status_code == HTTP_SERVER_ERROR
    newest = max(api.world.session.world.attempts_of(BUILD), key=lambda a: a.n)
    assert (newest.n, newest.status) == (3, "error")


def test_the_route_is_in_the_contract_and_an_mcp_tool(api: Api) -> None:
    operation = api.app.openapi()["paths"][PATH]["post"]

    assert operation["summary"] == "Restart the last failed turn"
    ref = operation["responses"]["201"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/SessionTurnOut")
    # Operator ruling 2026-11-27, MCP initiative tools: AD-23's "no MCP tool" is reversed, the
    # route is `retry_session`'s, and eight initiative and session operations join (36).
    assert operation["operationId"] in ALLOWED_OPERATION_IDS
    assert len(ALLOWED_OPERATION_IDS) == 36  # noqa: PLR2004
