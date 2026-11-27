"""The DBOS adapter's three queues (epic 3 story 2, AC4, AC5, AC6 adapter half, AC7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.dbos.adapter import DbosWorkflowEngine
from orchestrator.infrastructure.dbos.config import (
    INTERACTIVE_QUEUE,
    QUEUE_NAME,
    SESSION_QUEUE,
    EngineConfig,
)
from orchestrator.infrastructure.dbos.facade import ENQUEUED, QueuedWorkflow, StepRecord
from tests.unit.application.writer_fixtures import a_world
from tests.unit.fakes.dbos import FakeDurableEngine, a_queued_workflow
from tests.unit.test_dbos_walker import deps_for

AT = datetime(2026, 11, 22, tzinfo=UTC)
CONFIG = EngineConfig(
    database_url="postgresql://x",
    application_version="1",
    max_active_runs=2,
    max_interactive_runs=4,
)
KEY = "repo:main"


def adapter(fake: FakeDurableEngine, *, launched: bool = True) -> DbosWorkflowEngine:
    engine = DbosWorkflowEngine(CONFIG, fake, deps_for(a_world()))
    if launched:
        engine.launch()
    return engine


def queues_registered(fake: FakeDurableEngine) -> list[object]:
    return [args for name, args in fake.calls if name == "register_queue"]


def held(n: int, offset: int = 0) -> list[QueuedWorkflow]:
    return [
        a_queued_workflow(str(new_id()), ENQUEUED, AT + timedelta(seconds=offset + i))
        for i in range(n)
    ]


def test_launch_registers_walk_interactive_and_session_queues_in_order() -> None:
    fake = FakeDurableEngine()

    adapter(fake)

    assert queues_registered(fake) == [(QUEUE_NAME, 2), (INTERACTIVE_QUEUE, 4), (SESSION_QUEUE, 6)]


def test_an_interactive_run_goes_on_the_interactive_queue_with_the_same_key() -> None:
    fake = FakeDurableEngine()
    run_id = new_id()

    adapter(fake).enqueue(run_id, KEY, "interactive")

    assert fake.enqueued == [(INTERACTIVE_QUEUE, str(run_id), KEY)]


def test_a_walk_run_goes_on_the_walk_queue() -> None:
    fake = FakeDurableEngine()
    run_id = new_id()

    adapter(fake).enqueue(run_id, KEY, "walk")

    assert fake.enqueued == [(QUEUE_NAME, str(run_id), KEY)]


def test_a_repeated_enqueue_of_a_started_workflow_enqueues_nothing() -> None:
    step = StepRecord(step_id=1, name="x", output=None, error=None)
    fake = FakeDurableEngine(steps=[step])

    adapter(fake).enqueue(new_id(), KEY, "interactive")

    assert fake.enqueued == []


def test_list_queue_counts_positions_per_lane_walk_first() -> None:
    walk, interactive = held(2), held(2, offset=10)
    fake = FakeDurableEngine(queued={QUEUE_NAME: walk, INTERACTIVE_QUEUE: interactive})

    entries = adapter(fake).list_queue()

    assert [(e.lane, e.position) for e in entries] == [
        ("walk", 1),
        ("walk", 2),
        ("interactive", 1),
        ("interactive", 2),
    ]


def test_an_interactive_entry_is_not_behind_a_parked_walk_run() -> None:
    walk_running = QueuedWorkflow(workflow_id=str(new_id()), state="PENDING", enqueued_at=AT)
    waiting = held(1, offset=5)
    fake = FakeDurableEngine(queued={QUEUE_NAME: [walk_running], INTERACTIVE_QUEUE: waiting})

    entries = adapter(fake).list_queue()

    interactive = [e for e in entries if e.lane == "interactive"]
    assert [e.position for e in interactive] == [1]
