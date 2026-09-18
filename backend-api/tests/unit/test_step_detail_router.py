"""`GET /api/v1/runs/{run_id}/steps/{step_path}` (story 1-2) over an ASGI transport.

Covers every row of the I/O matrix in the intent contract:
- Agent step with 2 attempts (n=1 done, n=2 running) — newest first, result extracted from git
- Shell step — dispatch_prompt null, command equals with_resolved['run'], result null
- Step planned, no attempts — attempts=[]
- Skipped step — reason present, attempts absent (empty list)
- Run not found → 404 problem+json
- Step path not in run → 404 problem+json
- Git unavailable (git=None in ports) → result=null for all attempts
- Spec file absent at end_sha → result=null for that attempt
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import quote
from uuid import UUID

import httpx
import pytest

from orchestrator.api.providers import run_view_ports
from orchestrator.api.routers import step_detail as router_module
from orchestrator.api.schemas.step_detail import (  # noqa: F401 — AD-18 pairing
    AttemptDetailOut,
    StepDetailOut,
)
from orchestrator.application.use_cases.run_view_types import RunViewPorts
from orchestrator.application.use_cases.step_detail import (  # noqa: F401 — AD-18 pairing
    _dispatch_prompt,
    _extract_result,
    _retry_prompt,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.git import FakeGit
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
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"

RUNS = "/api/v1/runs"
NOW = datetime(2026, 9, 16, tzinfo=UTC)

#: A representative end SHA present on a completed attempt.
END_SHA = "abc123def456abc123def456abc123def456abc1"

#: Spec folder and story id for agent steps.
SPEC_FOLDER = "_bmad-output/planning-artifacts/mvp"
STORY_ID = "1-1"

#: The story file basename and its path inside the spec folder.
STORY_FILE_NAME = f"{STORY_ID}-serve-attempt-log.md"
STORY_FILE_PATH = f"{SPEC_FOLDER}/stories/{STORY_FILE_NAME}"

#: A spec file that contains an ## Auto Run Result section.
SPEC_FILE_WITH_RESULT = """\
# Story 1-1

## Some Other Section

some content

## Auto Run Result

all tests passed

## Another Section

more content
"""

#: A spec file missing the ## Auto Run Result section.
SPEC_FILE_WITHOUT_RESULT = """\
# Story 1-1

## Some Other Section

content only

