"""`DbosWorkflowEngine` (`infrastructure/dbos/adapter.py`): the `WorkflowEngine` port, for real.

The port is what every use case sees, so what is asserted here is the translation in both
directions — a Run id becoming a workflow id and a partition key, the engine's own queue rows
becoming `QueueEntry`, a step record becoming an `EngineRecord` — and the two rules AD-6 and
AD-12 put on it: the workflow id *is* the Run id, and there is one queue, `MAX_ACTIVE_RUNS`
wide, one Run per Repository.

Everything runs over the fake durable engine. The real one is exercised by `make e2e`, which
is also the only place the library's own behaviour is worth asserting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.values import Signal
from orchestrator.infrastructure.dbos.adapter import (
    CANCEL,
    FAILED,
    NOT_LAUNCHED,
    SUCCEEDED,
    DbosWorkflowEngine,
)
from orchestrator.infrastructure.dbos.config import (
    APP_NAME,
    HUMAN_TOPIC,
    QUEUE_NAME,
    EngineConfig,
)
from orchestrator.infrastructure.dbos.facade import ENQUEUED, PENDING, StepRecord
from orchestrator.infrastructure.dbos.walker import WalkerDeps
from tests.unit.application.writer_fixtures import a_world
from tests.unit.fakes.dbos import FakeDurableEngine, a_queued_workflow
from tests.unit.test_dbos_walker import deps_for

RUN_A = UUID("01960000-0000-7000-9000-00000000000a")
RUN_B = UUID("01960000-0000-7000-9000-00000000000b")
REPOSITORY = UUID("01960000-0000-7000-9000-0000000000ff")
CONCURRENCY = 2
EARLIER = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 6, 12, 5, tzinfo=UTC)
STEP_ID = 4


def a_config() -> EngineConfig:
    return EngineConfig(
        database_url="postgresql+psycopg://user:pw@postgres:5432/orchestrator",
        application_version="1",
        max_active_runs=CONCURRENCY,
    )


def an_engine(fake: FakeDurableEngine, deps: WalkerDeps | None = None) -> DbosWorkflowEngine:
    return DbosWorkflowEngine(a_config(), fake, deps or deps_for(a_world()))


def a_launched_engine(fake: FakeDurableEngine) -> DbosWorkflowEngine:
    engine = an_engine(fake)
    engine.launch()
    return engine


def test_it_satisfies_the_port() -> None:
    assert isinstance(an_engine(FakeDurableEngine()), WorkflowEngine)


def test_building_it_touches_the_engine_not_at_all() -> None:
    """The composition root builds this in every process, including one that never serves."""
    fake = FakeDurableEngine()

    an_engine(fake)

    assert fake.calls == []
    assert fake.declared == []


def test_launching_configures_starts_and_then_declares_the_queue() -> None:
    fake = FakeDurableEngine()

    a_launched_engine(fake)

    assert [name for name, _ in fake.calls] == ["configure", "start", "register_queue"]
    assert fake.configured is not None
    assert fake.configured["name"] == APP_NAME
    assert fake.configured["application_version"] == "1"


def test_the_queue_is_one_queue_max_active_runs_wide() -> None:
    fake = FakeDurableEngine()

    a_launched_engine(fake)

    assert ("register_queue", (QUEUE_NAME, CONCURRENCY)) in fake.calls


def test_enqueue_starts_the_walk_under_the_run_id_behind_its_repository() -> None:
    fake = FakeDurableEngine()
    engine = a_launched_engine(fake)

    reference = engine.enqueue(RUN_A, REPOSITORY)

    assert fake.enqueued == [(QUEUE_NAME, str(RUN_A), str(REPOSITORY))]
    assert reference == {"workflow_id": str(RUN_A)}


def test_enqueue_before_the_engine_is_launched_is_a_bug_and_says_so() -> None:
    engine = an_engine(FakeDurableEngine())

    with pytest.raises(RuntimeError, match=NOT_LAUNCHED):
        engine.enqueue(RUN_A, REPOSITORY)


def test_a_signal_is_sent_to_the_runs_own_topic() -> None:
    fake = FakeDurableEngine()
    engine = a_launched_engine(fake)

    engine.signal(RUN_A, Signal(kind="continue", payload={"accepted": ["a.py"]}))

    workflow_id, message, topic = fake.sent[0]
    assert workflow_id == str(RUN_A)
    assert topic == HUMAN_TOPIC.format(run_id=RUN_A)
    assert message == {"kind": "continue", "payload": {"accepted": ["a.py"]}}


def test_cancel_stops_the_workflow_of_that_run() -> None:
    fake = FakeDurableEngine()

    a_launched_engine(fake).cancel(RUN_A)

    assert fake.cancelled == [str(RUN_A)]


def test_cancel_also_ends_the_wait_a_parked_run_is_sitting_in() -> None:
    """A `recv` has no next step to raise in; without this the slot is held for 30 days."""
    fake = FakeDurableEngine()

    a_launched_engine(fake).cancel(RUN_A)

    workflow_id, message, topic = fake.sent[0]
    assert workflow_id == str(RUN_A)
    assert topic == HUMAN_TOPIC.format(run_id=RUN_A)
    assert message == {"kind": CANCEL}


def test_cancel_marks_the_workflow_before_it_ends_the_wait() -> None:
    """The other order wakes a walk that is not cancelled yet, and it takes another row."""
    fake = FakeDurableEngine()

    a_launched_engine(fake).cancel(RUN_A)

    assert [name for name, _ in fake.calls[-2:]] == ["cancel", "send"]


def test_the_queue_is_reported_oldest_first_with_positions_among_the_waiting() -> None:
    """A Run the engine is already running has no position: a position is a queue's idea."""
    fake = FakeDurableEngine(
        queued=[
            a_queued_workflow(str(RUN_B), ENQUEUED, LATER),
            a_queued_workflow(str(RUN_A), PENDING, EARLIER),
        ]
    )

    entries = a_launched_engine(fake).list_queue()

    assert [entry.run_id for entry in entries] == [RUN_A, RUN_B]
    assert [entry.engine_state for entry in entries] == ["pending", "enqueued"]
    assert [entry.position for entry in entries] == [None, 1]
    assert [entry.enqueued_at for entry in entries] == [EARLIER, LATER]


