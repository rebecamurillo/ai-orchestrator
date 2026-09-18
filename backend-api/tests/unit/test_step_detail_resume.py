"""`resume_command` and `session_lifetime_ends_at` on `AttemptDetailOut` (story 1-3).

Covers every row of the I/O matrix from the intent contract:
- `resume_command` key present and null when `terminal=None`
- `session_lifetime_ends_at` key present and null when `terminal=None`
- Both null for a shell step (attempt.command non-null)
- Both null when `attempt.session_id=None`, even with terminal wired
- `resume_command` non-null when attempt has session_id and `terminal` is wired with
  `build_harnesses(settings, FakeProcessRunner())` using the `claude` harness
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import quote
from uuid import UUID

import httpx

from orchestrator.api.providers import run_view_ports
from orchestrator.api.schemas.step_detail import AttemptDetailOut  # noqa: F401 — AD-18 pairing
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.application.use_cases.terminal import TerminalPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.registry import build_harnesses, build_terminal_env
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

HTTP_OK = 200
RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 16, tzinfo=UTC)

SPEC_FOLDER = "_bmad-output/planning-artifacts/mvp"
STORY_ID = "1-3"
#: A representative claude session id used in the resume-command path.
SESSION = "test-session-1f0a0d3c"
WORKTREE = "/work/acme/orchestrator/wt/feat-1"


# ── helpers ──────────────────────────────────────────────────────────────────


def _run() -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        created_at=NOW,
        worktree_path=WORKTREE,
    )


def _agent_step(run_id: UUID) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=1,
        path="steps[0]",
        label="story 1-3",
        kind="agent",
        gate="liveness",
        status="running",
        with_resolved={
            "skill": "bmad-dev-story",
            "spec_folder": SPEC_FOLDER,
            "story_id": STORY_ID,
            "harness": "claude",
        },
    )


def _shell_step(run_id: UUID) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=2,
        path="steps[1]",
        label="run tests",
        kind="shell",
        gate="liveness",
        status="done",
        with_resolved={"run": "make test"},
    )


def _agent_attempt(step: StepRun, *, session_id: str | None = SESSION) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=step.run_id,
        step_run_id=step.id,
        n=1,
        status="done",
        started_at=datetime(2026, 9, 16, 10, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 9, 16, 10, 5, 0, tzinfo=UTC),
        harness="claude",
        model="claude-opus-4-5",
        session_id=session_id,
        exit_code=0,
    )


def _shell_attempt(step: StepRun) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=step.run_id,
        step_run_id=step.id,
        n=1,
        status="done",
        started_at=datetime(2026, 9, 16, 10, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 9, 16, 10, 1, 0, tzinfo=UTC),
        exit_code=0,
    )


class Api:
    """A thin wrapper around the ASGI app for step-detail resume tests."""

    def __init__(
        self,
        env: dict[str, str],
        *,
        run: Run | None = None,
        steps: list[StepRun] | None = None,
        attempts: list[Attempt] | None = None,
        terminal: TerminalPorts | None = None,
    ) -> None:
        settings = Settings(**{key.lower(): value for key, value in env.items()})
        self._run = run or _run()
        self.run_id: UUID = self._run.id
        self._step_repo = FakeStepRunRepository(steps)
        self._attempt_repo = FakeAttemptRepository(attempts)
        self._run_repo = FakeRunRepository([self._run])
        ports = RunViewPorts(
            runs=self._run_repo,
            steps=self._step_repo,
            attempts=self._attempt_repo,
            gate_records=FakeGateRecordRepository(),
            projects=FakeProjectRepository(),
            repositories=FakeRepositoryRepository(),
            logs=FakeLogReader(),
            clock=FakeClock(NOW),
            terminal=terminal,
        )
        app = create_app(settings)
        app.dependency_overrides[run_view_ports] = lambda: ports
        self._app = app
        self._token = env["ORCHESTRATOR_TOKEN"]

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self._token}"},
        )

    def url(self, run_id: UUID | str, step_path: str) -> str:
        encoded = quote(step_path, safe="")
        return f"{RUNS}/{run_id}/steps/{encoded}"


def _wired_terminal(env: dict[str, str]) -> TerminalPorts:
    """Build a real `TerminalPorts` from the env fixture settings."""
    settings = Settings(**{key.lower(): value for key, value in env.items()})
    return TerminalPorts(
        env=build_terminal_env(settings),
        harnesses=build_harnesses(settings, FakeProcessRunner()),
    )


# ── resume_command and session_lifetime_ends_at null when terminal=None ──────


async def test_resume_command_key_is_present_and_null_when_terminal_none(
    env: dict[str, str],
) -> None:
    """`resume_command` is in the JSON response and null when `terminal=None` in ports."""
    run = _run()
    step = _agent_step(run.id)
    att = _agent_attempt(step)
    api = Api(env, run=run, steps=[step], attempts=[att], terminal=None)
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert "resume_command" in body["attempts"][0]
    assert body["attempts"][0]["resume_command"] is None


async def test_session_lifetime_ends_at_key_is_present_and_null_when_terminal_none(
    env: dict[str, str],
) -> None:
    """`session_lifetime_ends_at` is in the JSON response and null when `terminal=None`."""
    run = _run()
    step = _agent_step(run.id)
    att = _agent_attempt(step)
    api = Api(env, run=run, steps=[step], attempts=[att], terminal=None)
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert "session_lifetime_ends_at" in body["attempts"][0]
    assert body["attempts"][0]["session_lifetime_ends_at"] is None


# ── both null for shell step ─────────────────────────────────────────────────


async def test_shell_step_resume_fields_are_null(env: dict[str, str]) -> None:
    """Shell step (attempt.command non-null) → both resume fields null."""
    run = _run()
    step = _shell_step(run.id)
    att = _shell_attempt(step)
    api = Api(env, run=run, steps=[step], attempts=[att], terminal=None)
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["resume_command"] is None
    assert body["attempts"][0]["session_lifetime_ends_at"] is None


# ── both null when attempt.session_id=None ───────────────────────────────────


async def test_agent_attempt_without_session_id_resume_fields_are_null(
    env: dict[str, str],
) -> None:
    """`attempt.session_id=None` → both resume fields null even with terminal wired."""
    run = _run()
    step = _agent_step(run.id)
    att = _agent_attempt(step, session_id=None)
    api = Api(env, run=run, steps=[step], attempts=[att], terminal=_wired_terminal(env))
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["resume_command"] is None
    assert body["attempts"][0]["session_lifetime_ends_at"] is None


# ── resume_command non-null for wired claude attempt with session ─────────────


async def test_agent_attempt_with_session_and_wired_terminal_has_resume_command(
    env: dict[str, str],
) -> None:
    """`claude` + `session_id` + wired terminal → non-empty `resume_command` containing session."""
    run = _run()
    step = _agent_step(run.id)
    att = _agent_attempt(step, session_id=SESSION)
    api = Api(env, run=run, steps=[step], attempts=[att], terminal=_wired_terminal(env))
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    result = body["attempts"][0]["resume_command"]
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0
    assert SESSION in result
