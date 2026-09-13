"""`GET /api/v1/runs/{run_id}/detail?opened=1` (story 8-3) over an ASGI transport.

The pure use-case logic is `tests/unit/application/test_open_run.py`'s; this module proves
the route boundary: `?opened=1` calls `open_run` (updating `last_opened_at`), the plain
default does not, and an unknown run_id that would be `NotFound` in `open_run` is a 404.

Two `Api` helpers — one that overrides `open_run_ports` to yield the open-run ports (the
`?opened=1` case) and one that yields `None` (the default case) — exactly mirror how the
real `open_run_ports` dependency behaves: it reads `opened` itself and yields `None` when
absent or false.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import open_run_ports, run_view_ports
from orchestrator.application.use_cases.open_run import OpenRunPorts
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

HTTP_OK = 200
HTTP_NOT_FOUND = 404
PROBLEM_MEDIA_TYPE = "application/problem+json"
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 11, tzinfo=UTC)
PRIOR = datetime(2026, 9, 10, tzinfo=UTC)
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "inputs": {"base_branch": "main"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def _view_ports(runs: FakeRunRepository) -> RunViewPorts:
    clock = FakeClock(NOW)
    return RunViewPorts(
        runs=runs,
        steps=FakeStepRunRepository(),
        attempts=FakeAttemptRepository(),
        gate_records=FakeGateRecordRepository(),
        projects=FakeProjectRepository(),
        repositories=FakeRepositoryRepository(),
        logs=FakeLogReader(),
        clock=clock,
    )


class ApiWithOpen:
    """`open_run_ports` wired: simulates `?opened=true` (provider yields the ports).

    `open_uow` is entered on construction to mirror what the real provider does before
    yielding — `open_run` now calls `commit()` directly without re-entering the UoW.
    """

    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository()
        self.clock = FakeClock(NOW)
        self.open_uow = FakeUnitOfWork()
        self.open_uow.__enter__()  # mirrors what the real open_run_ports provider does
        self.open_ports = OpenRunPorts(runs=self.runs, uow=self.open_uow, clock=self.clock)
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[run_view_ports] = lambda: _view_ports(self.runs)
        self.app.dependency_overrides[open_run_ports] = lambda: self.open_ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


class ApiWithoutOpen:
    """`open_run_ports` yields `None`: simulates default (no `?opened`) request."""

    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.runs = FakeRunRepository()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[run_view_ports] = lambda: _view_ports(self.runs)
        self.app.dependency_overrides[open_run_ports] = lambda: None
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api_open(env: dict[str, str]) -> ApiWithOpen:
    return ApiWithOpen(env)


@pytest.fixture
def api_no_open(env: dict[str, str]) -> ApiWithoutOpen:
    return ApiWithoutOpen(env)


async def test_opened_true_updates_last_opened_at(api_open: ApiWithOpen) -> None:
    """When `open_ports` is provided (simulating `?opened=true`), `open_run` runs and
    `run.last_opened_at` advances to `NOW`."""
    run = a_run(last_opened_at=PRIOR)
    api_open.runs.add(run)

    async with api_open.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/detail")

    assert response.status_code == HTTP_OK
    stored = api_open.runs.runs[run.id]
    assert stored.last_opened_at == NOW
    assert stored.last_opened_before == PRIOR


async def test_opened_false_does_not_update_timestamps(api_no_open: ApiWithoutOpen) -> None:
    """`open_ports` is `None` (simulating default, no `?opened=1`): timestamps unchanged."""
    run = a_run(last_opened_at=PRIOR)
    api_no_open.runs.add(run)

    async with api_no_open.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/detail")

    assert response.status_code == HTTP_OK
    stored = api_no_open.runs.runs[run.id]
    assert stored.last_opened_at == PRIOR
    assert stored.last_opened_before is None


async def test_response_includes_last_opened_at_field(api_open: ApiWithOpen) -> None:
    """The response's `run` object carries `last_opened_at`."""
    run = a_run(last_opened_at=None)
    api_open.runs.add(run)

    async with api_open.client() as client:
        response = await client.get(f"{RUNS}/{run.id}/detail")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert "last_opened_at" in body["run"]


async def test_opened_unknown_run_is_404(api_open: ApiWithOpen) -> None:
    """With open_run_ports wired, an unknown `run_id` yields 404 from `open_run`'s NotFound."""
    async with api_open.client() as client:
        response = await client.get(f"{RUNS}/{UNKNOWN_ID}/detail")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
