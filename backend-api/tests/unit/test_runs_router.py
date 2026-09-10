"""`POST` and `GET /api/v1/runs/preflight` over an ASGI transport (SPEC CAP-3, FR-8).

The rules are asserted in `tests/unit/application/test_preflight_use_case.py`; what only a
request can show is here: which status each operation answers with, and that `GET` — the
sibling `test_bearer_auth.py`'s `paths[path]["get"]` sweep requires on a path that is
otherwise POST-only — answers the same computation over an empty request.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import preflight_ports
from orchestrator.api.routers import runs as router_module
from orchestrator.api.schemas.preflight import LineOut, PreflightIn
from orchestrator.application.preflight.model import Line, PreflightRequest
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"
PREFLIGHT = "/api/v1/runs/preflight"

NOW = datetime(2026, 1, 1, tzinfo=UTC)
REPO_INIT_ROW_COUNT = 8


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
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


class Api:
    """One application, one set of fake repositories, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str], *, git: FakeGit) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.ports = PreflightPorts(
            git=git,
            templates=fixtures.repository_of_versions(),
            runs=FakeRunRepository(),
            harnesses=FakeHarnessRepository(),
            repositories=FakeRepositoryRepository([repository()]),
            projects=FakeProjectRepository([project()]),
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=Path("/work"),
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[preflight_ports] = lambda: self.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

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
    return Api(env, git=fixtures.repo_init_git())


async def test_post_answers_the_repo_init_plan(api: Api) -> None:
    payload = {
        "template_name": "repo-init",
        "template_version": 1,
        "project_id": str(fixtures.PROJECT.id),
        "repository_id": str(fixtures.REPOSITORY.id),
        "base_branch": fixtures.BASE_BRANCH,
    }

    async with api.client() as client:
        response = await client.post(PREFLIGHT, json=payload)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["start_allowed"] is True
    assert len(body["rows"]) == REPO_INIT_ROW_COUNT
    assert body["queue_note"] == "starts immediately if the repository is free"


async def test_get_answers_the_empty_request(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(PREFLIGHT)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["start_allowed"] is False
    assert body["rows"] is None
    assert all(line["status"] == "skip" for line in body["lines"])


async def test_a_missing_body_field_is_a_skip_line_not_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(PREFLIGHT, json={})

    assert response.status_code == HTTP_OK


async def test_posting_without_the_bearer_is_a_401(api: Api) -> None:
    async with api.anonymous() as client:
        response = await client.post(PREFLIGHT, json={})

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_reading_without_the_bearer_is_a_401(api: Api) -> None:
    async with api.anonymous() as client:
        response = await client.get(PREFLIGHT)

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_the_path_publishes_both_a_get_and_a_post(api: Api) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert set(document["paths"][PREFLIGHT]) == {"get", "post"}


async def test_the_get_reaches_this_operation_so_the_bearer_sweep_can_index_it(
    api: Api,
) -> None:
    """`test_bearer_auth.py` reads `document["paths"][path]["get"]` for every published
    `/api/v1` path; a POST-only path fails that frozen test."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "get" in document["paths"][PREFLIGHT]


def test_the_router_declares_exactly_the_two_operations() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], "/runs/preflight"),
        (["POST"], "/runs/preflight"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


def test_preflight_in_as_request_carries_every_field() -> None:
    payload = PreflightIn(template_name="repo-init", template_version=1, harness="claude")

    request = payload.as_request()

    assert isinstance(request, PreflightRequest)
    assert request.template_name == "repo-init"
    assert request.harness == "claude"


def test_line_out_of_renders_a_line() -> None:
    out = LineOut.of(Line(check="origin reachable", status="ok", text="reachable"))

    assert out.model_dump(exclude_none=True) == {
        "check": "origin reachable",
        "status": "ok",
        "text": "reachable",
    }
