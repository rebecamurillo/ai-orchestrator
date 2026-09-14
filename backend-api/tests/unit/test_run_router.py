"""`POST/GET /api/v1/runs`, `GET /api/v1/runs/{run_id}` over an ASGI transport (SPEC CAP-4).

The rules are asserted in `tests/unit/application/test_create_run_use_case.py`; what only a
request can show is here: the route shape, the status each operation answers with, and —
the part this router exists to get right — that `/runs/preflight` (`api/routers/runs.py`,
frozen at exactly its two operations by `test_runs_router.py`) still resolves to pre-flight
once this module's own `/runs/{run_id}` is mounted beside it, rather than being swallowed as
a run id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import create_run_ports, preflight_ports, run_read_ports
from orchestrator.api.routers import run as router_module
from orchestrator.application.use_cases.create_run import CreateRunPorts, RunReadPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"

RUNS = "/api/v1/runs"
PREFLIGHT = "/api/v1/runs/preflight"

NOW = datetime(2026, 1, 1, tzinfo=UTC)
REPO_INIT_ROW_COUNT = 8
BUDGET = "10"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


def project() -> Project:
    return Project(
        id=fixtures.PROJECT.id,
        slug=fixtures.PROJECT.slug,
        name=fixtures.PROJECT.name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def repository() -> Repository:
    return Repository(
        id=fixtures.REPOSITORY.id,
        project_id=fixtures.PROJECT.id,
        slug=fixtures.REPOSITORY.slug,
        url=fixtures.REPOSITORY.url,
        default_branch=fixtures.REPOSITORY.default_branch,
        install_command=fixtures.REPOSITORY.install_command or "",
        quality_gate_command=fixtures.REPOSITORY.quality_gate_command or "",
        unit_test_command=fixtures.REPOSITORY.unit_test_command or "",
        test_globs=fixtures.REPOSITORY.test_globs,
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version=fixtures.BMAD_VERSION),
        created_at=NOW,
        updated_at=NOW,
    )


def repo_init_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "template_name": "repo-init",
        "template_version": 1,
        "project_id": str(fixtures.PROJECT.id),
        "repository_id": str(fixtures.REPOSITORY.id),
        "base_branch": fixtures.BASE_BRANCH,
        "budget_usd": BUDGET,
    }
    payload.update(overrides)
    return payload


class Api:
    """One application, one set of fakes, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str], *, existing: list[Run] | None = None) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository(existing or [])
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        preflight = PreflightPorts(
            git=fixtures.repo_init_git(),
            templates=self.templates,
            runs=self.runs,
            harnesses=FakeHarnessRepository(),
            repositories=FakeRepositoryRepository([repository()]),
            projects=FakeProjectRepository([project()]),
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=Path("/work"),
        )
        self.create_ports = CreateRunPorts(
            preflight=preflight,
            engine=self.engine,
            steps=self.steps,
            uow=self.uow,
            clock=FakeClock(NOW),
        )
        self.read_ports = RunReadPorts(runs=self.runs)
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[preflight_ports] = lambda: self.create_ports.preflight
        self.app.dependency_overrides[create_run_ports] = self._create_ports
        self.app.dependency_overrides[run_read_ports] = lambda: self.read_ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _create_ports(self) -> CreateRunPorts:
        """Enters the fake unit of work the way `create_run_ports` opens the real one."""
        with self.uow:
            yield self.create_ports

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def anonymous(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


# ── the route shape ──────────────────────────────────────────────────────────────────────


def test_the_router_declares_exactly_the_three_operations() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], "/runs"),
        (["GET"], "/runs/{run_id}"),
        (["POST"], "/runs"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_every_run_path_has_a_get(api: Api) -> None:
    """`test_bearer_auth.py` indexes `document["paths"][path]["get"]` for every published
    path; a `POST`-only `/runs` would break that frozen sweep the way an unpaired `/runs/
    preflight` would have (4.3)."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "get" in document["paths"][RUNS]
    assert "get" in document["paths"][f"{RUNS}/{{run_id}}"]


# ── mount order: `/runs/preflight` must never be swallowed as `/runs/{run_id}` ──────────


async def test_runs_preflight_still_resolves_once_run_id_is_mounted_beside_it(
    api: Api,
) -> None:
    async with api.client() as client:
        response = await client.get(PREFLIGHT)

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert "start_allowed" in body and "lines" in body


async def test_the_openapi_document_still_lists_preflight_as_its_own_path(api: Api) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert set(document["paths"][PREFLIGHT]) == {"get", "post"}
    assert set(document["paths"][f"{RUNS}/{{run_id}}"]) == {"get"}


# ── POST /runs ───────────────────────────────────────────────────────────────────────────


async def test_post_creates_and_enqueues_a_repo_init_run(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(RUNS, json=repo_init_payload())

    assert response.status_code == HTTP_CREATED, response.text
    body = response.json()
    assert body["starts_now"] is True
    assert body["run"]["status"] == "queued"
    assert body["run"]["template"] == "repo-init"
    assert body["run"]["version"] == 1
    assert body["run"]["budget_usd"] == "10.000000"
    assert len(api.steps.list_for_run(UUID(body["run"]["id"]))) == REPO_INIT_ROW_COUNT
    assert api.engine.calls


async def test_post_a_second_run_against_a_held_repository_waits(env: dict[str, str]) -> None:
    holder = Run(
        id=UUID("01960000-0000-7000-9000-000000000099"),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="repo-init",
        template_version=1,
        status="running",
        budget_usd=Decimal("1"),
        inputs={"base_branch": fixtures.BASE_BRANCH},
        created_at=NOW,
    )
    api = Api(env, existing=[holder])

    async with api.client() as client:
        response = await client.post(RUNS, json=repo_init_payload())

    assert response.status_code == HTTP_CREATED, response.text
    assert response.json()["starts_now"] is False


async def test_post_without_budget_is_a_422(api: Api) -> None:
    payload = repo_init_payload()
    del payload["budget_usd"]

    async with api.client() as client:
        response = await client.post(RUNS, json=payload)

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_post_with_a_zero_budget_is_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(RUNS, json=repo_init_payload(budget_usd="0"))

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_post_an_unknown_project_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(RUNS, json=repo_init_payload(project_id=UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND


async def test_post_without_the_bearer_is_a_401(api: Api) -> None:
    async with api.anonymous() as client:
        response = await client.post(RUNS, json=repo_init_payload())

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── GET /runs and /runs/{run_id} ─────────────────────────────────────────────────────────


async def test_get_reads_the_run_just_created(api: Api) -> None:
    async with api.client() as client:
        created = (await client.post(RUNS, json=repo_init_payload())).json()
        response = await client.get(f"{RUNS}/{created['run']['id']}")

    assert response.status_code == HTTP_OK
    assert response.json() == created["run"]


async def test_get_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{UNKNOWN_ID}")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_list_answers_every_stored_run(api: Api) -> None:
    async with api.client() as client:
        await client.post(RUNS, json=repo_init_payload())
        response = await client.get(RUNS)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert len(body["items"]) == 1
    assert body["next_cursor"] is None


async def test_reading_without_the_bearer_is_a_401(api: Api) -> None:
    async with api.anonymous() as client:
        response = await client.get(f"{RUNS}/{UNKNOWN_ID}")

    assert response.status_code == HTTP_UNAUTHORIZED
