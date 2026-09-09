"""`Alert.row_kind` and `Alert.checkpoint_story` (story 6-2, SPEC CAP-2): `run_detail`'s own
distinction between a spec checkpoint (parked on the `agent` row itself) and a done
checkpoint (parked on the loop's own `checkpoint` row, after the Story frame finished).

`run_views.py`'s own `test_run_views.py` is frozen and pins the fields `Alert` carried
before this story; this module is a new file rather than an addition to it, over its own
small, local fixtures — the same "small local duplication" `run_views.py`'s own module
docstring already names as this codebase's precedent for a handful of rows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

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

NOW = datetime(2026, 1, 1, tzinfo=UTC)
PROJECT_ID = UUID("01970000-0000-7000-9000-0000000000a1")
REPOSITORY_ID = UUID("01970000-0000-7000-9000-0000000000b1")
STORY_ID = "42"
TITLE = "Fix the thing"
COMMIT_MESSAGE = f"story {STORY_ID}: {TITLE} (orchestrator)"


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "park_kind": "checkpoint",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(
    run: Run, path: str, *, seq: int, kind: str, with_resolved: dict[str, object] | None = None
) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run.id,
        seq=seq,
        path=path,
        label=path.rsplit(".", maxsplit=1)[-1],
        kind=kind,
        gate="deterministic",
        status="done",
        story_id=STORY_ID,
        with_resolved=with_resolved or {},
    )


def an_attempt(row: StepRun, n: int, cost_usd: Decimal) -> Attempt:
    return Attempt(
        id=new_id(), run_id=row.run_id, step_run_id=row.id, n=n, status="done", cost_usd=cost_usd
    )


class Harness:
    """One set of fakes, wired the way `api/providers.py::run_view_ports` wires the real
    adapters — the same shape `test_run_views.py`'s own `Harness` uses."""

    def __init__(self) -> None:
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.gate_records = FakeGateRecordRepository()
        self.projects = FakeProjectRepository([])
        self.repositories = FakeRepositoryRepository([])
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


def test_a_spec_checkpoint_reports_the_agent_row_kind_and_no_summary(harness: Harness) -> None:
    """Parked directly on the `agent` row (`spec_checkpoint`): the planned file is what the
    screen shows (`GET /runs/{id}/files`), not a done-checkpoint summary."""
    run = a_run(park_path="stories[0].build")
    build = a_row(run, "stories[0].build", seq=2, kind="agent")
    harness.runs.add(run)
    harness.steps.add_many([build])

    detail = run_detail(harness.ports(), run.id)

    assert detail.alert is not None
    assert detail.alert.row_kind == "agent"
    assert detail.alert.checkpoint_story is None


def test_a_done_checkpoint_reports_the_story_summary(harness: Harness) -> None:
    """Parked on the loop's own `checkpoint` row, after the Story frame finished: the title
    read back off the commit-guard's own message, the build row's attempt count, the whole
    frame's cost, and the verify row's status."""
    run = a_run(park_path="stories[0].after")
    build = a_row(run, "stories[0].build", seq=2, kind="agent")
    verify = a_row(run, "stories[0].verify", seq=3, kind="shell")
    commit_guard = a_row(
        run,
        "stories[0].commit-guard",
        seq=4,
        kind="git.commit",
        with_resolved={"message": COMMIT_MESSAGE},
    )
    checkpoint = a_row(run, "stories[0].after", seq=5, kind="checkpoint")
    harness.steps.add_many([build, verify, commit_guard, checkpoint])
    harness.attempts.add(an_attempt(build, 1, Decimal("1.50")))
    harness.attempts.add(an_attempt(build, 2, Decimal("0.75")))
    harness.runs.add(run)

    detail = run_detail(harness.ports(), run.id)

    assert detail.alert is not None
    assert detail.alert.row_kind == "checkpoint"
    story = detail.alert.checkpoint_story
    assert story is not None
    assert story.story_id == STORY_ID
    assert story.title == TITLE
    assert story.attempts == 2  # noqa: PLR2004 — the two attempts added above
    assert story.cost_usd == Decimal("2.25")
    assert story.verify == "done"


def test_a_non_checkpoint_park_carries_no_row_kind_change(harness: Harness) -> None:
    """`blocked` is unaffected: the row kind is still read, but there is no Story frame
    summary to compute for it (only `checkpoint` builds one)."""
    run = a_run(park_kind="blocked", park_path="stories[0].build")
    build = a_row(run, "stories[0].build", seq=2, kind="agent")
    harness.runs.add(run)
    harness.steps.add_many([build])

    detail = run_detail(harness.ports(), run.id)

    assert detail.alert is not None
    assert detail.alert.row_kind == "agent"
    assert detail.alert.checkpoint_story is None