def test_a_state_the_port_does_not_name_is_reported_as_pending() -> None:
    fake = FakeDurableEngine(queued=[a_queued_workflow(str(RUN_A), "DELAYED", EARLIER)])

    assert a_launched_engine(fake).list_queue()[0].engine_state == "pending"


def test_an_attempts_record_is_the_step_that_opened_it() -> None:
    fake = FakeDurableEngine(
        steps=[StepRecord(step_id=STEP_ID, name="attempt_row", output=None, error=None)]
    )

    record = a_launched_engine(fake).attempt_record({"workflow_id": str(RUN_A), "step_id": STEP_ID})

    assert record is not None
    assert record.outcome == SUCCEEDED
    assert record.payload == {"name": "attempt_row", "step_id": STEP_ID, "error": None}


def test_a_step_that_failed_is_reported_as_failed() -> None:
    fake = FakeDurableEngine(
        steps=[StepRecord(step_id=STEP_ID, name="attempt_row", output=None, error="RuntimeError")]
    )

    record = a_launched_engine(fake).attempt_record({"workflow_id": str(RUN_A), "step_id": STEP_ID})

    assert record is not None
    assert record.outcome == FAILED


def test_an_engine_ref_the_adapter_did_not_write_reads_as_nothing() -> None:
    engine = a_launched_engine(FakeDurableEngine())

    assert engine.attempt_record({}) is None
    assert engine.attempt_record({"workflow_id": str(RUN_A)}) is None


def test_a_step_the_engine_never_recorded_reads_as_nothing() -> None:
    fake = FakeDurableEngine(
        steps=[StepRecord(step_id=1, name="next_row", output=None, error=None)]
    )

    engine = a_launched_engine(fake)

    assert engine.attempt_record({"workflow_id": str(RUN_A), "step_id": STEP_ID}) is None


def test_a_scheduled_job_is_registered_by_name_and_cron() -> None:
    fake = FakeDurableEngine()

    a_launched_engine(fake).schedule("clone_check", "0 3 * * *", lambda: None)

    assert [(name, cron) for name, cron, _ in fake.scheduled] == [("clone_check", "0 3 * * *")]


def test_the_walker_is_declared_once_the_engine_is_launched() -> None:
    """Declaring is registration, and the library is process-wide: it happens on launch."""
    fake = FakeDurableEngine()
    engine = an_engine(fake, deps_for(a_world()))

    assert fake.declared == []

    engine.launch()

    assert ("workflow", "run_walk") in fake.declared
