"""`run_detail`'s new `alert.attribution` and `StepRow.latest.cost_provisional` (5.10, SPEC
CAP-10) — does not touch the frozen `test_run_views.py`.

`alert.attribution` is the blocked Question's eyebrow: the parked row's own latest Attempt's
`harness`/`model`/`ended_at`, already settled by the time a Story can block (CAP-5's own
`mark_finished`-before-`apply_step_result` ordering). `cost_provisional` is `Attempt.
cost_provisional`, carried through `StepRowView.latest` so the Steps table can mark a row's
cost estimated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.use_cases.run_graph import run_graph_for
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
ENDED_AT = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
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
        "status": "needs_you",
        "park_kind": "blocked",
        "park_path": "stories[0].build",
        "park_reason": "## Auto Run Result\n\nWhich database migration tool should this use?",
        "budget_usd": Decimal("100"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_build_row(run: Run, *, status: str = "blocked") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=1,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status=status,  # type: ignore[arg-type]
        story_id="1-1",
    )


def an_attempt(row: StepRun, run: Run, *, cost_provisional: bool = False) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=row.id,
        n=1,
        status="blocked",
        ended_at=ENDED_AT,
        harness="claude",
        model="claude-opus-4",
        cost_usd=Decimal("1.23"),
        cost_provisional=cost_provisional,
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


def test_a_blocked_park_s_alert_is_attributed_to_the_parked_row_s_latest_attempt(
    harness: Harness,
) -> None:
    run = a_run()
    harness.runs.add(run)
    row = a_build_row(run)
    harness.steps.add_many([row])
    harness.attempts.add(an_attempt(row, run))

    detail = run_detail(harness.ports(), run.id)

    assert detail.alert is not None
    assert detail.alert.attribution is not None
    assert detail.alert.attribution.harness == "claude"
    assert detail.alert.attribution.model == "claude-opus-4"
    assert detail.alert.attribution.ended_at == ENDED_AT


def test_attribution_is_none_when_the_parked_row_never_ran(harness: Harness) -> None:
    run = a_run()
    harness.runs.add(run)
    harness.steps.add_many([a_build_row(run)])
    # no attempt stored for the row

    detail = run_detail(harness.ports(), run.id)

    assert detail.alert is not None
    assert detail.alert.attribution is None


def test_attribution_is_none_off_a_run_that_is_not_parked(harness: Harness) -> None:
    run = a_run(status="running", park_kind=None, park_path=None, park_reason=None)
    harness.runs.add(run)
    row = a_build_row(run, status="running")
    harness.steps.add_many([row])
    harness.attempts.add(an_attempt(row, run))

    detail = run_detail(harness.ports(), run.id)

    assert detail.alert is None


@pytest.mark.parametrize("provisional", [True, False])
def test_a_step_row_s_latest_attempt_carries_cost_provisional(
    harness: Harness, *, provisional: bool
) -> None:
    run = a_run()
    harness.runs.add(run)
    row = a_build_row(run)
    harness.steps.add_many([row])
    harness.attempts.add(an_attempt(row, run, cost_provisional=provisional))

    detail = run_detail(harness.ports(), run.id)

    step = next(s for s in detail.steps if s.path == row.path)
    assert step.latest is not None
    assert step.latest.cost_provisional is provisional


def test_run_graph_for_still_resolves_off_its_own_new_module(harness: Harness) -> None:
    """`run_graph_for` moved to its own module (5.10, line count alone) — proven callable
    from there directly, not only through `run_views.py`'s re-export."""
    run = a_run(status="running", park_kind=None, park_path=None, park_reason=None)
    harness.runs.add(run)
    harness.steps.add_many(
        [
            StepRun(
                id=new_id(),
                run_id=run.id,
                seq=1,
                path="checkout",
                label="checkout",
                kind="git.worktree",
                gate="deterministic",
                status="done",
            )
        ]
    )

    graph = run_graph_for(harness.ports(), run.id)

    assert graph.nodes
