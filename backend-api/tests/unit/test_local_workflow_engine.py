"""`LocalWorkflowEngine` (`infrastructure/engine/local.py`): the placeholder `WorkflowEngine`
`main.py` wires until 4.6 lands the durable, DBOS-backed one.

Every method of the port is exercised so `isinstance(engine, WorkflowEngine)` keeps holding
and so a future reader can see, in one place, exactly how little this class promises: an
`engine_ref` that is a counter, a queue that lives only in this process, and two no-ops.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.values import Signal
from orchestrator.infrastructure.engine import LocalWorkflowEngine

RUN_A = UUID("01960000-0000-7000-9000-00000000000a")
RUN_B = UUID("01960000-0000-7000-9000-00000000000b")
REPOSITORY = UUID("01960000-0000-7000-9000-0000000000ff")


def test_satisfies_the_protocol() -> None:
    assert isinstance(LocalWorkflowEngine(), WorkflowEngine)


def test_enqueue_returns_a_distinct_opaque_ref_each_time() -> None:
    engine = LocalWorkflowEngine()

    first = engine.enqueue(RUN_A, REPOSITORY)
    second = engine.enqueue(RUN_B, REPOSITORY)

    assert first != second
    assert isinstance(first, dict)


def test_list_queue_reports_every_enqueued_run_oldest_first() -> None:
    engine = LocalWorkflowEngine()
    engine.enqueue(RUN_A, REPOSITORY)
    engine.enqueue(RUN_B, REPOSITORY)

    entries = engine.list_queue()

    assert [entry.run_id for entry in entries] == [RUN_A, RUN_B]
    assert all(entry.engine_state == "enqueued" for entry in entries)


def test_cancel_removes_the_run_from_the_queue() -> None:
    engine = LocalWorkflowEngine()
    engine.enqueue(RUN_A, REPOSITORY)

    engine.cancel(RUN_A)

    assert engine.list_queue() == []


def test_cancel_an_unknown_run_does_not_raise() -> None:
    LocalWorkflowEngine().cancel(RUN_A)


def test_attempt_record_answers_none() -> None:
    engine = LocalWorkflowEngine()
    ref = engine.enqueue(RUN_A, REPOSITORY)

    assert engine.attempt_record(ref) is None


def test_signal_and_schedule_are_no_ops() -> None:
    engine = LocalWorkflowEngine()

    engine.signal(RUN_A, Signal(kind="cancel"))
    engine.schedule("clone_check", "0 0 * * *", lambda: None)
