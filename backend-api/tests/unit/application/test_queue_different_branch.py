"""`list_queue`: different branches on the same repository do not serialize (story 5-1, AD-12).

The primary behavioral guarantee of this story: two Runs on the same repository but different
declared branches get distinct partition keys and neither blocks the other with REASON_BRANCH_HELD.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.application.use_cases.queue import (
    REASON_BRANCH_HELD,
    REASON_RUNNING,
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
        "inputs": {},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def entry(run_id: object, state: str, position: int | None) -> QueueEntry:
    return QueueEntry(run_id=run_id, engine_state=state, position=position, enqueued_at=NOW)  # type: ignore[arg-type]


# ── different-branch runs on the same repository do not block each other ─────


def test_running_on_different_branch_does_not_cause_branch_held_reason() -> None:
    """A running Run on feat/s1 does not block a queued Run on feat/s2 with REASON_BRANCH_HELD.

    The queued run should fall through to REASON_RUNNING (the running run is simply occupying
    the concurrency slot) or REASON_GLOBAL_CONCURRENCY — never REASON_BRANCH_HELD
    (story 5-1, AD-12).
    """
    running = a_run(status="running", partition_branch="feat/s1")
    queued = a_run(status="queued", partition_branch="feat/s2")

    engine = FakeWorkflowEngine()
    engine.queue[running.id] = entry(running.id, "pending", None)
    engine.queue[queued.id] = entry(queued.id, "enqueued", 1)

    ports = QueuePorts(
        engine=engine,
        runs=FakeRunRepository([running, queued]),
        steps=FakeStepRunRepository(),
        clock=FakeClock(NOW),
        max_active_runs=2,
    )

    view = list_queue(ports)

    by_id = {row.run.id: row for row in view.items}
    # The running run holds a concurrency slot; the queued run reports REASON_RUNNING.
    assert by_id[running.id].reason == REASON_RUNNING
    # The queued run must NOT report branch-held — different branches on the same repo.
    assert by_id[queued.id].reason != REASON_BRANCH_HELD.format(run="epic · feat/s1")
