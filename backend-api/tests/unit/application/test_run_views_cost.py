"""`run_detail`'s new `cost_usd` sums (5.3) — does not touch the frozen `test_run_views.py`.

One scenario, the story spec's own AC: a Run with two story frames of two attempts each —
each `StepRowView.cost_usd` sums its own row's attempts, each `StoryCell.cost_usd` sums its
frame's rows, and `cost.spent_usd`/`cost.provisional` (pre-existing, off `run.spend_usd` and
any provisional attempt) are unaffected by the new fields.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.use_cases.run_views import RunViewPorts, run_detail
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
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

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000b1")


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
        "status": "running",
        "budget_usd": Decimal("100"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_build_row(run: Run, *, seq: int, story_id: str) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=seq,
        path=f"stories[{seq}].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="done",
        story_id=story_id,
    )


def a_commit_row(run: Run, *, seq: int, story_id: str) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=seq,
        path=f"stories[{seq - 1}].commit-guard",
        label="commit-guard",
        kind="git.commit",
        gate="deterministic",
        status="done",
        story_id=story_id,
    )


def an_attempt(row: StepRun, run: Run, *, n: int, cost_usd: Decimal, provisional: bool) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=row.id,
        n=n,
        status="done",
        cost_usd=cost_usd,
        cost_provisional=provisional,
    )


class Harness:
    def __init__(self) -> None:
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.gate_records = FakeGateRecordRepository()
        self.projects = FakeProjectRepository([project()])
        self.repositories = FakeRepositoryRepository([repository()])
        self.logs = FakeLogReader()
        self.clock = FakeClock(NOW)

    def ports(self) -> RunViewPorts:
        return RunViewPorts(
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            gate_records=self.gate_records,
            projects=self.projects,
            repositories=self.repositories,
            logs=self.logs,
            clock=self.clock,
        )


@pytest.fixture
def harness() -> Harness:
    return Harness()


def test_step_and_story_cost_sums_over_two_frames_of_two_attempts_each(harness: Harness) -> None:
    run = a_run(spend_usd=Decimal("10.00"))
    harness.runs.add(run)

    build_0 = a_build_row(run, seq=1, story_id="s0")
    commit_0 = a_commit_row(run, seq=2, story_id="s0")
    build_1 = a_build_row(run, seq=3, story_id="s1")
    commit_1 = a_commit_row(run, seq=4, story_id="s1")
    harness.steps.add_many([build_0, commit_0, build_1, commit_1])

    harness.attempts.add(an_attempt(build_0, run, n=1, cost_usd=Decimal("1.00"), provisional=True))
    harness.attempts.add(an_attempt(build_0, run, n=2, cost_usd=Decimal("2.00"), provisional=False))
    harness.attempts.add(an_attempt(build_1, run, n=1, cost_usd=Decimal("3.00"), provisional=False))
    harness.attempts.add(an_attempt(build_1, run, n=2, cost_usd=Decimal("4.00"), provisional=False))

    detail = run_detail(harness.ports(), run.id)

    steps_by_path = {row.path: row for row in detail.steps}
    assert steps_by_path[build_0.path].cost_usd == Decimal("3.00")
    assert steps_by_path[build_1.path].cost_usd == Decimal("7.00")
    assert steps_by_path[commit_0.path].cost_usd == Decimal("0")

    cells_by_story = {cell.story_id: cell for cell in detail.stories}
    assert cells_by_story["s0"].cost_usd == Decimal("3.00")
    assert cells_by_story["s1"].cost_usd == Decimal("7.00")

    assert detail.cost.spent_usd == Decimal("10.00")
    assert detail.cost.provisional is True
