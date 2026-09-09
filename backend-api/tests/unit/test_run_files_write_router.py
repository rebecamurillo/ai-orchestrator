"""`PUT /api/v1/runs/{run_id}/files` (story 6-3, SPEC CAP-2, FR-19) over an ASGI transport.

The pure join is `tests/unit/application/test_run_files_write.py`'s; this module proves the
route shape and every request-level refusal: 404 (unknown Run), 422 (a path that escapes the
workspace), 403 (a well-formed path outside the Run's own spec folder), 409 (a list file the
plan read, or a Run that is not parked without a terminal session), 401 (no bearer).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_files_write_ports
from orchestrator.api.routers import run_files as router_module
from orchestrator.application.use_cases.run_files import RunFilesWritePorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.runs import FakeGateRecordRepository, FakeRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 9, tzinfo=UTC)
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"
SPEC_FOLDER = "specs/gates"
SPEC_FILE = f"{SPEC_FOLDER}/SPEC.md"
STORIES_FILE = f"{SPEC_FOLDER}/stories.yaml"
WORKTREE_PATH = "/work/acme/widgets/wt/gates"
NEW_CONTENT = "# SPEC\n\nedited by the operator\n"


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "budget_usd": Decimal("10"),
        "inputs": {"spec_folder": SPEC_FOLDER},
        "worktree_path": WORKTREE_PATH,
        "park_path": "stories[0].build",
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Api:
    def __init__(self, env: dict[str, str], files: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository()
        self.git = FakeGit()
        self.records = FakeGateRecordRepository()
        self.uow = FakeUnitOfWork()
        self.uow.__enter__()
        self.workspace = FakeWorkspace(WORKTREE_PATH, files=files)
        self.ports = RunFilesWritePorts(
            runs=self.runs,
            workspace=lambda root: self.workspace,
            git=self.git,
            records=self.records,
            clock=FakeClock(EPOCH),
            uow=self.uow,
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[run_files_write_ports] = lambda: self.ports
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
    return Api(env, {SPEC_FILE: "old", STORIES_FILE: "stories: []\n"})


def test_the_router_declares_a_put_operation_beside_the_get() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert (["PUT"], "/runs/{run_id}/files") in routes


async def test_a_write_on_a_parked_run_returns_the_new_entry(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.put(
            f"{RUNS}/{run.id}/files", json={"path": SPEC_FILE, "content": NEW_CONTENT}
        )

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body == {"path": SPEC_FILE, "kind": "file", "size": len(NEW_CONTENT), "mtime": 0.0}
    assert api.git.called("commit") != []


async def test_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.put(
            f"{RUNS}/{UNKNOWN_ID}/files", json={"path": SPEC_FILE, "content": NEW_CONTENT}
        )

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_path_escaping_the_workspace_is_a_422(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.put(
            f"{RUNS}/{run.id}/files", json={"path": "../x", "content": NEW_CONTENT}
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_path_outside_the_spec_folder_is_a_403(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.put(
            f"{RUNS}/{run.id}/files", json={"path": "elsewhere.md", "content": NEW_CONTENT}
        )

    assert response.status_code == HTTP_FORBIDDEN
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_list_file_the_plan_read_is_a_409(api: Api) -> None:
    run = a_run(plan_refs={STORIES_FILE: "abc1234"})
    api.runs.add(run)

    async with api.client() as client:
        response = await client.put(
            f"{RUNS}/{run.id}/files", json={"path": STORIES_FILE, "content": "stories: []\n"}
        )

    assert response.status_code == HTTP_CONFLICT
    assert "planned at abc1234" in response.json()["detail"]


async def test_a_run_that_is_not_parked_is_a_409(api: Api) -> None:
    run = a_run(status="running")
    api.runs.add(run)

    async with api.client() as client:
        response = await client.put(
            f"{RUNS}/{run.id}/files", json={"path": SPEC_FILE, "content": NEW_CONTENT}
        )

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_terminal_session_is_a_409(api: Api) -> None:
    run = a_run(terminal_session=True)
    api.runs.add(run)

    async with api.client() as client:
        response = await client.put(
            f"{RUNS}/{run.id}/files", json={"path": SPEC_FILE, "content": NEW_CONTENT}
        )

    assert response.status_code == HTTP_CONFLICT


async def test_without_the_bearer_it_is_a_401(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.anonymous() as client:
        response = await client.put(
            f"{RUNS}/{run.id}/files", json={"path": SPEC_FILE, "content": NEW_CONTENT}
        )

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_the_put_reaches_this_operation_so_the_bearer_sweep_can_index_it(api: Api) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "put" in document["paths"][f"{RUNS}/{{run_id}}/files"]
