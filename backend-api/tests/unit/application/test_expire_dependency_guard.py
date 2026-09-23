"""`expire()` guard: dependency parks never expire via the 30-day timer (story 5-4).

AC coverage:
- `expire()` on a dependency-parked Run logs a message and returns without calling
  `expire_run` — the timer does not apply to dependency parks.
- `expire()` on a non-dependency park (e.g., `blocked`) still expires normally.
- No gate record with event="failed" is written when a dependency park is skipped.
"""

from __future__ import annotations

from decimal import Decimal

from structlog.testing import capture_logs

from orchestrator.application.steps import StepPorts
from orchestrator.application.use_cases.walk import WalkPorts, expire
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

BUDGET = Decimal("10.00")
WORK_DIR = "/work"


def a_parked_run(park_kind: str, **over: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "park_kind": park_kind,
        "park_path": None if park_kind == "dependency" else "stories[0].build",
        "park_reason": "because",
        "budget_usd": BUDGET,
        "created_at": EPOCH,
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def make_walk_ports(run: Run, extra_runs: list[Run] | None = None) -> WalkPorts:
    all_runs = [run] + (extra_runs or [])
    uow = FakeUnitOfWork()
    clock = FakeClock()
    writers = WriterPorts(
        runs=FakeRunRepository(all_runs),
        steps=FakeStepRunRepository(),
        attempts=FakeAttemptRepository(),
        records=FakeGateRecordRepository(),
        uow=uow,
        clock=clock,
    )
    return WalkPorts(
        writers=writers,
        step=StepPorts(git=FakeGit(), clock=clock, work_dir=WORK_DIR),
    )


# ── dependency park guard ──────────────────────────────────────────────────────────────────


def test_expire_skips_dependency_parked_run_status_unchanged() -> None:
    run = a_parked_run("dependency")
    walk_ports = make_walk_ports(run)

    status = expire(walk_ports, run.id)

    stored = walk_ports.writers.runs.get(run.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert status == "needs_you"


def test_expire_logs_skip_for_dependency_park() -> None:
    run = a_parked_run("dependency")
    walk_ports = make_walk_ports(run)

    with capture_logs() as logs:
        expire(walk_ports, run.id)

    assert any("dependency" in str(log).lower() for log in logs)


def test_expire_does_not_write_failed_record_for_dependency_park() -> None:
    run = a_parked_run("dependency")
    walk_ports = make_walk_ports(run)

    expire(walk_ports, run.id)

    records = walk_ports.writers.records.list_for_run(run.id)
    assert not any(r.event == "failed" for r in records)


def test_expire_does_not_transition_dependency_park_to_failed() -> None:
    run = a_parked_run("dependency")
    walk_ports = make_walk_ports(run)

    expire(walk_ports, run.id)

    stored = walk_ports.writers.runs.get(run.id)
    assert stored is not None
    assert stored.status != "failed"


# ── non-dependency parks still expire ─────────────────────────────────────────────────────


def test_expire_expires_blocked_park_to_failed() -> None:
    run = a_parked_run("blocked")
    walk_ports = make_walk_ports(run)

    status = expire(walk_ports, run.id)

    stored = walk_ports.writers.runs.get(run.id)
    assert stored is not None
    assert stored.status == "failed"
    assert status == "failed"


def test_expire_expired_blocked_park_writes_failed_record() -> None:
    run = a_parked_run("blocked")
    walk_ports = make_walk_ports(run)

    expire(walk_ports, run.id)

    records = walk_ports.writers.records.list_for_run(run.id)
    assert any(r.event == "failed" for r in records)


# ── expire parks dependency-waiting dependents ────────────────────────────────────────────


def test_expire_parks_dependency_waiting_run_when_predecessor_expires() -> None:
    """When a non-dependency park expires to failed, its dependents are parked (story 5-4 P4)."""
    predecessor = a_parked_run("blocked")
    # Revised for fan-in after_run_ids (multi-repo initiative S1, spine AD-12/AD-13
    # amendment, 2026-09-23): the 1:1 pointer became a list.
    dependent = build_run("queued", after_run_ids=(predecessor.id,))
    walk_ports = make_walk_ports(predecessor, extra_runs=[dependent])

    expire(walk_ports, predecessor.id)

    stored = walk_ports.writers.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"
