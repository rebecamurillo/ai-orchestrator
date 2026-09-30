"""`POST /api/v1/harnesses/{name}/readiness` over an ASGI transport (SPEC CAP-8).

The rules are asserted in `tests/unit/application/test_harness_readiness_start.py`; what
only a request can show is here: the route shape, the 201 body, and the two refusals.
`api/routers/harnesses.py`'s own frozen route-count test is why this lives in a router of
its own — see that module's docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import harness_ports, readiness_ports
from orchestrator.api.routers import harness_readiness as router_module
from orchestrator.application.use_cases import harness_readiness
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.harness_readiness import HarnessReadinessPorts
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG, Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
HTTP_NOT_FOUND = 404
READINESS = "/api/v1/harnesses/claude/readiness"

NOW = datetime(2026, 3, 4, tzinfo=UTC)

#: The exemplar this suite configures readiness with — fixture data, not a product name
#: (Operator decision 2026-09-30: no template name hardcoded in product code). It replaces
#: the fixture that monkeypatched `harness_readiness.READINESS_TEMPLATE_NAME`/`_VERSION`,
#: and asserts more: the *configured* name is what the dispatched Run carries.
TEMPLATE_NAME = "repo-init"


def project() -> Project:
    return Project(
        id=UUID("01960000-0000-7000-8000-0000000000f1"),
        slug=READINESS_PROJECT_SLUG,
        name="Readiness",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        builtin=True,
        created_at=NOW,
        updated_at=NOW,
    )


def repository(project_id: UUID) -> Repository:
    return Repository(
        id=UUID("01960000-0000-7000-8000-0000000000f2"),
        project_id=project_id,
        slug=harness_readiness.READINESS_REPOSITORY_SLUG,
        url="file:///work/readiness/origin.git",
        default_branch="main",
        install_command="",
        quality_gate_command="sh check.sh",
        unit_test_command="",
        test_globs=(),
        package_manager="other",
        clone_check=CloneCheck(
            status="ok", at=NOW, output="ok", bmad_version=fixtures.BMAD_VERSION
        ),
        created_at=NOW,
        updated_at=NOW,
    )


class Api:
    """One application, one set of fakes, and a client that carries the bearer."""

    def __init__(
        self, env: dict[str, str], *, seed_project: bool = True, existing: list[Run] | None = None
    ) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.project = project()
        self.repository = repository(self.project.id)
        self.projects = FakeProjectRepository([self.project] if seed_project else [])
        self.repositories = FakeRepositoryRepository([self.repository] if seed_project else [])
        self.runs = FakeRunRepository(existing or [])
        self.templates = fixtures.FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        preflight = PreflightPorts(
            git=FakeGit(
                refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA},
                files={(fixtures.BASE_SHA, "specs/readiness/SPEC.md"): "# readiness"},
                listings={},
            ),
            templates=self.templates,
            runs=self.runs,
            harnesses=FakeHarnessRepository(),
            repositories=self.repositories,
            projects=self.projects,
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=fixtures.BASE.parent.parent.parent,
        )
        self.ports = HarnessReadinessPorts(
            create_run=CreateRunPorts(
                preflight=preflight,
                engine=self.engine,
                steps=self.steps,
                uow=self.uow,
                clock=FakeClock(NOW),
                skip_harness_check=True,
            ),
            budget_usd=Decimal("5"),
            template_name=TEMPLATE_NAME,
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[readiness_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> HarnessReadinessPorts:
        with self.uow:
            yield self.ports

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_dispatches_a_run_and_answers_201_with_the_run_and_queue_note(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(READINESS)

    assert response.status_code == HTTP_CREATED
    body = response.json()
    run_id = UUID(body["run"]["id"])
    assert run_id in api.runs.runs
    # the configured Template, at the latest version the store holds of it (AD-7, AD-15)
    assert api.runs.runs[run_id].template_name == TEMPLATE_NAME
    assert api.runs.runs[run_id].template_version == max(api.templates.list_versions(TEMPLATE_NAME))
    assert "starts_now" in body
    assert "waiting" in body


async def test_the_path_publishes_a_post(api: Api) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "post" in document["paths"]["/api/v1/harnesses/{name}/readiness"]


async def test_answers_404_when_the_readiness_project_is_not_seeded(env: dict[str, str]) -> None:
    api = Api(env, seed_project=False)

    async with api.client() as client:
        response = await client.post(READINESS)

    assert response.status_code == HTTP_NOT_FOUND


async def test_answers_409_when_a_non_terminal_readiness_run_is_already_in_progress(
    env: dict[str, str],
) -> None:
    api = Api(env)
    in_flight = Run(
        id=UUID("01960000-0000-7000-8000-0000000000f3"),
        project_id=api.project.id,
        repository_id=api.repository.id,
        template_name="repo-init",
        template_version=1,
        inputs={"harness": "claude", "branch": "readiness/claude/2026-03-03"},
        status="running",
        budget_usd=Decimal("5"),
        created_at=NOW,
    )
    api.runs.add(in_flight)

    async with api.client() as client:
        response = await client.post(READINESS)

    assert response.status_code == HTTP_CONFLICT


def test_the_router_declares_exactly_the_post_and_the_get() -> None:
    routes = {(tuple(sorted(route.methods)), route.path) for route in router_module.router.routes}

    assert routes == {
        (("POST",), "/harnesses/{name}/readiness"),
        (("GET",), "/harnesses/{name}/readiness"),
    }


async def test_get_readiness_reads_the_stored_harness(env: dict[str, str]) -> None:
    api = Api(env)
    harnesses = FakeHarnessRepository([Harness(name="claude", enabled=True, version_pin="2.1.258")])
    api.app.dependency_overrides[harness_ports] = lambda: HarnessPorts(
        uow=api.uow, harnesses=harnesses
    )

    async with api.client() as client:
        response = await client.get(READINESS)

    assert response.status_code == HTTP_OK
    assert response.json()["name"] == "claude"
    assert response.json()["enabled"] is True


async def test_get_readiness_answers_404_for_an_unknown_harness(env: dict[str, str]) -> None:
    api = Api(env)
    api.app.dependency_overrides[harness_ports] = lambda: HarnessPorts(
        uow=api.uow, harnesses=FakeHarnessRepository()
    )

    async with api.client() as client:
        response = await client.get(READINESS)

    assert response.status_code == HTTP_NOT_FOUND
