"""A terminal Run's leftover `running` row is not a working step (retro F1, AD-30).

Cancel kills a started row's process group but leaves the row `running` and its attempt open
(AD-8 keeps that writer unchanged), so the read side must skip every row and open attempt of a
`cancelled`, `failed` or `done` Run — or one cancelled Run would refuse every hold.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers_instance import activity_ports, hold_ports
from orchestrator.application.use_cases.instance_activity import (
    ActivityPorts,
    working_steps,
)
from orchestrator.application.use_cases.instance_hold import HoldPorts
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
ACTIVITY = "/api/v1/instance/activity"
HOLD = "/api/v1/instance/hold"


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(T0)
        self.engine = FakeWorkflowEngine(clock=self.clock)
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.holds = FakeInstanceHoldRepository()
        self.uow = FakeUnitOfWork()

    def run(self, status: str) -> Run:
        run = Run(  # type: ignore[call-arg]
            id=new_id(),
            project_id=new_id(),
            repository_id=new_id(),
            template_name="epic",
            template_version=1,
            status=status,  # type: ignore[arg-type]
            budget_usd=0,
            inputs={"branch": "feat/x"},
            created_at=T0,
            engine_ref={"ref": 1},
        )
        self.runs.add(run)
        return run

    def row_with_open_attempt(
        self, run: Run, *, seq: int = 1, status: str = "running", role: str = "agent"
    ) -> StepRun:
        row = StepRun(  # type: ignore[call-arg]
            id=new_id(),
            run_id=run.id,
            seq=seq,
            path=f"steps[{seq}]",
            label="x",
            kind="agent",
            gate="deterministic",
            status=status,  # type: ignore[arg-type]
        )
        self.steps.add_many([row])
        self.attempts.add(
            Attempt(  # type: ignore[call-arg]
                id=new_id(),
                run_id=run.id,
                step_run_id=row.id,
                n=1,
                role=role,
                status="running",
                started_at=T0 - timedelta(minutes=5),
            )
        )
        return row

    def activity_ports(self) -> ActivityPorts:
        return ActivityPorts(
            queue=QueuePorts(
                engine=self.engine,
                runs=self.runs,
                steps=self.steps,
                clock=self.clock,
                max_active_runs=2,
                holds=self.holds,
            ),
            attempts=self.attempts,
            dbos_application_version="1",
        )

    def hold_ports(self) -> HoldPorts:
        return HoldPorts(
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            holds=self.holds,
            uow=self.uow,
            clock=self.clock,
        )


def a_world_with_terminal_leftovers() -> World:
    world = World()
    for status in ("cancelled", "failed"):
        run = world.run(status)
        world.row_with_open_attempt(run)
        world.row_with_open_attempt(run, seq=2, status="checkpoint", role="session")
    return world


def test_rows_and_open_attempts_of_terminal_runs_are_not_working() -> None:
    world = a_world_with_terminal_leftovers()

    assert working_steps(world.runs, world.steps, world.attempts) == []


def test_a_running_run_beside_the_leftovers_is_still_working() -> None:
    world = a_world_with_terminal_leftovers()
    live = world.run("running")
    world.row_with_open_attempt(live)

    working = working_steps(world.runs, world.steps, world.attempts)

    assert [step.run_id for step in working] == [live.id]


@pytest.fixture
def api(env: dict[str, str]) -> tuple[World, FastAPI, str]:
    world = a_world_with_terminal_leftovers()
    app = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
    app.dependency_overrides[activity_ports] = world.activity_ports
    app.dependency_overrides[hold_ports] = world.hold_ports
    return world, app, env["ORCHESTRATOR_TOKEN"]


def _client(app: FastAPI, token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://backend-api",
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_the_activity_read_lists_no_working_step_of_a_terminal_run(
    api: tuple[World, FastAPI, str],
) -> None:
    _world, app, token = api

    async with _client(app, token) as client:
        response = await client.get(ACTIVITY)

    assert response.status_code == 200  # noqa: PLR2004
    assert response.json()["working"] == []


async def test_the_hold_is_placed_while_terminal_runs_keep_running_rows(
    api: tuple[World, FastAPI, str],
) -> None:
    world, app, token = api

    async with _client(app, token) as client:
        response = await client.post(HOLD, json={"ttl_seconds": 600, "reason": "upgrade"})

    assert 200 <= response.status_code < 300  # noqa: PLR2004
    assert world.holds.hold is not None
    assert world.uow.committed is True