"""

#: Unknown UUID for not-found scenarios.
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


# ── helpers ──────────────────────────────────────────────────────────────────


def _run(*, worktree_path: str | None = f"/work/{SPEC_FOLDER}") -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        created_at=NOW,
        worktree_path=worktree_path,
    )


def _agent_step(run_id: UUID, *, status: str = "running") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=1,
        path="steps[0]",
        label="story 1-1: serve attempt log",
        kind="agent",
        gate="liveness",
        status=status,  # type: ignore[arg-type]
        with_resolved={
            "skill": "bmad-dev-story",
            "spec_folder": SPEC_FOLDER,
            "story_id": STORY_ID,
            "harness": "claude",
            "model": "claude-opus-4-5",
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


def _skipped_step(run_id: UUID) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=3,
        path="steps[2]",
        label="already done",
        kind="agent",
        gate="unvalidated",
        status="skipped",
        reason="skipped · already done",
    )


def _planned_step(run_id: UUID) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=4,
        path="steps[3]",
        label="future step",
        kind="agent",
        gate="unvalidated",
        status="planned",
    )


def _attempt(
    step: StepRun,
    *,
    n: int,
    status: str = "done",
    end_sha: str | None = END_SHA,
) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=step.run_id,
        step_run_id=step.id,
        n=n,
        status=status,  # type: ignore[arg-type]
        started_at=datetime(2026, 9, 16, 10, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 9, 16, 10, 5, 0, tzinfo=UTC) if status != "running" else None,
        harness="claude",
        model="claude-opus-4-5",
        session_id=f"sess-{n}",
        exit_code=0 if status == "done" else None,
        tokens_in=1000,
        tokens_out=500,
        cost_usd=Decimal("0.05"),
        end_sha=end_sha,
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
    """A thin wrapper around the ASGI app for step-detail router tests."""

    def __init__(
        self,
        env: dict[str, str],
        *,
        git: FakeGit | None = None,
        run: Run | None = None,
        steps: list[StepRun] | None = None,
        attempts: list[Attempt] | None = None,
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
            git=git,
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

    def anonymous(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app, raise_app_exceptions=False),
            base_url="http://backend-api",
        )

    def url(self, run_id: UUID | str, step_path: str) -> str:
        encoded = quote(step_path, safe="")
        return f"{RUNS}/{run_id}/steps/{encoded}"


# ── Structural test ──────────────────────────────────────────────────────────


def test_the_router_declares_exactly_one_operation() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert routes == [(["GET"], "/runs/{run_id}/steps/{step_path}")]
    for route in router_module.router.routes:
        assert route.dependencies == []


# ── Agent step, two attempts ─────────────────────────────────────────────────


@pytest.fixture
def agent_api(env: dict[str, str]) -> Api:
    git = FakeGit(
        listings={(END_SHA, f"{SPEC_FOLDER}/stories"): [STORY_FILE_PATH]},
        files={(END_SHA, STORY_FILE_PATH): SPEC_FILE_WITH_RESULT},
    )
    run = _run()
    step = _agent_step(run.id, status="running")
    a1 = _attempt(step, n=1, status="done", end_sha=END_SHA)
    a2 = _attempt(step, n=2, status="running", end_sha=None)
    return Api(env, git=git, run=run, steps=[step], attempts=[a1, a2])


async def test_agent_step_returns_200(agent_api: Api, env: dict[str, str]) -> None:
    step = next(iter(agent_api._step_repo.steps.values()))
    async with agent_api.client() as client:
        resp = await client.get(agent_api.url(agent_api.run_id, step.path))
    assert resp.status_code == HTTP_OK


async def test_agent_step_response_has_step_fields(agent_api: Api) -> None:
    step = next(iter(agent_api._step_repo.steps.values()))
    async with agent_api.client() as client:
        resp = await client.get(agent_api.url(agent_api.run_id, step.path))
    body = resp.json()
    assert body["path"] == step.path
    assert body["kind"] == "agent"
    assert body["status"] == "running"
    assert "with_resolved" in body


async def test_agent_step_attempts_newest_first(agent_api: Api) -> None:
    """Attempts list is newest first (highest n first)."""
    step = next(iter(agent_api._step_repo.steps.values()))
    async with agent_api.client() as client:
        resp = await client.get(agent_api.url(agent_api.run_id, step.path))
    body = resp.json()
    attempts = body["attempts"]
    assert len(attempts) == 2  # noqa: PLR2004 — two attempts seeded in the fixture
    assert attempts[0]["n"] == 2  # noqa: PLR2004 — n=2 is the newest (running)
    assert attempts[1]["n"] == 1


async def test_agent_step_running_attempt_has_null_result(agent_api: Api) -> None:
    """n=2 is running (end_sha=None) → result is null."""
    step = next(iter(agent_api._step_repo.steps.values()))
    async with agent_api.client() as client:
        resp = await client.get(agent_api.url(agent_api.run_id, step.path))
    body = resp.json()
    newest = body["attempts"][0]
    assert newest["n"] == 2  # noqa: PLR2004 — n=2 is the running attempt
    assert newest["result"] is None


async def test_agent_step_done_attempt_has_extracted_result(agent_api: Api) -> None:
    """n=1 is done with end_sha → result contains the ## Auto Run Result section text."""
    step = next(iter(agent_api._step_repo.steps.values()))
    async with agent_api.client() as client:
        resp = await client.get(agent_api.url(agent_api.run_id, step.path))
    body = resp.json()
    done_attempt = body["attempts"][1]
    assert done_attempt["n"] == 1
    assert done_attempt["result"] is not None
    assert "all tests passed" in done_attempt["result"]


async def test_agent_step_has_dispatch_prompt(agent_api: Api) -> None:
    """dispatch_prompt is set for an agent step with skill."""
    step = next(iter(agent_api._step_repo.steps.values()))
    async with agent_api.client() as client:
        resp = await client.get(agent_api.url(agent_api.run_id, step.path))
    body = resp.json()
    # Both attempts share the same dispatch_prompt (from with_resolved)
    for attempt in body["attempts"]:
        assert attempt["dispatch_prompt"] is not None
        assert "bmad-dev-story" in attempt["dispatch_prompt"]


# ── Shell step ───────────────────────────────────────────────────────────────


@pytest.fixture
def shell_api(env: dict[str, str]) -> Api:
    run = _run()
    step = _shell_step(run.id)
    att = _shell_attempt(step)
    return Api(env, run=run, steps=[step], attempts=[att])


