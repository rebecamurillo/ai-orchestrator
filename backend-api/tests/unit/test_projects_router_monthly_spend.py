"""`GET /projects` and `GET /projects/{id}`: monthly spend fields and count isolation
(story 8-6).

`test_project_schemas_monthly_spend.py` proves `ProjectRead.of()` in isolation and
`test_project_spend.py` proves the use case; this module proves the router's own loop
(`api/routers/projects.py::list_projects`) wires up `project_spend.project_metrics()` and
that one project's metrics do not bleed into another.

Mirrors `test_projects_router_trajectory_count.py` — that file is frozen, so this one
replicates the `Harness` class with an additional `runs` wiring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
from fastapi import FastAPI

from orchestrator.api.providers import project_ports
from orchestrator.api.providers_trajectories import trajectory_repository
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository
from tests.unit.fakes.runs import FakeRunRepository

PROJECTS = "/api/v1/projects"
TWO_NEEDS_YOU = 2

# Clock starts on a known date so "this month" is deterministic.
CLOCK_NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)
THIS_MONTH = datetime(2026, 9, 10, tzinfo=UTC)
LAST_MONTH = datetime(2026, 8, 20, tzinfo=UTC)
RECENT = datetime(2026, 9, 13, tzinfo=UTC)  # within 7 days of CLOCK_NOW
OLD = datetime(2026, 8, 1, tzinfo=UTC)  # > 7 days before CLOCK_NOW


class Harness:
    """`test_projects_router_trajectory_count.py::Harness` extended with `runs` wiring."""

    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.projects = FakeProjectRepository()
        self.crypto = FakeCrypto()
        self.clock = FakeClock(start=CLOCK_NOW)
        self.runs = FakeRunRepository()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[project_ports] = self._ports
        self.app.dependency_overrides[trajectory_repository] = lambda: None
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> ProjectPorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return ProjectPorts(
            uow=self.uow,
            projects=self.projects,
            crypto=self.crypto,
            clock=self.clock,
            runs=self.runs,
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


def a_run(project_id: object, **overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": project_id,
        "repository_id": new_id(),
        "template_name": "dev",
        "template_version": 1,
        "status": "done",
        "budget_usd": Decimal("10"),
        "spend_usd": Decimal("0"),
        "spend_provisional": False,
        "created_at": THIS_MONTH,
        "started_at": THIS_MONTH,
        "ended_at": THIS_MONTH,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


async def create_project(api: Harness, name: str) -> str:
    async with api.client() as client:
        response = await client.post(PROJECTS, json={"name": name})
    return str(response.json()["id"])


# ── monthly spend ─────────────────────────────────────────────────────────────


async def test_monthly_spend_usd_appears_in_list_response(env: dict[str, str]) -> None:
    api = Harness(env)
    project_id = await create_project(api, "My Project")
    api.runs.add(a_run(project_id=project_id, spend_usd=Decimal("12.30"), started_at=THIS_MONTH))
    api.runs.add(a_run(project_id=project_id, spend_usd=Decimal("40.00"), started_at=LAST_MONTH))

    async with api.client() as client:
        body = (await client.get(PROJECTS)).json()

    items = body["items"]
    assert len(items) == 1
    assert items[0]["monthly_spend_usd"] == "12.30"


async def test_monthly_spend_provisional_reflected_in_response(env: dict[str, str]) -> None:
    api = Harness(env)
    project_id = await create_project(api, "Provisional Project")
    api.runs.add(
        a_run(
            project_id=project_id,
            spend_usd=Decimal("5.40"),
            spend_provisional=True,
            started_at=THIS_MONTH,
        )
    )

    async with api.client() as client:
        body = (await client.get(PROJECTS)).json()

    assert body["items"][0]["monthly_spend_provisional"] is True


async def test_needs_you_count_in_list_response(env: dict[str, str]) -> None:
    api = Harness(env)
    project_id = await create_project(api, "Needs You Project")
    api.runs.add(a_run(project_id=project_id, status="needs_you"))
    api.runs.add(a_run(project_id=project_id, status="needs_you"))
    api.runs.add(a_run(project_id=project_id, status="done"))

    async with api.client() as client:
        body = (await client.get(PROJECTS)).json()

    assert body["items"][0]["needs_you_count"] == TWO_NEEDS_YOU


async def test_failed_recent_count_in_list_response(env: dict[str, str]) -> None:
    api = Harness(env)
    project_id = await create_project(api, "Failed Project")
    api.runs.add(
        a_run(
            project_id=project_id,
            status="failed",
            ended_at=RECENT,
            created_at=RECENT,
            started_at=RECENT,
        )
    )
    api.runs.add(
        a_run(project_id=project_id, status="failed", ended_at=OLD, created_at=OLD, started_at=OLD)
    )

    async with api.client() as client:
        body = (await client.get(PROJECTS)).json()

    assert body["items"][0]["failed_recent_count"] == 1


# ── isolation: one project's metrics must not bleed into another ──────────────


async def test_metrics_do_not_bleed_between_projects_in_list(env: dict[str, str]) -> None:
    api = Harness(env)
    rich_id = await create_project(api, "Rich Project")
    zero_id = await create_project(api, "Zero Project")
    api.runs.add(
        a_run(
            project_id=rich_id, spend_usd=Decimal("7.00"), started_at=THIS_MONTH, status="needs_you"
        )
    )

    async with api.client() as client:
        body = (await client.get(PROJECTS)).json()

    by_id = {item["id"]: item for item in body["items"]}
    assert by_id[rich_id]["monthly_spend_usd"] == "7.00"
    assert by_id[rich_id]["needs_you_count"] == 1
    assert by_id[zero_id]["monthly_spend_usd"] == "0.00"
    assert by_id[zero_id]["needs_you_count"] == 0


async def test_get_by_id_returns_correct_monthly_spend(env: dict[str, str]) -> None:
    api = Harness(env)
    project_id = await create_project(api, "Detail Project")
    api.runs.add(a_run(project_id=project_id, spend_usd=Decimal("3.50"), started_at=THIS_MONTH))

    async with api.client() as client:
        body = (await client.get(f"{PROJECTS}/{project_id}")).json()

    assert body["monthly_spend_usd"] == "3.50"
