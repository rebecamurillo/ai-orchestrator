"""`GET /api/v1/runs?view=board` (4.12, SPEC CAP-12) over an ASGI transport.

The pure join is `tests/unit/application/test_run_views.py`'s; this module proves the route
shape (still exactly `run.py`'s three operations — no new route), the query parameter, and
that the plain `GET /runs` list is untouched by this story (`tests/unit/test_run_router.py`
already pins that response exactly; this file adds to the surface without touching it).

The harness wires every port `run_read_ports` (`api/providers.py`) really wires in
production — `projects`, `repositories`, `gate_records` included, not just `runs`/`steps` —
so a wiring mistake in that provider (e.g. swapping `projects`/`repositories`) would show up
here as a wrong `project_name`/`repository_slug`, not only in the pure-function tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_read_ports
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeGateRecordRepository, FakeRunRepository, FakeStepRunRepository

HTTP_OK = 200
HTTP_UNPROCESSABLE = 422
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 7, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000c1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000c2")


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "repo-init",
        "template_version": 1,
        "status": "queued",
        "budget_usd": Decimal("10"),
        "inputs": {"base_branch": "main"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_project() -> Project:
    return Project(
        id=PROJECT_ID,
        slug="acme",
        name="Acme",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def a_repository() -> Repository:
    return Repository(
        id=REPOSITORY_ID,
        project_id=PROJECT_ID,
        slug="acme-app",
        url="https://example.invalid/acme/app.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


class Api:
    def __init__(self, env: dict[str, str], *, runs: list[Run] | None = None) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository(runs or [])
        self.steps = FakeStepRunRepository()
        self.gate_records = FakeGateRecordRepository()
        self.ports = RunReadPorts(
            runs=self.runs,
            steps=self.steps,
            projects=FakeProjectRepository([a_project()]),
            repositories=FakeRepositoryRepository([a_repository()]),
            gate_records=self.gate_records,
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[run_read_ports] = lambda: self.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_view_board_answers_the_five_columns(api: Api) -> None:
    api.runs.add(a_run(status="running"))
    api.runs.add(a_run(status="done"))

    async with api.client() as client:
        response = await client.get(f"{RUNS}?view=board")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert set(body["columns"]) == {"queued", "running", "needs_you", "done", "failed"}
    assert len(body["columns"]["running"]) == 1
    assert len(body["columns"]["done"]) == 1
    assert body["counts"] == {"running": 1, "queued": 0, "needs_you": 0}


async def test_a_card_names_its_project_and_repository_through_the_real_wiring(
    api: Api,
) -> None:
    """End-to-end proof that `run_read_ports` wires `projects`/`repositories` the way the
    pure `_card` builder expects — a swapped port here would show up as a wrong slug/name,
    which the pure-function tests alone cannot catch."""
    api.runs.add(a_run(status="running"))

    async with api.client() as client:
        response = await client.get(f"{RUNS}?view=board")

    card = response.json()["columns"]["running"][0]
    assert card["project_name"] == "Acme"
    assert card["repository_slug"] == "acme-app"


async def test_needs_you_since_reads_the_real_gate_record_wiring(api: Api) -> None:
    run = a_run(status="needs_you", park_kind="blocked")
    api.runs.add(run)
    api.gate_records.add(
        GateRecord(id=new_id(), run_id=run.id, at=NOW, event="blocked", actor="machine")
    )

    async with api.client() as client:
        response = await client.get(f"{RUNS}?view=board")

    card = response.json()["columns"]["needs_you"][0]
    assert card["needs_you_since"] == "2026-09-07T00:00:00Z"


async def test_a_cancelled_run_files_under_failed_with_can(api: Api) -> None:
    api.runs.add(a_run(status="cancelled"))

    async with api.client() as client:
        response = await client.get(f"{RUNS}?view=board")

    body = response.json()
    assert len(body["columns"]["failed"]) == 1
    assert body["columns"]["failed"][0]["token"] == "CAN"


async def test_project_id_filters_the_board(api: Api) -> None:
    other_project = UUID("01960000-0000-7000-9000-0000000000c9")
    api.runs.add(a_run(project_id=PROJECT_ID))
    api.runs.add(a_run(project_id=other_project))

    async with api.client() as client:
        response = await client.get(f"{RUNS}?view=board&project_id={PROJECT_ID}")

    body = response.json()
    assert len(body["columns"]["queued"]) == 1


async def test_project_id_also_filters_the_plain_list_without_view(api: Api) -> None:
    """The same `project_id` query parameter, on the branch that answers `Page[RunSummaryOut]`
    rather than the Board — `list_runs` forwards it to `ports.runs.list(project_id=...)`
    either way (`api/routers/run.py`)."""
    other_project = UUID("01960000-0000-7000-9000-0000000000c9")
    scoped = a_run(project_id=PROJECT_ID)
    api.runs.add(scoped)
    api.runs.add(a_run(project_id=other_project))

    async with api.client() as client:
        response = await client.get(f"{RUNS}?project_id={PROJECT_ID}")

    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(scoped.id)]


async def test_without_view_the_plain_list_is_unaffected(api: Api) -> None:
    api.runs.add(a_run())

    async with api.client() as client:
        response = await client.get(RUNS)

    body = response.json()
    assert "items" in body
    assert "columns" not in body


async def test_an_unknown_view_value_is_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}?view=nope")

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_a_malformed_project_id_is_a_422_on_the_board_branch(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}?view=board&project_id=not-a-uuid")

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_a_malformed_project_id_is_a_422_on_the_plain_list_branch(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}?project_id=not-a-uuid")

    assert response.status_code == HTTP_UNPROCESSABLE
