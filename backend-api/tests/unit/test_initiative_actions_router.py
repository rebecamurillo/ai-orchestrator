"""`POST /initiatives`, `/{id}/cancel`, `/{id}/start-next` over ASGI on the shared fakes
(story 5, epic 7, AC1-AC9)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers_initiatives import initiative_ports, initiative_read_ports
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.initiative_world import InitiativeWorld
from tests.unit.application.test_initiative_start_next import SEQ, parked
from tests.unit.fakes.workspace import FakeWorkspace

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
PROBLEM = "application/problem+json"
LIST = "/api/v1/initiatives"
NOT_FORCEABLE_START = "start-next refused: the next step is not a conversation step"
NO_CONVERSATION = "no conversation step is open"


class Harness:
    def __init__(self, env: dict[str, str]) -> None:
        self.world = InitiativeWorld()
        self.token = env["ORCHESTRATOR_TOKEN"]
        self.app: FastAPI = create_app(Settings())
        self.app.dependency_overrides[initiative_ports] = self._write
        self.app.dependency_overrides[initiative_read_ports] = self._read

    def _write(self) -> Iterator[InitiativePorts]:
        with self.world.uow:
            yield self.world.ports

    def _read(self) -> InitiativeReadPorts:
        world = self.world
        return InitiativeReadPorts(
            initiatives=world.initiatives,
            advances=world.advances,
            projects=world.projects,
            repositories=world.repositories,
            runs=world.runs,
            initiative_runs=world.runs,
            steps=world.signals.writers.steps,
            attempts=world.signals.writers.attempts,
            git=world.git,
            workspace=lambda path: FakeWorkspace(path, {}),
            clock=world.harness.clock,
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def body(self, **overrides: Any) -> dict[str, Any]:
        values: dict[str, Any] = {
            "project_id": str(self.world.project.id),
            "name": "Snake v3",
            "first_message": "hello",
        }
        values.update(overrides)
        return values


@pytest.fixture
def harness(env: dict[str, str]) -> Harness:
    return Harness(env)


async def test_a_create_answers_201_with_the_new_initiatives_detail(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.post(LIST, json=harness.body())

    body = response.json()
    assert response.status_code == HTTP_CREATED
    assert body["slug"] == "snake-v3"
    assert len(body["runs"]) == 1
    assert body["status"]


async def test_an_unknown_project_is_a_404_problem(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.post(LIST, json=harness.body(project_id=str(new_id())))

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_a_held_slug_is_a_409_naming_the_holder(harness: Harness) -> None:
    holder = harness.world.seed(harness.world.initiative())

    async with harness.client() as client:
        response = await client.post(LIST, json=harness.body())

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM)
    assert f"{holder.name} ({holder.id})" in response.json()["detail"]


@pytest.mark.parametrize("change", [{"extra": 1}, {"first_message": None}])
async def test_a_bad_create_body_is_a_422_and_creates_nothing(
    harness: Harness, change: dict[str, Any]
) -> None:
    body = harness.body(**change)
    if body.get("first_message") is None:
        del body["first_message"]

    async with harness.client() as client:
        response = await client.post(LIST, json=body)

    assert response.status_code == HTTP_UNPROCESSABLE
    assert harness.world.initiatives.initiatives == {}
    assert harness.world.runs.runs == {}


async def test_a_cancel_answers_the_cancelled_detail_then_refuses_a_second(
    harness: Harness,
) -> None:
    initiative, _ = parked(harness.world)
    url = f"{LIST}/{initiative.id}/cancel"

    async with harness.client() as client:
        first = await client.post(url)
        second = await client.post(url)
        unknown = await client.post(f"{LIST}/{new_id()}/cancel")

    assert first.status_code == HTTP_OK
    assert first.json()["status"] == "cancelled"
    assert second.status_code == HTTP_CONFLICT
    assert second.headers["content-type"].startswith(PROBLEM)
    assert unknown.status_code == HTTP_NOT_FOUND


async def test_start_next_forces_the_skip_at_the_stop_and_answers_the_detail(
    harness: Harness,
) -> None:
    initiative, run = parked(harness.world)

    async with harness.client() as client:
        response = await client.post(f"{LIST}/{initiative.id}/start-next", json={"park_seq": SEQ})

    assert response.status_code == HTTP_OK
    assert response.json()["id"] == str(initiative.id)
    signals = [args for call, args in harness.world.engine.calls if call == "signal"]
    assert len(signals) == 1
    run_id, signal = signals[0]  # type: ignore[misc]
    assert run_id == run.id
    assert (signal.kind, signal.stop, signal.payload) == ("skip_step", SEQ, {"forced": True})


async def test_a_stale_stop_is_a_409_and_nothing_is_sent(harness: Harness) -> None:
    initiative, run = parked(harness.world)

    async with harness.client() as client:
        response = await client.post(
            f"{LIST}/{initiative.id}/start-next", json={"park_seq": SEQ + 1}
        )

    assert response.status_code == HTTP_CONFLICT
    assert harness.world.engine.calls == []
    assert harness.world.runs.runs[run.id] == run


async def test_the_gate_is_never_forced(harness: Harness) -> None:
    initiative, _ = parked(harness.world, "tech")

    async with harness.client() as client:
        response = await client.post(f"{LIST}/{initiative.id}/start-next", json={"park_seq": SEQ})

    assert response.status_code == HTTP_CONFLICT
    assert response.json()["detail"].startswith(NOT_FORCEABLE_START)
    assert harness.world.engine.calls == []


async def test_no_open_conversation_is_a_409_and_an_unknown_initiative_a_404(
    harness: Harness,
) -> None:
    initiative, _ = parked(harness.world, status="running", park_kind=None, park_path=None)

    async with harness.client() as client:
        none_open = await client.post(f"{LIST}/{initiative.id}/start-next", json={"park_seq": SEQ})
        unknown = await client.post(f"{LIST}/{new_id()}/start-next", json={"park_seq": SEQ})

    assert none_open.status_code == HTTP_CONFLICT
    assert none_open.json()["detail"] == NO_CONVERSATION
    assert unknown.status_code == HTTP_NOT_FOUND


@pytest.mark.parametrize("body", [{"park_seq": "1"}, {"park_seq": True}, {"park_seq": 1, "x": 1}])
async def test_a_bad_start_next_body_is_a_422(harness: Harness, body: dict[str, Any]) -> None:
    async with harness.client() as client:
        response = await client.post(f"{LIST}/{UUID(int=1)}/start-next", json=body)

    assert response.status_code == HTTP_UNPROCESSABLE