async def test_shell_step_dispatch_prompt_is_null(shell_api: Api) -> None:
    step = next(iter(shell_api._step_repo.steps.values()))
    async with shell_api.client() as client:
        resp = await client.get(shell_api.url(shell_api.run_id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["dispatch_prompt"] is None


async def test_shell_step_command_equals_run_value(shell_api: Api) -> None:
    step = next(iter(shell_api._step_repo.steps.values()))
    async with shell_api.client() as client:
        resp = await client.get(shell_api.url(shell_api.run_id, step.path))
    body = resp.json()
    assert body["attempts"][0]["command"] == "make test"


# ── Step planned, no attempts ─────────────────────────────────────────────────


@pytest.fixture
def planned_api(env: dict[str, str]) -> Api:
    run = _run()
    step = _planned_step(run.id)
    return Api(env, run=run, steps=[step], attempts=[])


async def test_planned_step_returns_empty_attempts(planned_api: Api) -> None:
    step = next(iter(planned_api._step_repo.steps.values()))
    async with planned_api.client() as client:
        resp = await client.get(planned_api.url(planned_api.run_id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"] == []
    assert body["status"] == "planned"


# ── Skipped step ─────────────────────────────────────────────────────────────


@pytest.fixture
def skipped_api(env: dict[str, str]) -> Api:
    run = _run()
    step = _skipped_step(run.id)
    return Api(env, run=run, steps=[step], attempts=[])


async def test_skipped_step_carries_reason(skipped_api: Api) -> None:
    step = next(iter(skipped_api._step_repo.steps.values()))
    async with skipped_api.client() as client:
        resp = await client.get(skipped_api.url(skipped_api.run_id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["reason"] == "skipped · already done"
    assert body["attempts"] == []


# ── Run not found ─────────────────────────────────────────────────────────────


async def test_unknown_run_is_a_404(env: dict[str, str]) -> None:
    api = Api(env)
    async with api.client() as client:
        resp = await client.get(api.url(UNKNOWN_ID, "steps[0]"))
    assert resp.status_code == HTTP_NOT_FOUND
    assert resp.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── Step path not in run ──────────────────────────────────────────────────────


async def test_unknown_step_path_is_a_404(env: dict[str, str]) -> None:
    run = _run()
    api = Api(env, run=run, steps=[], attempts=[])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, "steps[0]"))
    assert resp.status_code == HTTP_NOT_FOUND
    assert resp.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── Git unavailable ───────────────────────────────────────────────────────────


async def test_git_none_results_in_null_result(env: dict[str, str]) -> None:
    """When git=None in ports, result is null for all attempts."""
    run = _run()
    step = _agent_step(run.id)
    a1 = _attempt(step, n=1, status="done", end_sha=END_SHA)
    api = Api(env, git=None, run=run, steps=[step], attempts=[a1])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["result"] is None


# ── Spec file absent ──────────────────────────────────────────────────────────


async def test_spec_file_absent_gives_null_result(env: dict[str, str]) -> None:
    """When git.read_file returns None, result is null."""
    git = FakeGit(
        listings={(END_SHA, f"{SPEC_FOLDER}/stories"): [STORY_FILE_PATH]},
        files={},  # file absent — returns None
    )
    run = _run()
    step = _agent_step(run.id)
    a1 = _attempt(step, n=1, status="done", end_sha=END_SHA)
    api = Api(env, git=git, run=run, steps=[step], attempts=[a1])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["result"] is None


# ── Auth ──────────────────────────────────────────────────────────────────────


async def test_without_the_bearer_it_is_a_401(env: dict[str, str]) -> None:
    run = _run()
    step = _planned_step(run.id)
    api = Api(env, run=run, steps=[step])
    async with api.anonymous() as client:
        resp = await client.get(api.url(run.id, step.path))
    assert resp.status_code == HTTP_UNAUTHORIZED


# ── dispatch_prompt: `prompt` key (not skill) ─────────────────────────────────


def _prompt_step(run_id: UUID) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=5,
        path="steps[4]",
        label="prompt step",
        kind="agent",
        gate="unvalidated",
        status="done",
        with_resolved={"prompt": "implement this feature"},
    )


async def test_prompt_key_in_with_resolved_produces_dispatch_prompt(
    env: dict[str, str],
) -> None:
    """Line 46: `_dispatch_prompt` returns `str(prompt)` when `prompt` key present."""
    run = _run()
    step = _prompt_step(run.id)
    att = Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=step.id,
        n=1,
        status="done",
        started_at=NOW,
        ended_at=NOW,
    )
    api = Api(env, run=run, steps=[step], attempts=[att])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["dispatch_prompt"] == "implement this feature"


# ── retry_prompt: `retry.prompt` key present ─────────────────────────────────


async def test_retry_prompt_extracted_from_retry_dict(env: dict[str, str]) -> None:
    """Lines 59-60: `_retry_prompt` returns the prompt inside the retry dict."""
    run = _run()
    step = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=6,
        path="steps[5]",
        label="retry step",
        kind="agent",
        gate="unvalidated",
        status="done",
        with_resolved={"skill": "bmad-dev-story", "retry": {"prompt": "retry text", "max": 3}},
    )
    att = Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=step.id,
        n=1,
        status="done",
        started_at=NOW,
        ended_at=NOW,
    )
    api = Api(env, run=run, steps=[step], attempts=[att])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["retry_prompt"] == "retry text"


