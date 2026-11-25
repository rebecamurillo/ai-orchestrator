"""`GET /initiatives/{id}?opened=true` over ASGI on the shared fakes (story 6, epic 7; AC5)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers_initiatives import initiative_read_ports, open_initiative_ports
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.application.use_cases.open_initiative import OpenInitiativePorts
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.initiative_read_world import FOLDER, WORKTREE, ReadWorld
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.git import FakeGit

HTTP_OK = 200
HTTP_NOT_FOUND = 404
PRD = f"{FOLDER}/snake/PRD.md"
OPENED = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)
TURN_ENDED = datetime(2026, 11, 24, 21, 30, tzinfo=UTC)
FIRST_READ = datetime(2026, 11, 24, 22, 0, tzinfo=UTC)


class RecordingUow:
    def commit(self) -> None:
        pass


class Harness:
    def __init__(self, env: dict[str, str]) -> None:
        self.world = ReadWorld(git=FakeGit(changes={WORKTREE: (Change(PRD, "added"),)}))
        self.token = env["ORCHESTRATOR_TOKEN"]
        self.app: FastAPI = create_app(Settings())
        self.app.dependency_overrides[initiative_read_ports] = self._reads
        self.app.dependency_overrides[open_initiative_ports] = self._opens

    def _reads(self) -> InitiativeReadPorts:
        return self.world.ports

    def _opens(self, opened: bool = False) -> Iterator[OpenInitiativePorts | None]:
        if not opened:
            yield None
            return
        yield OpenInitiativePorts(self.world.initiatives, RecordingUow(), self.world.clock)  # type: ignore[arg-type]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def harness(env: dict[str, str]) -> Harness:
    return Harness(env)


def snapshot(world: ReadWorld) -> tuple[object, ...]:
    return (
        dict(world.runs.runs),
        dict(world.steps.steps),
        dict(world.attempts.attempts),
        dict(world.records.records),
    )


def seeded(harness: Harness) -> str:
    world = harness.world
    initiative = world.initiative(last_opened_at=OPENED)
    run = world.run(initiative, status="running", worktree_path=WORKTREE)
    row = world.row(run, 1, status="running")
    world.turn(row, 1, start_sha="a", end_sha="b", ended_at=TURN_ENDED)
    world.clock = FakeClock(FIRST_READ)
    return f"/api/v1/initiatives/{initiative.id}"


def file_of(body: dict[str, object]) -> dict[str, object]:
    return body["workflows"][0]["steps"][0]["files"][0]  # type: ignore[index, return-value]


async def test_ac5_an_opened_read_marks_the_files_changed_since_the_previous_view(
    harness: Harness,
) -> None:
    path = seeded(harness)

    async with harness.client() as client:
        first = (await client.get(f"{path}?opened=true")).json()
        harness.world.clock.advance(60)
        second = (await client.get(f"{path}?opened=true")).json()

    assert file_of(first)["changed"] is True
    assert file_of(first)["time"] == "2026-11-24T21:30:00Z"
    assert file_of(first)["run_id"] is not None
    assert first["last_opened_at"] == "2026-11-24T22:00:00Z"
    assert file_of(second)["changed"] is False
    assert second["last_opened_at"] == "2026-11-24T22:01:00Z"


async def test_ac5_a_plain_read_writes_nothing(harness: Harness) -> None:
    path = seeded(harness)
    world = harness.world
    before = snapshot(world)

    async with harness.client() as client:
        body = (await client.get(path)).json()

    assert body["last_opened_at"] == "2026-11-24T21:00:00Z"
    assert file_of(body)["changed"] is True
    assert not [c for c in world.initiatives.calls if c[0] in ("update", "get_for_update")]
    assert snapshot(world) == before


async def test_the_body_carries_the_header_keys(harness: Harness) -> None:
    path = seeded(harness)

    async with harness.client() as client:
        body = (await client.get(path)).json()

    assert body["folder"] == f"{FOLDER}/snake"
    assert body["project"]["name"] == harness.world.project.name
    assert body["hub"]["slug"] == harness.world.hub.slug
    assert body["current_position"] == 1
    assert body["workflow_count"] == len(body["workflows"])
    assert body["sequence_fixed_at"] == body["created_at"]
    assert {"owners", "sessions", "current_step"} <= set(body)


@pytest.mark.parametrize("query", ["", "?opened=true"])
async def test_ac5_an_unknown_id_is_a_404_problem(harness: Harness, query: str) -> None:
    async with harness.client() as client:
        response = await client.get(f"/api/v1/initiatives/{new_id()}{query}")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith("application/problem+json")
