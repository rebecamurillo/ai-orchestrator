"""`list_queue` and `read_activity` while an upgrade holds the instance (SPEC CAP-4, AD-30)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orchestrator.application.use_cases.instance_activity import ActivityPorts, read_activity
from orchestrator.application.use_cases.queue import (
    REASON_HELD,
    REASON_RUNNING,
    REASON_WAITING_ANSWER,
    QueuePorts,
    list_queue,
)
from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.engine import QueueEntry
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def a_run(status: str) -> Run:
    return Run(  # type: ignore[call-arg]
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status=status,  # type: ignore[arg-type]
        budget_usd=0,
        created_at=NOW,
        engine_ref={"workflow": "x"},
    )


def a_hold(expires_in: int) -> InstanceHold:
    return InstanceHold(
        id=new_id(), held_at=NOW, expires_at=NOW + timedelta(seconds=expires_in), reason="upgrade"
    )


def ports(hold: InstanceHold | None, *runs: Run, with_holds: bool = True) -> QueuePorts:
    engine = FakeWorkflowEngine()
    for run in runs:
        engine.queue[run.id] = QueueEntry(
            run_id=run.id, engine_state="pending", position=None, enqueued_at=NOW
        )
    return QueuePorts(
        engine=engine,
        runs=FakeRunRepository(list(runs)),
        steps=FakeStepRunRepository(),
        clock=FakeClock(NOW),
        max_active_runs=2,
        holds=FakeInstanceHoldRepository(hold) if with_holds else None,
    )


def reasons(queue: QueuePorts) -> dict[object, str]:
    return {row.run.id: row.reason for row in list_queue(queue).items}


def test_a_running_run_reads_held_and_a_parked_one_still_waits_for_an_answer() -> None:
    running, parked = a_run("running"), a_run("needs_you")

    queue = ports(a_hold(60), parked, running)

    assert reasons(queue) == {running.id: REASON_HELD, parked.id: REASON_WAITING_ANSWER}
    assert [row.run.id for row in list_queue(queue).items] == [running.id, parked.id]
    assert REASON_HELD == "held for upgrade"


def test_an_expired_hold_a_missing_hold_and_no_repository_read_running() -> None:
    running = a_run("running")

    for queue in (
        ports(a_hold(0), running),
        ports(None, running),
        ports(a_hold(60), running, with_holds=False),
    ):
        assert reasons(queue) == {running.id: REASON_RUNNING}


def test_the_activity_read_carries_the_hold_and_the_queue_reason() -> None:
    running = a_run("running")
    hold = a_hold(60)
    activity = read_activity(
        ActivityPorts(
            queue=ports(hold, running),
            attempts=FakeAttemptRepository(),
            dbos_application_version="1",
        )
    )

    assert activity.hold is not None
    assert (activity.hold.held_at, activity.hold.expires_at, activity.hold.reason) == (
        hold.held_at,
        hold.expires_at,
        "upgrade",
    )
    assert [run.queue_reason for run in activity.in_engine] == ["held for upgrade"]


def test_the_activity_read_has_no_hold_when_expired_absent_or_unwired() -> None:
    for queue in (ports(a_hold(0)), ports(None), ports(a_hold(60), with_holds=False)):
        activity = read_activity(
            ActivityPorts(
                queue=queue, attempts=FakeAttemptRepository(), dbos_application_version="1"
            )
        )
        assert activity.hold is None
