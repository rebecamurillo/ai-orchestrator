"""The Board cards and the Run detail carry the initiative fields over HTTP (story 4, epic 7):
AC9 and AC10."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_read_ports, run_view_ports
from orchestrator.application.use_cases.run_read_ports import RunReadPorts
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.initiative_read_world import ReadWorld
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.runs import FakeGateRecordRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HTTP_OK = 200
NINE_KEYS = {
    "run",
    "header",
    "alert",
    "steps",
    "stories",
    "cost",
    "gate_record",
    "admitted_signals",
    "summary",
}


class Harness:
    def __init__(self, env: dict[str, str]) -> None:
        self.world = ReadWorld()
        self.token = env["ORCHESTRATOR_TOKEN"]
        templates = FakeTemplateVersionRepository(
            [TemplateVersion(name="p/spec", version=2, yaml="type: interactive\n", hash="h")]
        )
        world = self.world
        self.read = RunReadPorts(
            runs=world.runs,
            steps=world.steps,
            projects=world.projects,
            repositories=world.repositories,
            attempts=world.attempts,
            initiatives=world.initiatives,
            templates=templates,
            workspace=world.workspace,
        )
        self.view = RunViewPorts(
            runs=world.runs,
            steps=world.steps,
            attempts=world.attempts,
            gate_records=FakeGateRecordRepository(),
            projects=world.projects,
            repositories=world.repositories,
            logs=FakeLogReader(),
            clock=world.clock,
            initiatives=world.initiatives,
            templates=templates,
            workspace=world.workspace,
        )
        self.app: FastAPI = create_app(Settings())
        self.app.dependency_overrides[run_read_ports] = lambda: self.read
        self.app.dependency_overrides[run_view_ports] = lambda: self.view

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def harness(env: dict[str, str]) -> Harness:
    return Harness(env)


async def test_a_spec_run_waiting_on_her_turn_is_a_running_card_with_its_initiative(
    harness: Harness,
) -> None:
    initiative = harness.world.initiative()
    run = harness.world.parked_spec(initiative)

    async with harness.client() as client:
        body = (await client.get("/api/v1/runs?view=board")).json()

    assert body["columns"]["needs_you"] == []
    assert body["counts"]["needs_you"] == 0
    (card,) = body["columns"]["running"]
    assert card["id"] == str(run.id)
    assert card["attention"] == "your_turn"
    assert card["template_type"] == "interactive"
    assert card["initiative"] == {
        "id": str(initiative.id),
        "slug": "snake",
        "step": "intake",
        "position": 1,
        "workflow_count": 2,
    }


async def test_the_detail_carries_the_same_initiative_and_template_type(harness: Harness) -> None:
    initiative = harness.world.initiative()
    run = harness.world.parked_spec(initiative)

    async with harness.client() as client:
        body = (await client.get(f"/api/v1/runs/{run.id}/detail")).json()

    assert body["initiative"]["slug"] == "snake"
    assert body["initiative"]["step"] == "intake"
    assert body["template_type"] == "interactive"


async def test_a_run_outside_an_initiative_omits_both_detail_keys(harness: Harness) -> None:
    run = harness.world.run(
        harness.world.initiative(),
        initiative_id=None,
        initiative_position=None,
        template_name="unstored",
    )

    async with harness.client() as client:
        response = await client.get(f"/api/v1/runs/{run.id}/detail")

    assert response.status_code == HTTP_OK
    assert set(response.json()) == NINE_KEYS
