"""`WorkflowEngine` on the durable engine (AD-6): the port's six methods, and a launch.

This is the only implementation of the port there will be, and it is thin on purpose —
every method is one call to the facade plus the translation between this system's words and
the engine's. What it owns is the two decisions AD-6 and AD-12 name:

- **The workflow id is the Run id.** `run.engine_ref` is `{workflow_id}`, and because the id
  is the Run's own, an `enqueue` repeated after a lost response finds the workflow it already
  started instead of starting a second walk. `attempt.engine_ref` adds the `step_id` of the
  durable step that opened the Attempt, which is what `attempt_record` reads back.
- **One queue, `MAX_ACTIVE_RUNS` wide, one Run per Repository.** The partition key is the
  Repository id, so two Runs against one Repository serialise without a lock table, and the
  slot and the partition are held for the whole life of the walk — including the `recv` a
  parked Run waits in (AD-12; PRD FR-13 states the trade-off).

`launch` is not on the port. Starting the engine is the composition root's business and
happens once, in the application's start-up step, after the migrations and the seeds
(Operations); everything else here is reached through `WorkflowEngine`. Building this class
touches the library not at all — the walker's declarations and the queue register inside
`launch`, because the library is a process-wide singleton and every unit test that builds the
composition root would otherwise register the walker a second time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import structlog

from orchestrator.domain.ports.engine import EngineRecord, QueueEntry, QueueState
from orchestrator.domain.values import Signal
from orchestrator.infrastructure.dbos.config import (
    HUMAN_TOPIC,
    QUEUE_NAME,
    STEP_ID,
    WORKFLOW_ID,
    EngineConfig,
    dbos_config,
)
from orchestrator.infrastructure.dbos.facade import (
    ENQUEUED,
    PENDING,
    DurableEngine,
    QueuedWorkflow,
)
from orchestrator.infrastructure.dbos.walker import WalkerDeps, build_walk

log = structlog.get_logger(__name__)

#: What the adapter logs when the engine is started and recovery begins.
ENGINE_LAUNCHED = "durable engine launched"

#: The engine's two words for a workflow the queue holds, as the port's own two.
STATES: dict[str, QueueState] = {ENQUEUED: "enqueued", PENDING: "pending"}

#: What `attempt_record` reports when the engine's own record carries no error.
SUCCEEDED = "succeeded"

#: What it reports when it does.
FAILED = "failed"

#: What an enqueue before `launch` refuses with — a composition-root bug, not an outcome.
NOT_LAUNCHED = "the durable engine has not been launched"

#: The signal kind `cancel` sends to end a parked Run's wait. The walk reads it as a kind
#: like any other and takes its next step, which is the one the cancellation raises in.
CANCEL = "cancel"


class DbosWorkflowEngine:
    """The durable `WorkflowEngine`. Constructing it registers the walker and the queue."""

    def __init__(self, config: EngineConfig, engine: DurableEngine, deps: WalkerDeps) -> None:
        self._config = config
        self._engine = engine
        self._deps = deps
        self._walk: Callable[[str], None] | None = None

    def launch(self) -> None:
        """Start the engine: from here it dequeues Runs and recovers interrupted ones."""
        self._engine.configure(dbos_config(self._config))
        self._walk = build_walk(self._engine, self._deps)
        self._engine.start()
        # after `start`, and that is the library's order rather than a preference: declaring
        # the queue writes its concurrency to the system database, which does not exist until
        # the engine is started. The queue manager picks a queue up on its next poll.
        self._engine.register_queue(QUEUE_NAME, concurrency=self._config.max_active_runs)
        log.info(ENGINE_LAUNCHED, version=self._config.application_version)

    def enqueue(self, run_id: UUID, partition_key: UUID) -> dict[str, Any]:
        """Put a Run behind its Repository's partition (AD-12); return its `engine_ref`."""
        self._engine.enqueue(
            QUEUE_NAME, self._walker(), str(run_id), partition_key=str(partition_key)
        )
        return {WORKFLOW_ID: str(run_id)}

    def _walker(self) -> Callable[[str], None]:
        """The declared walk. A Run cannot be enqueued into an engine nothing started."""
        if self._walk is None:
            raise RuntimeError(NOT_LAUNCHED)
        return self._walk

    def signal(self, run_id: UUID, signal: Signal) -> None:
        """Deliver one Operator signal (AD-13) to the Run's single `recv` wait."""
        self._engine.send(
            str(run_id), signal.model_dump(mode="json"), HUMAN_TOPIC.format(run_id=run_id)
        )

    def cancel(self, run_id: UUID) -> None:
        """Stop the Run's walk: the next step raises, and a wait is ended so there is one.

        Cancelling alone is not enough for a parked Run. The walk is then inside its single
        `recv`, which waits for a message or for `HUMAN_WAIT_SECONDS` — thirty days by
        default — and has no next step to raise in, so the workflow would go on holding its
        slot and its Repository partition (AD-12) long after the Operator cancelled it. The
        message ends the wait; the step the walk takes next is the one that raises.
        """
        self._engine.cancel(str(run_id))
        self._engine.send(str(run_id), {"kind": CANCEL}, HUMAN_TOPIC.format(run_id=run_id))

    def list_queue(self) -> list[QueueEntry]:
        """Every Run this engine is holding, queued or pending, oldest first."""
        held = sorted(self._engine.queued(QUEUE_NAME), key=lambda entry: entry.enqueued_at)
        waiting = 0
        entries: list[QueueEntry] = []
        for workflow in held:
            position = None
            if workflow.state == ENQUEUED:
                waiting += 1
                position = waiting
            entries.append(_entry(workflow, position))
        return entries

    def attempt_record(self, engine_ref: dict[str, Any]) -> EngineRecord | None:
        """What the engine knows about one Attempt's step, or `None` if it knows nothing."""
        workflow_id, step_id = engine_ref.get(WORKFLOW_ID), engine_ref.get(STEP_ID)
        if workflow_id is None or step_id is None:
            return None
        for step in self._engine.steps(str(workflow_id)):
            if step.step_id == step_id:
                outcome = FAILED if step.error is not None else SUCCEEDED
                return EngineRecord(
                    outcome=outcome,
                    payload={"name": step.name, STEP_ID: step.step_id, "error": step.error},
                )
        return None

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        """Register a recurring job (SPEC CAP-11: `clone_check` daily, `worktree_gc` at 7d)."""
        self._engine.schedule(name, cron, job)


def _entry(workflow: QueuedWorkflow, position: int | None) -> QueueEntry:
    """One held workflow as the port's own row. An unknown state is reported as pending."""
    return QueueEntry(
        run_id=UUID(workflow.workflow_id),
        engine_state=STATES.get(workflow.state, "pending"),
        position=position,
        enqueued_at=workflow.enqueued_at,
    )
