"""`GET /projects` and `GET /projects/{id}`: `trajectory_count` is each Project's own count,
not a value that leaks between rows of the same list response (SPEC CAP-6, UX-DR12).

`test_project_schemas_trajectory_count.py` proves `ProjectRead.of()` in isolation; this
module proves the router's own loop (`api/routers/projects.py::list_projects`) calls it once
per Project with that Project's own id — a regression here (a stale count carried from the
previous loop iteration, or every row silently reading `0`) would not turn any assertion in
the frozen `test_projects_router.py` red, because that file predates the field and never
reads it.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from orchestrator.api.providers import project_ports
from orchestrator.api.providers_trajectories import trajectory_repository
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.trajectory import GateResults, Trajectory
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository
from tests.unit.fakes.trajectories import FakeTrajectoryRepository

PROJECTS = "/api/v1/projects"
TWO_TRAJECTORIES = 2
FIVE_TRAJECTORIES = 5


class Harness:
    """`test_projects_router.py::Harness`, mirrored rather than imported — that file is
    frozen and this one additionally overrides `trajectory_repository`."""

    def __init__(self, env: dict[str, str], trajectories: FakeTrajectoryRepository) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.projects = FakeProjectRepository()
        self.crypto = FakeCrypto()
        self.clock = FakeClock()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[project_ports] = self._ports
        self.app.dependency_overrides[trajectory_repository] = lambda: trajectories
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> ProjectPorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return ProjectPorts(
            uow=self.uow, projects=self.projects, crypto=self.crypto, clock=self.clock
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


def a_trajectory(**overrides: object) -> Trajectory:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "repository_id": new_id(),
        "epic_index": 0,
        "frame": "stories[0]",
        "gate_results": GateResults(build="liveness", verify="done", commit_guard="done"),
        "recorded_at": FakeClock().now(),
    }
    fields.update(overrides)
    return Trajectory(**fields)  # type: ignore[arg-type]


async def create(api: Harness, name: str) -> str:
    async with api.client() as client:
        response = await client.post(PROJECTS, json={"name": name})
    return str(response.json()["id"])


async def test_each_row_of_the_list_carries_its_own_projects_count(
    env: dict[str, str],
) -> None:
    trajectories = FakeTrajectoryRepository()
    api = Harness(env, trajectories)
    busy_id = await create(api, "Busy Project")
    quiet_id = await create(api, "Quiet Project")
    for _ in range(TWO_TRAJECTORIES):
        trajectories.add(a_trajectory(project_id=busy_id))
    for _ in range(FIVE_TRAJECTORIES):
        trajectories.add(a_trajectory(project_id=quiet_id))

    async with api.client() as client:
        body = (await client.get(PROJECTS)).json()

    by_id = {item["id"]: item["trajectory_count"] for item in body["items"]}
    assert by_id[busy_id] == TWO_TRAJECTORIES
    assert by_id[quiet_id] == FIVE_TRAJECTORIES


async def test_get_by_id_reads_only_that_projects_own_trajectories(
    env: dict[str, str],
) -> None:
    trajectories = FakeTrajectoryRepository()
    api = Harness(env, trajectories)
    mine_id = await create(api, "Mine")
    theirs_id = await create(api, "Theirs")
    trajectories.add(a_trajectory(project_id=theirs_id))
    trajectories.add(a_trajectory(project_id=theirs_id))

    async with api.client() as client:
        body = (await client.get(f"{PROJECTS}/{mine_id}")).json()

    assert body["trajectory_count"] == 0


async def test_a_project_with_no_stored_trajectories_reads_zero_beside_one_that_has_them(
    env: dict[str, str],
) -> None:
    """The loop's first Project must not carry a nonzero count forward to the second."""
    trajectories = FakeTrajectoryRepository()
    api = Harness(env, trajectories)
    first_id = await create(api, "First")
    trajectories.add(a_trajectory(project_id=first_id))
    second_id = await create(api, "Second")

    async with api.client() as client:
        body = (await client.get(PROJECTS)).json()

    by_id = {item["id"]: item["trajectory_count"] for item in body["items"]}
    assert by_id[first_id] == 1
    assert by_id[second_id] == 0