# ── result extraction: spec_folder absent in with_resolved ────────────────────


async def test_no_spec_folder_gives_null_result(env: dict[str, str]) -> None:
    """Line 84: `_extract_result` returns None when spec_folder absent."""
    git = FakeGit(
        listings={(END_SHA, f"{SPEC_FOLDER}/stories"): [STORY_FILE_PATH]},
        files={(END_SHA, STORY_FILE_PATH): SPEC_FILE_WITH_RESULT},
    )
    run = _run()
    step = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=7,
        path="steps[6]",
        label="no-folder step",
        kind="agent",
        gate="unvalidated",
        status="done",
        with_resolved={"skill": "bmad-dev-story"},  # no spec_folder, no story_id
    )
    att = _attempt(step, n=1, status="done", end_sha=END_SHA)
    api = Api(env, git=git, run=run, steps=[step], attempts=[att])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["result"] is None


# ── result extraction: listing has no file matching story_id ──────────────────


async def test_no_matching_story_file_gives_null_result(env: dict[str, str]) -> None:
    """Line 93: `_extract_result` returns None when no listing entry starts with story_id."""
    git = FakeGit(
        listings={
            (END_SHA, f"{SPEC_FOLDER}/stories"): [f"{SPEC_FOLDER}/stories/2-99-unrelated.md"]
        },
        files={(END_SHA, f"{SPEC_FOLDER}/stories/2-99-unrelated.md"): SPEC_FILE_WITH_RESULT},
    )
    run = _run()
    step = _agent_step(run.id)
    att = _attempt(step, n=1, status="done", end_sha=END_SHA)
    api = Api(env, git=git, run=run, steps=[step], attempts=[att])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["result"] is None


# ── result extraction: file has no ## Auto Run Result heading ─────────────────


async def test_spec_file_without_result_heading_gives_null_result(env: dict[str, str]) -> None:
    """Lines 103-104: `_extract_result` returns None when heading is absent from file."""
    git = FakeGit(
        listings={(END_SHA, f"{SPEC_FOLDER}/stories"): [STORY_FILE_PATH]},
        files={(END_SHA, STORY_FILE_PATH): SPEC_FILE_WITHOUT_RESULT},
    )
    run = _run()
    step = _agent_step(run.id)
    att = _attempt(step, n=1, status="done", end_sha=END_SHA)
    api = Api(env, git=git, run=run, steps=[step], attempts=[att])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert body["attempts"][0]["result"] is None


# ── result extraction: result section at end of file (no following heading) ───

#: A spec file where the result section is the last section (no following ##).
SPEC_FILE_RESULT_AT_END = """\
# Story 1-1

## Auto Run Result

result text at end of file
"""


async def test_result_section_at_end_of_file_is_extracted(env: dict[str, str]) -> None:
    """Lines 107-112: natural for-loop exhaustion when no ## heading follows the result."""
    git = FakeGit(
        listings={(END_SHA, f"{SPEC_FOLDER}/stories"): [STORY_FILE_PATH]},
        files={(END_SHA, STORY_FILE_PATH): SPEC_FILE_RESULT_AT_END},
    )
    run = _run()
    step = _agent_step(run.id)
    att = _attempt(step, n=1, status="done", end_sha=END_SHA)
    api = Api(env, git=git, run=run, steps=[step], attempts=[att])
    async with api.client() as client:
        resp = await client.get(api.url(run.id, step.path))
    body = resp.json()
    assert resp.status_code == HTTP_OK
    assert "result text at end of file" in body["attempts"][0]["result"]
