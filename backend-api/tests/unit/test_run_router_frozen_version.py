"""`POST /api/v1/runs` and `/runs/preflight` refuse a template version that is not stored
(epic 3, story 3, 2026-11-23; SPEC CAP-3). The rule is asserted in
`tests/unit/application/test_create_run_frozen_version.py`; this module shows its answers."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from orchestrator.api.providers import create_run_ports, preflight_ports
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_create_run_frozen_version import (
    MISSING_VERSION,
    NAME,
    frozen_demo_store,
)
from tests.unit.application.test_create_run_use_case import NOW, project, repository
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository
from tests.unit.test_run_router import PROBLEM_MEDIA_TYPE, RUNS, repo_init_payload

PREFLIGHT = f"{RUNS}/preflight"
HTTP_OK = 200
HTTP_UNPROCESSABLE = 422


@pytest.fixture
def stack(env: dict[str, str]) -> tuple[httpx.AsyncClient, FakeRunRepository, FakeWorkflowEngine]:
    runs = FakeRunRepository([])
    engine = FakeWorkflowEngine()
    uow = FakeUnitOfWork()
    preflight = PreflightPorts(
        git=fixtures.repo_init_git(),
        templates=frozen_demo_store(runs),
        runs=runs,
        harnesses=FakeHarnessRepository(),
        repositories=FakeRepositoryRepository([repository()]),
        projects=FakeProjectRepository([project()]),
        bmad_version=fixtures.BMAD_VERSION,
        max_active_runs=2,
        work_dir=Path("/work"),
    )
    ports = CreateRunPorts(
        preflight=preflight,
        engine=engine,
        steps=FakeStepRunRepository(),
        uow=uow,
        clock=FakeClock(NOW),
    )

    def create_ports():  # type: ignore[no-untyped-def]
        with uow:
            yield ports

    app = create_app(Settings(**{key.lower(): value for key, value in env.items()}))
    app.dependency_overrides[preflight_ports] = lambda: preflight
    app.dependency_overrides[create_run_ports] = create_ports
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://backend-api",
        headers={"Authorization": f"Bearer {env['ORCHESTRATOR_TOKEN']}"},
    )
    return client, runs, engine


async def test_post_runs_for_a_version_that_is_gone_answers_422_and_stores_nothing(
    stack: tuple[httpx.AsyncClient, FakeRunRepository, FakeWorkflowEngine],
) -> None:
    client, runs, engine = stack
    async with client:
        response = await client.post(
            RUNS, json=repo_init_payload(template_name=NAME, template_version=MISSING_VERSION)
        )

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    first = response.json()["errors"][0]
    assert first["template"] == NAME
    assert first["version"] == str(MISSING_VERSION)
    assert runs.runs == {}
    assert engine.calls == []


async def test_preflight_for_a_version_that_is_gone_reports_a_plan_error(
    stack: tuple[httpx.AsyncClient, FakeRunRepository, FakeWorkflowEngine],
) -> None:
    client, _, _ = stack
    async with client:
        response = await client.post(
            PREFLIGHT,
            json=repo_init_payload(template_name=NAME, template_version=MISSING_VERSION),
        )

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["plan_error"]["template"] == NAME
    assert body["plan_error"]["version"] == MISSING_VERSION
    assert body["rows"] is None
