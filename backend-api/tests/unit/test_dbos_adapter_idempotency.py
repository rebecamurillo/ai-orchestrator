"""`DbosWorkflowEngine.enqueue` idempotency guard (story 5-1, AD-12).

When the durable engine already has steps recorded for a Run id, a second `enqueue` call
must be a no-op — it returns the workflow reference without calling the engine's enqueue
again. This is the guard against double-enqueueing after a lost HTTP response.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.infrastructure.dbos.adapter import DbosWorkflowEngine
from orchestrator.infrastructure.dbos.config import WORKFLOW_ID, EngineConfig
from orchestrator.infrastructure.dbos.facade import StepRecord
from tests.unit.application.writer_fixtures import a_world
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.test_dbos_adapter import deps_for

RUN_A = UUID("01960000-0000-7000-9000-00000000000a")
PARTITION_KEY = "01960000-0000-7000-9000-0000000000ff:feat/topic"


def an_engine(fake: FakeDurableEngine) -> DbosWorkflowEngine:
    config = EngineConfig(
        database_url="postgresql+psycopg://user:pw@postgres:5432/orchestrator",
        application_version="1",
        max_active_runs=2,
    )
    return DbosWorkflowEngine(config, fake, deps_for(a_world()))


def a_launched_engine(fake: FakeDurableEngine) -> DbosWorkflowEngine:
    engine = an_engine(fake)
    engine.launch()
    return engine


def test_enqueue_is_a_no_op_when_the_engine_has_steps_for_that_run() -> None:
    """If the engine already recorded steps for RUN_A, enqueue must not add to the queue."""
    existing_step = StepRecord(step_id=1, name="plan", output=None, error=None)
    fake = FakeDurableEngine(steps=[existing_step])
    engine = a_launched_engine(fake)

    reference = engine.enqueue(RUN_A, partition_key=PARTITION_KEY)

    # The engine's enqueue list must be empty — no second walk was started.
    assert fake.enqueued == []
    # The returned reference still carries the workflow id.
    assert reference == {WORKFLOW_ID: str(RUN_A)}


def test_enqueue_proceeds_when_the_engine_has_no_steps_for_that_run() -> None:
    """First call (no existing steps): enqueue starts the walk normally."""
    fake = FakeDurableEngine(steps=[])
    engine = a_launched_engine(fake)

    engine.enqueue(RUN_A, partition_key=PARTITION_KEY)

    assert len(fake.enqueued) == 1
    # The partition key must be forwarded verbatim to the durable engine (AD-12).
    assert fake.enqueued[0][2] == PARTITION_KEY
