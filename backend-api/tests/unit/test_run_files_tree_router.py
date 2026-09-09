"""`GET /api/v1/runs/{run_id}/files` with no `path` (story 6-3, SPEC CAP-2, FR-19) over an
ASGI transport — the tree branch `test_run_files_router.py`'s own
`test_a_missing_path_query_param_answers_the_tree` names but does not itself detail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_files_ports
from orchestrator.application.use_cases.run_files import RunFilesPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

HTTP_OK = 200
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 9, tzinfo=UTC)
SPEC_FOLDER = "specs/gates"
SPEC_FILE = f"{SPEC_FOLDER}/SPEC.md"
STORY_FILE = f"{SPEC_FOLDER}/stories/2-record-the-plan.md"
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


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, {SPEC_FILE: "spec text", STORY_FILE: CONTENT})


async def test_the_tree_root_is_the_scope_folder(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files")

    assert response.status_code == HTTP_OK
    assert response.json()["root"] == SPEC_FOLDER


async def test_every_file_and_ancestor_directory_is_a_row(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files")

    rows = {(row["path"], row["kind"]) for row in response.json()["entries"]}
    assert (SPEC_FILE, "file") in rows
    assert (STORY_FILE, "file") in rows
    assert (f"{SPEC_FOLDER}/stories", "dir") in rows


async def test_a_file_row_carries_its_size_and_mtime(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files")

    row = next(row for row in response.json()["entries"] if row["path"] == SPEC_FILE)
    assert row["size"] == len("spec text")
    assert row["mtime"] == 0.0


async def test_a_present_path_still_reads_one_file_not_the_tree(api: Api) -> None:
    run = a_run()
    api.runs.add(run)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/files", params={"path": SPEC_FILE})

    assert response.status_code == HTTP_OK
    assert response.json() == {
        "path": SPEC_FILE,
        "content": "spec text",
        "size": len("spec text"),
        "mtime": 0.0,
    }
