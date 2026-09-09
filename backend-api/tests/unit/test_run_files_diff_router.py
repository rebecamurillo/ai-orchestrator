"""`GET /api/v1/runs/{run_id}/files?diff=1` over an ASGI transport (story 6-6, FR-31).

The pure join is `tests/unit/application/test_run_files_diff.py`'s; this module proves the
*mode*: that `diff=1` is a third answer on the route that already exists rather than a third
operation on the resource (`test_run_files_router.py` pins this router at two operations),
that each of the read's three shapes still comes back on its own query, and that the diff's
own refusals reach the wire as `application/problem+json`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_files_diff_ports, run_files_ports
from orchestrator.api.routers import run_files as router_module
from orchestrator.application.rules.protected_paths import hits_payload
from orchestrator.application.use_cases.run_files import RunFilesDiffPorts, RunFilesPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)
from tests.unit.fakes.workspace import FakeWorkspace

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
PROBLEM_MEDIA_TYPE = "application/problem+json"
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 9, tzinfo=UTC)
SPEC_FOLDER = "specs/gates"
STORY_PATH = f"{SPEC_FOLDER}/stories/2-record-the-plan.md"
CONTENT = "---\nstatus: ready-for-dev\n---\n"
BUILD = "stories[0].build"
WORKTREE = "/work/acme/widgets/wt/gates"
START_SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
AGENTS = "AGENTS.md"
UNIFIED = "diff --git a/AGENTS.md b/AGENTS.md\n@@ -1 +1 @@\n-old\n+new\n"


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.run = Run(
            id=new_id(),
            project_id=new_id(),
            repository_id=new_id(),
            template_name="epic",
            template_version=1,
            status="needs_you",
            budget_usd=Decimal("10"),
            inputs={"spec_folder": SPEC_FOLDER},
            worktree_path=WORKTREE,
            created_at=NOW,
            park_kind="protected_path",
            park_path=BUILD,
            park_reason="protected path modified: AGENTS.md",
        )
        row = StepRun(
            id=new_id(),
            run_id=self.run.id,
            seq=1,
            path=BUILD,
            label=BUILD,
            kind="agent",
            gate="liveness",
            status="error",
        )
        attempts = FakeAttemptRepository()
        attempts.add(
            Attempt(
                id=new_id(),
                run_id=self.run.id,
                step_run_id=row.id,
                n=1,
                status="done",
                started_at=NOW,
                start_sha=START_SHA,
            )
        )
        records = FakeGateRecordRepository()
        records.add(
            GateRecord(
                id=new_id(),
                run_id=self.run.id,
                at=NOW,
                path=BUILD,
                event="protected_path",
                actor="machine",
                text=self.run.park_reason or "",
                payload=hits_payload((Change(path=AGENTS, kind="added"),)),
            )
        )
        runs = FakeRunRepository([self.run])
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[run_files_ports] = lambda: RunFilesPorts(
            runs=runs, workspace=lambda root: FakeWorkspace(root, files={STORY_PATH: CONTENT})
        )
        self.app.dependency_overrides[run_files_diff_ports] = lambda: RunFilesDiffPorts(
            runs=runs,
            steps=FakeStepRunRepository([row]),
            attempts=attempts,
            records=records,
            git=FakeGit(diff=[UNIFIED]),
        )
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


async def test_diff_1_answers_the_unified_diff_and_the_sha_it_ran_from(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(
            f"{RUNS}/{api.run.id}/files", params={"path": AGENTS, "diff": 1}
        )

    assert response.status_code == HTTP_OK, response.text
    assert response.json() == {"path": AGENTS, "from_sha": START_SHA, "diff": UNIFIED}


async def test_the_same_path_without_diff_is_still_the_files_own_read(api: Api) -> None:
    """Three shapes on one route: the mode is a query, and it changes only the answer."""
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{api.run.id}/files", params={"path": STORY_PATH})

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["content"] == CONTENT


async def test_no_path_at_all_is_still_the_tree(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{api.run.id}/files")

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["root"] == SPEC_FOLDER


async def test_a_path_that_is_not_a_recorded_hit_is_a_403(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(
            f"{RUNS}/{api.run.id}/files", params={"path": STORY_PATH, "diff": 1}
        )

    assert response.status_code == HTTP_FORBIDDEN
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_an_escaping_path_is_a_422_in_this_mode_too(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(
            f"{RUNS}/{api.run.id}/files", params={"path": "../x", "diff": 1}
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_an_unknown_run_is_a_404_in_this_mode_too(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{new_id()}/files", params={"path": AGENTS, "diff": 1})

    assert response.status_code == HTTP_NOT_FOUND


async def test_the_router_still_declares_exactly_the_two_operations() -> None:
    """The mode is a query on the read, never a third route: `runs.py`'s own frozen
    route-count rule is the reason this router exists at all."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/runs/{run_id}/files"), (["PUT"], "/runs/{run_id}/files")]
