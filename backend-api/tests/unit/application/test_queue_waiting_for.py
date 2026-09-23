"""`list_queue` includes dependency-waiting Runs with reason="waiting for runs {…}".

Revised for fan-in after_run_ids (multi-repo initiative S1, spine AD-12/AD-13 amendment,
2026-09-23): AD-12's queue reason became the plural `waiting for runs {x, …}`, because a
Run now waits for a list of predecessors rather than for one.

AC coverage:
- A queued run with after_run_ids set appears with reason=REASON_WAITING_FOR, position=None.
- Two predecessors are both named, in declared order, comma-separated.
- A queued run with an empty after_run_ids (saved run) does NOT appear as a dependency row.
- Dependency rows sort after saved rows (_order_key returns (4, 0)).
- Saved run and dependency-waiting run are correctly separated.
- _order_key for dependency rows with a non-empty after_run_ids.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.use_cases.queue import (
    REASON_SAVED,
    REASON_WAITING_FOR,
    QueuePorts,
    QueueRow,
    _order_key,
    list_queue,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BUDGET = Decimal("10")
PREDECESSOR_ID = new_id()
SECOND_PREDECESSOR_ID = new_id()


def a_run(
    *, engine_ref: dict | None = None, after_run_ids: tuple = (), status: str = "queued"
) -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status=status,  # type: ignore[arg-type]
        budget_usd=BUDGET,
        created_at=NOW,
        engine_ref=engine_ref if engine_ref is not None else {},
        after_run_ids=after_run_ids,
    )


def ports_with(runs: list[Run]) -> tuple[QueuePorts, FakeWorkflowEngine]:
    engine = FakeWorkflowEngine()
    ports = QueuePorts(
        engine=engine,
        runs=FakeRunRepository(runs),
        steps=FakeStepRunRepository(),
        clock=FakeClock(NOW),
        max_active_runs=2,
    )
    return ports, engine


# ── dependency-waiting run appears in queue ────────────────────────────────────────────────


def test_dependency_waiting_run_appears_with_waiting_for_reason() -> None:
    dep = a_run(after_run_ids=(PREDECESSOR_ID,))
    ports, _ = ports_with([dep])

    view = list_queue(ports)

    assert len(view.items) == 1
    assert view.items[0].run.id == dep.id
    assert str(PREDECESSOR_ID) in view.items[0].reason
    assert view.items[0].position is None


def test_dependency_waiting_run_reason_matches_constant_format() -> None:
    dep = a_run(after_run_ids=(PREDECESSOR_ID,))
    ports, _ = ports_with([dep])

    view = list_queue(ports)

    expected_reason = REASON_WAITING_FOR.format(runs=str(PREDECESSOR_ID))
    assert view.items[0].reason == expected_reason


def test_dependency_waiting_run_names_every_predecessor_in_declared_order() -> None:
    """Fan-in: AD-12's `waiting for runs {x, …}` lists the whole predecessor list."""
    dep = a_run(after_run_ids=(PREDECESSOR_ID, SECOND_PREDECESSOR_ID))
    ports, _ = ports_with([dep])

    view = list_queue(ports)

    expected = REASON_WAITING_FOR.format(
        runs=f"{PREDECESSOR_ID}, {SECOND_PREDECESSOR_ID}",
    )
    assert view.items[0].reason == expected


def test_dependency_waiting_waiting_since_is_created_at() -> None:
    dep = a_run(after_run_ids=(PREDECESSOR_ID,))
    ports, _ = ports_with([dep])

    view = list_queue(ports)

    assert view.items[0].waiting_since == NOW


# ── saved vs dependency separation ─────────────────────────────────────────────────────────


def test_saved_run_without_after_run_ids_appears_as_saved_not_dependency() -> None:
    saved = a_run()  # after_run_ids=()
    ports, _ = ports_with([saved])

    view = list_queue(ports)

    assert len(view.items) == 1
    assert view.items[0].reason == REASON_SAVED


TWO_ROWS = 2


def test_saved_and_dependency_runs_appear_as_separate_rows() -> None:
    saved = a_run()  # after_run_ids=()
    dep = a_run(after_run_ids=(PREDECESSOR_ID,))
    ports, _ = ports_with([saved, dep])

    view = list_queue(ports)

    assert len(view.items) == TWO_ROWS
    reasons = {item.reason for item in view.items}
    assert REASON_SAVED in reasons
    expected_waiting = REASON_WAITING_FOR.format(runs=str(PREDECESSOR_ID))
    assert expected_waiting in reasons


# ── ordering ───────────────────────────────────────────────────────────────────────────────


def test_order_key_for_dependency_row_is_4_0() -> None:
    dep = a_run(after_run_ids=(PREDECESSOR_ID,))
    row = QueueRow(
        position=None,
        run=dep,
        next_step_label="",
        reason=REASON_WAITING_FOR.format(runs=str(PREDECESSOR_ID)),
        waiting_since=NOW,
        waiting_seconds=0.0,
    )

    assert _order_key(row) == (4, 0)


def test_dependency_row_sorts_after_saved_row() -> None:
    saved_run = a_run()
    dep = a_run(after_run_ids=(PREDECESSOR_ID,))
    saved_row = QueueRow(
        position=None,
        run=saved_run,
        next_step_label="",
        reason=REASON_SAVED,
        waiting_since=NOW,
        waiting_seconds=0.0,
    )
    dep_row = QueueRow(
        position=None,
        run=dep,
        next_step_label="",
        reason=REASON_WAITING_FOR.format(runs=str(PREDECESSOR_ID)),
        waiting_since=NOW,
        waiting_seconds=0.0,
    )

    ordered = sorted([dep_row, saved_row], key=_order_key)

    assert ordered[0].reason == REASON_SAVED
    assert ordered[1].run.after_run_ids == (PREDECESSOR_ID,)
