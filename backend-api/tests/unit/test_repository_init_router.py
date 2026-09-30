"""`POST/GET /api/v1/repositories/{id}/init` over an ASGI transport (SPEC CAP-10, FR-30).

The rules are asserted in `tests/unit/application/test_repository_init.py`; what only a
request can show is here: the route shape, the status each operation answers with, and the
problem document each refusal becomes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import create_run_ports, project_ports
from orchestrator.api.routers import repository_init as router_module
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.projects import ProjectPorts
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
HTTP_NOT_FOUND = 404
PROBLEM_MEDIA_TYPE = "application/problem+json"

REPOSITORIES = "/api/v1/repositories"

#: What the committed `.env.example` sets `INIT_TEMPLATE` to — read here as the fixture
#: repository's own exemplar name, which is also what the contract happens to name.
SHIPPED_DEFAULT = "repo-init"
#: The same exemplar text under a second name, for the one test that proves the *configured*
#: name is what reaches the Run (Operator decision 2026-09-30: no template name hardcoded in
#: product code).
RENAMED_TEMPLATE = "house-init"
NOW = datetime(2026, 1, 1, tzinfo=UTC)
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


def repository(**overrides: object) -> Repository:
    fields: dict[str, object] = {
        "id": fixtures.REPOSITORY.id,
        "project_id": fixtures.PROJECT.id,
        "slug": fixtures.REPOSITORY.slug,
        "url": fixtures.REPOSITORY.url,
        "default_branch": fixtures.REPOSITORY.default_branch,
        "install_command": fixtures.REPOSITORY.install_command or "",
        "quality_gate_command": fixtures.REPOSITORY.quality_gate_command or "",
        "unit_test_command": fixtures.REPOSITORY.unit_test_command or "",
        "test_globs": fixtures.REPOSITORY.test_globs,
        "package_manager": "uv",
        "clone_check": CloneCheck(
            status="ok", at=NOW, output="", bmad_version=fixtures.BMAD_VERSION
        ),
        "created_at": NOW,
        "updated_at": NOW,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


class Api:
    """One application, one set of fakes, and a client that carries the bearer."""

    def __init__(
        self,
        env: dict[str, str],
        *,
        existing: list[Run] | None = None,
        init_template: str | None = None,
    ) -> None:
        overrides = {key.lower(): value for key, value in env.items()}
        if init_template is not None:
            overrides["init_template"] = init_template
        self.settings = Settings(**overrides)
        self.runs = FakeRunRepository(existing or [])
        self.repositories = FakeRepositoryRepository([repository()])
        self.projects = FakeProjectRepository([project()])
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        stored = self.templates.versions[(SHIPPED_DEFAULT, 1)]
        self.templates.add(stored.model_copy(update={"name": RENAMED_TEMPLATE}))
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        preflight = PreflightPorts(
            git=fixtures.repo_init_git(),
            templates=self.templates,
            runs=self.runs,
            harnesses=FakeHarnessRepository(),
            repositories=self.repositories,
            projects=self.projects,
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
        self.project_uow = FakeUnitOfWork()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[create_run_ports] = self._create_ports
        self.app.dependency_overrides[project_ports] = self._project_ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _create_ports(self) -> CreateRunPorts:
        with self.uow:
            yield self.create_ports

    def _project_ports(self) -> ProjectPorts:
        with self.project_uow:
            yield ProjectPorts(
                uow=self.project_uow,
                projects=self.projects,
                repositories=self.repositories,
                crypto=None,  # type: ignore[arg-type] — no rule read here encrypts anything
                clock=FakeClock(NOW),
            )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


def path_for(repository_id: object = fixtures.REPOSITORY.id) -> str:
    return f"{REPOSITORIES}/{repository_id}/init"


# ── the route shape ──────────────────────────────────────────────────────────────────────


def test_the_router_declares_exactly_the_two_operations() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], "/repositories/{repository_id}/init"),
        (["POST"], "/repositories/{repository_id}/init"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_the_path_has_a_get_the_bearer_sweep_can_index(api: Api) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "get" in document["paths"][path_for("{repository_id}")]
    assert "post" in document["paths"][path_for("{repository_id}")]


# ── POST ─────────────────────────────────────────────────────────────────────────────────


async def test_post_creates_an_initialisation_run(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(path_for())

    assert response.status_code == HTTP_CREATED, response.text
    body = response.json()
    assert body["run"]["template"] == api.settings.init_template
    assert body["run"]["version"] == max(api.templates.list_versions(api.settings.init_template))
    assert body["run"]["branch"] == fixtures.REPOSITORY.default_branch
    assert body["starts_now"] is True


async def test_post_starts_the_template_init_template_names(env: dict[str, str]) -> None:
    """Operator decision 2026-09-30: no template name hardcoded in product code. The whole
    provider chain is real here — only the ports' *adapters* are faked — so this is what
    proves `INIT_TEMPLATE` reaches `init_repository` rather than a constant."""
    api = Api(env, init_template=RENAMED_TEMPLATE)

    async with api.client() as client:
        response = await client.post(path_for())

    assert response.status_code == HTTP_CREATED, response.text
    assert response.json()["run"]["template"] == RENAMED_TEMPLATE


async def test_post_on_an_unknown_repository_is_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(path_for(UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND, response.text
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE


async def test_post_with_a_failed_clone_check_is_409(env: dict[str, str]) -> None:
    api = Api(env)
    api.repositories.update(
        repository(
            clone_check=CloneCheck(
                status="failed", at=NOW, output="fatal: Authentication failed", bmad_version=None
            )
        )
    )

    async with api.client() as client:
        response = await client.post(path_for())

    assert response.status_code == HTTP_CONFLICT, response.text
    assert "clone check failed" in response.json()["detail"]


async def test_post_while_a_repo_init_run_is_already_going_is_409(env: dict[str, str]) -> None:
    running = Run(
        id=UUID("01a06887-79ab-759b-97a0-71c32ad939c3"),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="repo-init",
        template_version=1,
        status="running",
        budget_usd=0,
        created_at=NOW,
    )
    api = Api(env, existing=[running])

    async with api.client() as client:
        response = await client.post(path_for())

    assert response.status_code == HTTP_CONFLICT, response.text
    assert str(running.id) in response.json()["detail"]


# ── GET ──────────────────────────────────────────────────────────────────────────────────


async def test_get_reads_the_repository_this_path_initialises(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(path_for())

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["id"] == str(fixtures.REPOSITORY.id)


async def test_get_on_an_unknown_repository_is_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(path_for(UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND, response.text
