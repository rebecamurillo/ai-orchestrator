"""`GET /api/v1/steps` (SPEC CAP-5, FR-25 history) over an ASGI transport.

A router of its own, on its own path, for the reason `api/routers/run_files.py` and
`api/routers/queue.py` each give for theirs: `tests/unit/test_runs_router.py` pins
`api/routers/runs.py` at exactly two operations, so a new route is a new module rather than
a third operation on a frozen one. The join and the paging are
`tests/unit/application/test_history.py`'s; this module proves the route shape, the one
envelope (`{items, next_cursor}`), the query parameters reaching the use case, the two
refusals, and that the one credential guards it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import history_ports
from orchestrator.api.routers import history as router_module
from orchestrator.application.use_cases.history import HistoryPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.history import HistoryEntry
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.history import FakeHistoryQuery
from tests.unit.fakes.tracer import FakeTracer

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_UNPROCESSABLE_CONTENT = 422
STEPS = "/api/v1/steps"
PROBLEM = "application/problem+json"
AT = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
STEP_SEQ = 3
ATTEMPT_SECONDS = 12.0
PAGED_ATTEMPTS = 4
PAGE = 2


def an_entry(
    *, minute: int = 1, harness: str | None = "codex", project_id: UUID | None = None
) -> HistoryEntry:
    run = Run(
        id=new_id(),
        project_id=project_id or new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("10.000000"),
        inputs={"base_branch": "main"},
        created_at=AT,
        trace_id="tr-1",
    )
    step = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=STEP_SEQ,
        path="epics[0].stories[0].build",
        label="build",
        kind="agent",
        gate="deterministic",
        status="done",
    )
    attempt = Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=step.id,
        n=1,
        status="done",
        started_at=AT + timedelta(minutes=minute),
        ended_at=AT + timedelta(minutes=minute, seconds=12),
        harness=harness,
        model="gpt-5-codex",
        session_id="sess-9",
        tokens_in=10,
        tokens_out=20,
        cost_usd=Decimal("1.500000"),
    )
    return HistoryEntry(attempt=attempt, step=step, run=run, project_name="acme")


class Api:
    def __init__(self, env: dict[str, str], entries: list[HistoryEntry] | None = None) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.query = FakeHistoryQuery(entries or [])
        self.ports = HistoryPorts(history=self.query, tracer=FakeTracer())
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[history_ports] = lambda: self.ports
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
    return Api(env)


def test_the_router_declares_exactly_one_operation() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/steps")]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_an_empty_history_answers_the_one_list_envelope(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(STEPS)

    assert response.status_code == HTTP_OK
    assert response.json() == {"items": [], "next_cursor": None}


async def test_a_row_carries_the_columns_the_table_prints(env: dict[str, str]) -> None:
    entry = an_entry()
    api = Api(env, [entry])

    async with api.client() as client:
        response = await client.get(STEPS)

    row = response.json()["items"][0]
    assert row["attempt_id"] == str(entry.attempt.id)
    assert row["run_id"] == str(entry.run.id)
    assert row["seq"] == STEP_SEQ
    assert row["project_name"] == "acme"
    assert row["run_label"] == "story v1 · main"
    assert row["path"] == "epics[0].stories[0].build"
    assert row["kind"] == "agent"
    assert row["harness"] == "codex"
    assert row["status"] == "done"
    assert row["token"] == "DON"
    assert row["cost_usd"] == "1.500000"
    assert row["started_at"] == "2026-09-09T08:01:00Z"
    assert row["seconds"] == ATTEMPT_SECONDS
    assert row["trace_url"].endswith("tr-1")
    assert row["log_tail_url"] == f"/api/v1/runs/{entry.run.id}/detail"


async def test_the_cursor_pages_the_answer(env: dict[str, str]) -> None:
    api = Api(env, [an_entry(minute=n) for n in range(PAGED_ATTEMPTS)])

    async with api.client() as client:
        first = (await client.get(STEPS, params={"limit": PAGE})).json()
        second = (
            await client.get(STEPS, params={"limit": PAGE, "cursor": first["next_cursor"]})
        ).json()
        third = (
            await client.get(STEPS, params={"limit": PAGE, "cursor": second["next_cursor"]})
        ).json()

    assert first["next_cursor"] is not None
    assert len({row["attempt_id"] for row in first["items"] + second["items"]}) == PAGED_ATTEMPTS
    assert third == {"items": [], "next_cursor": None}


async def test_the_filters_reach_the_query(env: dict[str, str]) -> None:
    project_id = new_id()
    api = Api(env, [an_entry(project_id=project_id)])

    async with api.client() as client:
        await client.get(
            STEPS, params={"project_id": str(project_id), "status": "DON", "harness": "codex"}
        )

    spec = api.query.calls[-1]
    assert spec.project_id == project_id
    assert spec.statuses == ("done",)
    assert spec.harness == "codex"


async def test_an_unknown_status_token_is_a_problem_document(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(STEPS, params={"status": "NOPE"})

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_an_unreadable_cursor_is_a_problem_document(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(STEPS, params={"cursor": "%%%"})

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_a_limit_outside_the_bounds_is_refused(api: Api) -> None:
    async with api.client() as client:
        too_big = await client.get(STEPS, params={"limit": 5000})
        too_small = await client.get(STEPS, params={"limit": 0})

    assert too_big.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert too_small.status_code == HTTP_UNPROCESSABLE_CONTENT


async def test_an_unauthenticated_request_is_refused(api: Api) -> None:
    async with api.anonymous() as client:
        response = await client.get(STEPS)

    assert response.status_code == HTTP_UNAUTHORIZED
