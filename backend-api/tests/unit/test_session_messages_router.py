"""`POST /api/v1/runs/{run_id}/session/messages` and the turns `GET .../session` gains
(story 2-5, AD-23)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import signal_effect_ports
from orchestrator.api.providers_session import message_ports, session_ports
from orchestrator.api.routers import session as session_router
from orchestrator.application.use_cases.session_turn import EMPTY_MESSAGE, NO_SESSION
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.session_turn_fixtures import TurnWorld, a_turn_world

HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
HTTP_SERVER_ERROR = 500

RUNS = "/api/v1/runs"


class Api:
    def __init__(self, env: dict[str, str], world: TurnWorld) -> None:
        self.world = world
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[signal_effect_ports] = self._effect_ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _effect_ports(self) -> Iterator[SignalEffectPorts]:
        yield self.world.session.ports

    @property
    def messages(self) -> str:
        return f"{RUNS}/{self.world.session.world.run.id}/session/messages"

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, a_turn_world())


async def test_a_message_is_accepted_as_a_queued_turn(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(api.messages, json={"text": "Why is the route missing?"})

    assert response.status_code == HTTP_ACCEPTED, response.text
    body = response.json()
    assert (body["turn"], body["status"], body["message"]) == (
        1,
        "queued",
        "Why is the route missing?",
    )
    assert (body["reply"], body["ended_at"], body["exit_code"], body["cost_usd"]) == (
        "",
        None,
        None,
        None,
    )
    (turn,) = api.world.session.world.attempts_of("stories[0].build")
    assert body["attempt_id"] == str(turn.id)
    assert body["started_at"].endswith("Z")


async def test_the_session_reads_its_turns(api: Api) -> None:
    async with api.client() as client:
        await client.post(api.messages, json={"text": "Why?"})
        read = await client.get(f"{RUNS}/{api.world.session.world.run.id}/session")

    body = read.json()
    assert body["turn_running"] is True
    assert [(turn["turn"], turn["message"], turn["status"]) for turn in body["turns"]] == [
        (1, "Why?", "queued")
    ]
    assert body["turns"][0]["ended_at"] is None


async def test_a_message_with_no_session_is_a_409(env: dict[str, str]) -> None:
    api = Api(env, a_turn_world(start=False))

    async with api.client() as client:
        response = await client.post(api.messages, json={"text": "Why?"})

    assert response.status_code == HTTP_CONFLICT
    assert response.json()["detail"] == NO_SESSION


async def test_an_empty_message_is_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(api.messages, json={"text": "  "})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["detail"] == EMPTY_MESSAGE


async def test_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(f"{RUNS}/{new_id()}/session/messages", json={"text": "go"})

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_failed_enqueue_is_a_500_and_closes_the_turn(api: Api) -> None:
    api.world.session.world.engine.session_turn_error = RuntimeError("queue unavailable")

    async with api.client() as client:
        response = await client.post(api.messages, json={"text": "go"})

    assert response.status_code == HTTP_SERVER_ERROR
    assert response.headers["content-type"].startswith("application/problem+json")
    (turn,) = api.world.session.world.attempts_of("stories[0].build")
    assert (turn.status, turn.output_ref) == ("error", "queue unavailable")


def test_the_route_declares_its_problem_documents() -> None:
    assert set(session_router.MESSAGE_REFUSALS) == {
        HTTP_NOT_FOUND,
        HTTP_CONFLICT,
        HTTP_UNPROCESSABLE,
        HTTP_SERVER_ERROR,
    }


def test_the_provider_carries_the_signal_writers_and_engine() -> None:
    world = a_turn_world()
    ports = world.session.ports

    built = message_ports(ports)

    assert built.writers is ports.signal.writers
    assert built.engine is ports.signal.engine
    assert session_ports(ports).writers is ports.signal.writers
