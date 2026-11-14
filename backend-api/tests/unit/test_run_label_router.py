"""`PATCH /api/v1/runs/{id}` and the label on every Run payload (story 3; AC4-AC6)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_read_ports
from orchestrator.api.providers_run_label import run_label_ports
from orchestrator.api.routers import run_label as router_module
from orchestrator.api.schemas.runs import RunIn, RunSummaryOut
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_label import RunLabelPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
PROBLEM = "application/problem+json"
RUNS = "/api/v1/runs"
NOW = datetime(2026, 11, 10, 10, 23, 41, tzinfo=UTC)
PROJECT_ID = UUID(int=9)


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": new_id(),
        "template_name": "bench",
        "template_version": 1,
        "status": "cancelled",
        "budget_usd": Decimal("10"),
        "inputs": {"base_branch": "main", "initiative_folder": "initiatives/snake"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository()
        self.uow = FakeUnitOfWork()
        self.projects = FakeProjectRepository(
            [
                Project(
                    id=PROJECT_ID,
                    slug="familio",
                    name="familio",
                    context_text="",
                    context_paths=(),
                    env_vars_enc=(),
                    log_prompt_content=False,
                    created_at=NOW,
                    updated_at=NOW,
                )
            ]
        )
        self.app: FastAPI = create_app(settings)
        self.app.dependency_overrides[run_label_ports] = self._label_ports
        self.app.dependency_overrides[run_read_ports] = lambda: RunReadPorts(
            runs=self.runs,
            steps=FakeStepRunRepository(),
            projects=self.projects,
            repositories=FakeRepositoryRepository(),
        )
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _label_ports(self):  # type: ignore[no-untyped-def]
        with self.uow:
            yield RunLabelPorts(
                runs=self.runs,
                steps=FakeStepRunRepository(),
                projects=self.projects,
                uow=self.uow,
            )

    def client(self, *, auth: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if auth else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_a_cancelled_run_takes_a_label_and_stays_cancelled(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.patch(
            f"{RUNS}/{run.id}", json={"label": "snake round 2 · story session"}
        )

    body = response.json()
    assert response.status_code == HTTP_OK
    assert body["label"] == "snake round 2 · story session"
    assert body["label_set_by_operator"] is True
    assert body["status"] == "cancelled"


async def test_null_restores_the_default(api: Api) -> None:
    run = a_run(label="mine", label_set_by_operator=True)
    api.runs.add(run)

    async with api.client() as client:
        response = await client.patch(f"{RUNS}/{run.id}", json={"label": None})

    body = response.json()
    assert response.status_code == HTTP_OK
    assert body["label"] == "familio snake bench 2026-11-10 10:23"
    assert body["label_set_by_operator"] is False


@pytest.mark.parametrize("label", ["x" * 121, "", "   "])
async def test_an_out_of_bounds_label_is_a_problem_and_changes_nothing(
    api: Api, label: str
) -> None:
    run = a_run(label="kept")
    api.runs.add(run)

    async with api.client() as client:
        response = await client.patch(f"{RUNS}/{run.id}", json={"label": label})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM)
    assert api.runs.runs[run.id].label == "kept"


async def test_an_unknown_run_is_a_404_problem(api: Api) -> None:
    async with api.client() as client:
        response = await client.patch(f"{RUNS}/{new_id()}", json={"label": "x"})

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_the_bearer_is_required(api: Api) -> None:
    async with api.client(auth=False) as client:
        response = await client.patch(f"{RUNS}/{new_id()}", json={"label": "x"})

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_get_and_the_board_carry_the_label(api: Api) -> None:
    run = a_run(label="snake", label_set_by_operator=True, status="queued")
    api.runs.add(run)

    async with api.client() as client:
        one = (await client.get(f"{RUNS}/{run.id}")).json()
        board = (await client.get(RUNS, params={"view": "board"})).json()

    assert (one["label"], one["label_set_by_operator"]) == ("snake", True)
    card = board["columns"]["queued"][0]
    assert (card["label"], card["label_set_by_operator"]) == ("snake", True)


def test_the_create_body_passes_the_label_through_and_the_summary_echoes_it() -> None:
    body = RunIn(
        template_name="t",
        template_version=1,
        project_id=PROJECT_ID,
        repository_id=new_id(),
        base_branch="main",
        label="mine",
    )

    assert body.as_request().label == "mine"
    assert RunSummaryOut.of(a_run(label="mine")).label == "mine"


def test_the_router_declares_exactly_the_patch() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["PATCH"], "/runs/{run_id}")]


@pytest.mark.parametrize("raw", [r'{"label": "snake\u0000round"}', r'{"label": "snake \ud800"}'])
async def test_a_label_a_text_column_cannot_hold_is_a_problem(api: Api, raw: str) -> None:
    run = a_run(label="kept")
    api.runs.add(run)

    async with api.client() as client:
        response = await client.patch(
            f"{RUNS}/{run.id}", content=raw, headers={"content-type": "application/json"}
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM)
    assert api.runs.runs[run.id].label == "kept"
