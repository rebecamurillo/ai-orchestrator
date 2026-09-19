"""TDD gate for `reply_available` in `run_detail()` (story 3-4).

Four I/O-matrix rows:
1. True  — harness is resumable and the latest attempt has a session_id.
2. False — harness is not resumable (capabilities.resume = False).
3. False — harness is resumable but the latest attempt has no session_id.
4. False — `harness_is_resumable` is None (port not wired).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from orchestrator.application.use_cases.run_views import RunViewPorts, run_detail
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

NOW = datetime(2026, 9, 17, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-000000000aa1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-000000000bb1")


def _run() -> Run:
    return Run(
        id=new_id(),
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        template_name="epic",
        template_version=1,
        inputs={"base_branch": "main"},
        status="needs_you",
        park_kind="blocked",
        budget_usd=None,
        created_at=NOW,
    )


def _row(run: Run) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=1,
        path="epics[0].stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="blocked",
    )


def _attempt(run: Run, row: StepRun, *, session_id: str | None, harness: str) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=row.id,
        n=1,
        status="blocked",
        harness=harness,
        session_id=session_id,
    )


def _ports(
    run: Run,
    row: StepRun,
    attempt: Attempt,
    *,
    harness_is_resumable: object = None,
) -> RunViewPorts:
    runs = FakeRunRepository()
    runs.add(run)
    steps = FakeStepRunRepository()
    steps.add_many([row])
    attempts = FakeAttemptRepository([attempt])
    return RunViewPorts(
        runs=runs,
        steps=steps,
        attempts=attempts,
        gate_records=FakeGateRecordRepository(),
        projects=FakeProjectRepository([]),
        repositories=FakeRepositoryRepository([]),
        logs=FakeLogReader(),
        clock=FakeClock(NOW),
        harness_is_resumable=harness_is_resumable,  # type: ignore[arg-type]
    )


def test_reply_available_true_when_resumable_and_session_id_recorded() -> None:
    run = _run()
    row = _row(run)
    attempt = _attempt(run, row, session_id="ses-abc123", harness="claude")
    ports = _ports(run, row, attempt, harness_is_resumable=lambda name: name == "claude")

    detail = run_detail(ports, run.id)

    assert detail.reply_available is True


def test_reply_available_false_when_harness_not_resumable() -> None:
    run = _run()
    row = _row(run)
    attempt = _attempt(run, row, session_id="ses-abc123", harness="opencode")
    ports = _ports(run, row, attempt, harness_is_resumable=lambda name: False)

    detail = run_detail(ports, run.id)

    assert detail.reply_available is False


def test_reply_available_false_when_session_id_is_none() -> None:
    run = _run()
    row = _row(run)
    attempt = _attempt(run, row, session_id=None, harness="claude")
    ports = _ports(run, row, attempt, harness_is_resumable=lambda name: True)

    detail = run_detail(ports, run.id)

    assert detail.reply_available is False


def test_reply_available_false_when_harness_is_resumable_not_wired() -> None:
    """The safe-unwired case: `RunViewPorts` built without `harness_is_resumable`
    degrades to `reply_available=False` rather than failing (same pattern as `terminal`)."""
    run = _run()
    row = _row(run)
    attempt = _attempt(run, row, session_id="ses-abc123", harness="claude")
    ports = _ports(run, row, attempt)  # harness_is_resumable omitted

    detail = run_detail(ports, run.id)

    assert detail.reply_available is False
