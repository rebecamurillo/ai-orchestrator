"""`run_detail`'s `terminal` block (6.7, SPEC CAP-7, FR-21) — does not touch the frozen
`test_run_views.py` or `test_run_views_attribution.py`.

Two claims, and the second is the load-bearing one:

1. A wired read publishes the resume command on the Run's own read model, beside the
   `terminal_session` flag whose value its `in_progress` is.
2. A read that was *not* wired for it publishes `terminal: null` rather than failing — the
   `tracer` precedent, and what keeps every frozen `RunViewPorts(...)` construction in this
   suite compiling and passing unchanged.

What the command itself may and may not contain is `tests/unit/test_terminal_command.py`'s
subject; this file is about where it appears and where it does not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.use_cases.run_views import RunViewPorts, run_detail
from orchestrator.application.use_cases.terminal import TerminalPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.registry import build_harnesses, build_terminal_env
from orchestrator.infrastructure.settings import Settings
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

NOW = datetime(2026, 1, 1, tzinfo=UTC)
STARTED_AT = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")
BUILD = "stories[0].build"
WORKTREE = "/work/acme/acme-app/wt/epics-1"
SESSION = "1f0a0d3c-8b17-4a9e-9c2b-2d4e6f8a0b1c"
CLAUDE_SESSION_DAYS = 30


def project() -> Project:
    return Project(
        id=PROJECT_ID,
        slug="acme",
        name="Acme",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def repository() -> Repository:
    return Repository(
        id=REPOSITORY_ID,
        project_id=PROJECT_ID,
        slug="acme-app",
        url="https://example.invalid/acme/app.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "epic",
        "template_version": 1,
        "inputs": {"base_branch": "main"},
        "status": "needs_you",
        "park_kind": "blocked",
        "park_path": BUILD,
        "park_reason": "intent gap",
        "budget_usd": Decimal("100"),
        "worktree_path": WORKTREE,
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_build_row(run: Run) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=1,
        path=BUILD,
        label="build",
        kind="agent",
        gate="liveness",
        status="blocked",
        story_id="1-1",
    )


def an_attempt(row: StepRun, run: Run, **over: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": run.id,
        "step_run_id": row.id,
        "n": 1,
        "status": "blocked",
        "started_at": STARTED_AT,
        "harness": "claude",
        "model": "claude-opus-5",
        "session_id": SESSION,
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


class Harness:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.gate_records = FakeGateRecordRepository()
        self.projects = FakeProjectRepository([project()])
        self.repositories = FakeRepositoryRepository([repository()])
        self.logs = FakeLogReader()
        self.clock = FakeClock(NOW)

    def ports(self, *, wired: bool = True) -> RunViewPorts:
        return RunViewPorts(
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            gate_records=self.gate_records,
            projects=self.projects,
            repositories=self.repositories,
            logs=self.logs,
            clock=self.clock,
            terminal=self._terminal() if wired else None,
        )

    def _terminal(self) -> TerminalPorts:
        return TerminalPorts(
            env=build_terminal_env(self.settings),
            harnesses=build_harnesses(self.settings, FakeProcessRunner()),
        )

    def park(self, **run_over: object) -> Run:
        run = a_run(**run_over)
        self.runs.add(run)
        row = a_build_row(run)
        self.steps.add_many([row])
        self.attempts.add(an_attempt(row, run))
        return run


@pytest.fixture
def harness(env: dict[str, str]) -> Harness:
    return Harness(Settings())


def test_a_wired_read_publishes_the_resume_command(harness: Harness) -> None:
    run = harness.park()

    detail = run_detail(harness.ports(), run.id)

    assert detail.terminal is not None
    assert detail.terminal.command.startswith("docker compose exec -e ORCH_RUN_ID=")
    assert detail.terminal.command.endswith(f"cd {WORKTREE} && claude --resume {SESSION}'")


def test_the_command_names_this_runs_own_project_slug(harness: Harness) -> None:
    """`ORCH_PROJECT` is the Project's slug, which the read model has to look up — a Run
    carries only the id — so the wiring is asserted rather than assumed."""
    run = harness.park()

    detail = run_detail(harness.ports(), run.id)

    assert detail.terminal is not None
    assert "-e ORCH_PROJECT=acme" in detail.terminal.command


def test_the_lifetime_is_the_parked_attempts_own_start_plus_thirty_days(
    harness: Harness,
) -> None:
    run = harness.park()

    detail = run_detail(harness.ports(), run.id)

    assert detail.terminal is not None
    assert detail.terminal.session_lifetime_ends_at == STARTED_AT + timedelta(
        days=CLAUDE_SESSION_DAYS
    )


def test_in_progress_follows_the_runs_own_terminal_session_flag(harness: Harness) -> None:
    run = harness.park(terminal_session=True)

    detail = run_detail(harness.ports(), run.id)

    assert detail.terminal is not None
    assert detail.terminal.in_progress is True
    assert detail.run.terminal_session is True


def test_a_read_that_was_not_wired_for_it_publishes_no_terminal_at_all(
    harness: Harness,
) -> None:
    """The `tracer` precedent: an unwired optional port degrades to `None`, which is what
    keeps every `RunViewPorts(...)` written before this story compiling and passing."""
    run = harness.park()

    assert run_detail(harness.ports(wired=False), run.id).terminal is None


def test_a_stop_the_escape_hatch_does_not_apply_to_publishes_no_terminal(
    harness: Harness,
) -> None:
    """A Run with no worktree — the whole `None` set is `test_terminal_command.py`'s, and
    this is the one assertion that the read model passes it through rather than inventing a
    block of its own."""
    run = harness.park(worktree_path=None)

    assert run_detail(harness.ports(), run.id).terminal is None
