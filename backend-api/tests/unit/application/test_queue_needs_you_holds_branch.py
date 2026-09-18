"""`list_queue` row 6 (story 5-1, AD-12): a `needs_you` run holds both its global-
concurrency slot AND its (Repository, branch) partition — a second queued run on the
same branch reports `"branch held by {run}"`, not `"running"`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.application.use_cases.queue import (
    REASON_BRANCH_HELD,
    QueuePorts,
    list_queue,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.engine import QueueEntry
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
REPOSITORY = new_id()
PROJECT = new_id()


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT,
        "repository_id": REPOSITORY,
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": 0,
        "inputs": {"branch": "feat/s"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def entry(run_id: object, state: str, position: int | None) -> QueueEntry:
    return QueueEntry(run_id=run_id, engine_state=state, position=position, enqueued_at=NOW)  # type: ignore[arg-type]


# ── row 6: needs_you run holds (repository, branch) partition ────────────────


def test_queued_run_reports_branch_held_when_holder_is_needs_you() -> None:
    """A needs_you run holds its partition; a second run for the same branch is
    branch-held, not globally-constrained (story 5-1, AD-12 row 6)."""
    holder = a_run(
        status="needs_you",
        partition_branch="feat/s",
        park_kind="checkpoint",
        park_path="review",
    )
    waiting = a_run(status="queued", partition_branch="feat/s")

    engine = FakeWorkflowEngine()
    engine.queue[holder.id] = entry(holder.id, "pending", None)
    engine.queue[waiting.id] = entry(waiting.id, "enqueued", 1)

    ports = QueuePorts(
        engine=engine,
        runs=FakeRunRepository([holder, waiting]),
        steps=FakeStepRunRepository(),
        clock=FakeClock(NOW),
        max_active_runs=2,
    )

    view = list_queue(ports)

    by_id = {row.run.id: row for row in view.items}
    # operator revision 2026-09-15: partition by (repository, branch)
    assert by_id[waiting.id].reason == REASON_BRANCH_HELD.format(run="epic · feat/s")
    assert by_id[waiting.id].position == 1
