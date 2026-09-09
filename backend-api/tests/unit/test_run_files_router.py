"""`GET /api/v1/runs/{run_id}/files` (story 6-2, SPEC CAP-2, FR-19) over an ASGI transport.

The pure join is `tests/unit/application/test_run_files.py`'s; this module proves the route
shape, the honest-alternative placement (a sibling of `runs.py`, not a growth of it — see
`api/routers/run_files.py`'s own docstring), and every request-level refusal: 404 (unknown
Run or no file there), 422 (a path that escapes the workspace), 403 (a well-formed path
outside the Run's own spec folder), 401 (no bearer).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_files_ports
from orchestrator.api.routers import run_files as router_module
from orchestrator.application.use_cases.run_files import RunFilesPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 9, tzinfo=UTC)
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"
SPEC_FOLDER = "specs/gates"
STORY_PATH = f"{SPEC_FOLDER}/stories/2-record-the-plan.md"
CONTENT = "---\nstatus: ready-for-dev\n---\n\n# Story\n"


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
        "worktree_path": "/work/acme/widgets/wt/gates",
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Api:
    def __init__(self, env: dict[str, str], files: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository()
        self.ports = RunFilesPorts(
            runs=self.runs, workspace=lambda root: FakeWorkspace(root, files=files)
        )
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[run_files_ports] = lambda: self.ports
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
    return Api(env, {STORY_PATH: CONTENT})


def test_the_router_declares_exactly_one_operation() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/runs/{run_id}/files")]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_a_file_inside_the_spec_folder_is_read(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files", params={"path": STORY_PATH})

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body == {
        "path": STORY_PATH,
        "content": CONTENT,
        "size": len(CONTENT),
        "mtime": 0.0,
    }


async def test_a_glob_pattern_resolves_server_side(api: Api) -> None:
    run = a_run()
    api.runs.add(run)
    pattern = f"{SPEC_FOLDER}/stories/2-*.md"

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files", params={"path": pattern})

    assert response.status_code == HTTP_OK
    assert response.json()["path"] == STORY_PATH


async def test_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{UNKNOWN_ID}/files", params={"path": STORY_PATH})

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_path_escaping_the_workspace_is_a_422(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files", params={"path": "../x"})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_path_outside_the_spec_folder_is_a_403(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files", params={"path": "elsewhere.md"})

    assert response.status_code == HTTP_FORBIDDEN
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_missing_path_query_param_is_a_422(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files")

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_without_the_bearer_it_is_a_401(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.anonymous() as client:
        response = await client.get(f"{RUNS}/{run.id}/files", params={"path": STORY_PATH})

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_the_get_reaches_this_operation_so_the_bearer_sweep_can_index_it(api: Api) -> None:
    """`test_bearer_auth.py` indexes `document["paths"][path]["get"]` for every published
    path — nothing to prove wrong here, this route is `GET`-only already, but the shape
    check itself belongs beside the other router tests that state it."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "get" in document["paths"][f"{RUNS}/{{run_id}}/files"]
