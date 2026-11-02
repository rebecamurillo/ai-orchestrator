"""`role` on `AttemptDetailOut` (story 1-7, spine AD-21, ratified 2026-11-01).

The step's attempts table lists every attempt whatever its role. A `consult` or `session`
attempt carries its `role` and no terminal command; an `agent` attempt omits `role`, as
`reply_available` is omitted when it holds its default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import quote

import httpx

from orchestrator.api.providers import run_view_ports
from orchestrator.api.schemas.step_detail import AttemptDetailOut
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.application.use_cases.terminal import TerminalPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import TerminalEnvironment
from orchestrator.domain.statuses import AttemptRole
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

HTTP_OK = 200
NOW = datetime(2026, 11, 2, tzinfo=UTC)
WORKTREE = "/work/acme/widgets/wt/roles"
PATH = "stories[0].build"


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="needs_you",
        park_kind="blocked",
        park_path=PATH,
        budget_usd=Decimal("10"),
        created_at=NOW,
        worktree_path=WORKTREE,
    )


def a_row(run: Run) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=1,
        path=PATH,
        label="build",
        kind="agent",
        gate="liveness",
        status="blocked",
    )


def an_attempt(row: StepRun, n: int, role: AttemptRole) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=row.run_id,
        step_run_id=row.id,
        n=n,
        role=role,
        status="blocked",
        started_at=NOW,
        harness="claude",
        session_id=f"s{n}",
    )


async def attempts_of(env: dict[str, str], second_role: AttemptRole) -> list[dict[str, object]]:
    settings = Settings(**{key.lower(): value for key, value in env.items()})
    run = a_run()
    row = a_row(run)
    ports = RunViewPorts(
        runs=FakeRunRepository([run]),
        steps=FakeStepRunRepository([row]),
        attempts=FakeAttemptRepository(
            [an_attempt(row, 1, "agent"), an_attempt(row, 2, second_role)]
        ),
        gate_records=FakeGateRecordRepository(),
        projects=FakeProjectRepository(),
        repositories=FakeRepositoryRepository(),
        logs=FakeLogReader(),
        clock=FakeClock(NOW),
        terminal=TerminalPorts(
            env=lambda attempt, **_: TerminalEnvironment(identifiers=(), exports=()),
            harnesses={"claude": FakeHarness()},
        ),
    )
    app = create_app(settings)
    app.dependency_overrides[run_view_ports] = lambda: ports
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    headers = {"Authorization": f"Bearer {env['ORCHESTRATOR_TOKEN']}"}
    async with httpx.AsyncClient(
        transport=transport, base_url="http://backend-api", headers=headers
    ) as client:
        response = await client.get(f"/api/v1/runs/{run.id}/steps/{quote(PATH, safe='')}")
    assert response.status_code == HTTP_OK
    attempts: list[dict[str, object]] = response.json()["attempts"]
    return attempts


async def test_a_consult_attempt_is_listed_with_its_role_and_no_terminal_command(
    env: dict[str, str],
) -> None:
    consult, agent = await attempts_of(env, "consult")

    assert (consult["n"], consult["role"], consult["resume_command"]) == (2, "consult", None)
    assert "role" not in agent
    assert agent["resume_command"] is not None


async def test_a_session_attempt_is_listed_with_its_role(env: dict[str, str]) -> None:
    session, _ = await attempts_of(env, "session")

    assert (session["role"], session["resume_command"]) == ("session", None)


async def test_two_agent_attempts_carry_no_role_and_both_resume(env: dict[str, str]) -> None:
    attempts = await attempts_of(env, "agent")

    assert all("role" not in attempt for attempt in attempts)
    assert all(attempt["resume_command"] is not None for attempt in attempts)


def test_the_schema_publishes_role_as_an_optional_enum() -> None:
    schema = AttemptDetailOut.model_json_schema()

    assert "role" not in schema.get("required", [])
    assert schema["properties"]["role"]["enum"] == ["agent", "consult", "session"]
    assert "default" not in schema["properties"]["role"]
