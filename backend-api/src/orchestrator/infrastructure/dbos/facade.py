"""The only module that imports `dbos` (AD-6), behind the shape the rest of this package uses.

Everything the durable engine can do for this system is one method here, so the adapter and
the walker are written against one small protocol instead of against a library: they are
built with a `DurableEngine` and a unit test builds them with a fake one, which is the only
way a walker whose every step is a decorator can be tested without a Postgres.

The protocol is deliberately narrow and stated in this system's words — `enqueue` takes a
partition key because AD-12 says the Repository is the partition, `queued` returns what
`list_queue` needs and not a library row. What it does *not* abstract is durability: the
decorators are the library's, and `RealEngine` is the only implementation there will be.

`configure`, `register_queue` and `start` are three methods rather than one launch, because
the library is a process-wide singleton and the order is its own: the instance exists first,
the walker's decorators register against it, `start` opens the system database and recovers,
and the queue is declared last because declaring it *writes* its concurrency to that
database. Splitting them is also what lets the adapter be *built* without
touching the library at all — which is what a unit test that builds the composition root
depends on. Every step is declared `retries_allowed=False` (AD-6): the engine never
re-executes a side effect on its own, and the only automatic re-execution in this system is
the one a Template declares.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, TypeVar, runtime_checkable

from dbos import DBOS, DBOSConfig, SetEnqueueOptions, SetWorkflowID

#: A durable function keeps the signature it was declared with.
F = TypeVar("F", bound=Callable[..., Any])

#: The library's word for a workflow that has been dequeued and is running (or waiting).
PENDING = "PENDING"

#: The library's word for a workflow that is waiting for a slot on its queue.
ENQUEUED = "ENQUEUED"


@dataclass(frozen=True)
class QueuedWorkflow:
    """One workflow the queue is holding: what `list_queue` (SPEC CAP-11) reports."""

    workflow_id: str
    state: str
    enqueued_at: datetime


@dataclass(frozen=True)
class StepRecord:
    """One recorded step of a workflow — what `attempt_record` answers with (AD-6)."""

    step_id: int
    name: str
    output: Any
    error: str | None


@runtime_checkable
class DurableEngine(Protocol):
    """The durable engine, as this package uses it."""

    def workflow(self, function: F) -> F:
        """Declare a durable workflow: its step results are replayed after a restart."""
        ...

    def step(self, function: F) -> F:
        """Declare a durable step, with the engine's own retries off (AD-6)."""
        ...

    def register_queue(self, name: str, *, concurrency: int) -> None:
        """One queue, `concurrency` workflows at a time, one per partition (AD-12).

        Called after `start`: this writes the queue's configuration to the system database.
        """
        ...

    def enqueue(self, queue: str, workflow: F, run_id: str, *, partition_key: str) -> None:
        """Start `workflow(run_id)` on that queue, under `run_id`, behind its partition."""
        ...

    def send(self, workflow_id: str, message: Any, topic: str) -> None:
        """Deliver one message to a workflow's `recv` (AD-13)."""
        ...

    def recv(self, topic: str, timeout_seconds: int) -> Any:
        """Wait for one message, or `None` when the deadline passes."""
        ...

    def cancel(self, workflow_id: str) -> None:
        """Stop a workflow: its next step raises and the workflow ends."""
        ...

    def queued(self, queue: str) -> list[QueuedWorkflow]:
        """Every workflow this queue is holding, oldest first."""
        ...

    def steps(self, workflow_id: str) -> list[StepRecord]:
        """Every step this workflow has recorded, in the order they ran."""
        ...

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        """Register a recurring job (SPEC CAP-11 registers the two of them)."""
        ...

    def step_id(self) -> int | None:
        """The id of the step now running, or `None` outside one."""
        ...

    def configure(self, config: dict[str, Any]) -> None:
        """Create the engine instance the declarations below register against."""
        ...

    def start(self) -> None:
        """Start dequeueing, and recover the workflows an earlier process was running."""
        ...


class RealEngine:
    """`DurableEngine` over the library. The only place `dbos` is named."""

    def workflow(self, function: F) -> F:
        return DBOS.workflow()(function)

    def step(self, function: F) -> F:
        return DBOS.step(retries_allowed=False)(function)

    def register_queue(self, name: str, *, concurrency: int) -> None:
        DBOS.register_queue(name, global_concurrency=concurrency, partition_concurrency=1)

    def enqueue(self, queue: str, workflow: F, run_id: str, *, partition_key: str) -> None:
        # the workflow id *is* the Run id, so an enqueue that is retried after a lost
        # response finds the workflow it already started instead of starting a second one
        with SetWorkflowID(run_id), SetEnqueueOptions(queue_partition_key=partition_key):
            DBOS.enqueue_workflow(queue, workflow, run_id)

    def send(self, workflow_id: str, message: Any, topic: str) -> None:
        DBOS.send(workflow_id, message, topic)

    def recv(self, topic: str, timeout_seconds: int) -> Any:
        return DBOS.recv(topic, timeout_seconds)

    def cancel(self, workflow_id: str) -> None:
        DBOS.cancel_workflow(workflow_id)

    def queued(self, queue: str) -> list[QueuedWorkflow]:
        held = DBOS.list_workflows(queue_name=queue, status=[ENQUEUED, PENDING], load_input=False)
        return [
            QueuedWorkflow(
                workflow_id=status.workflow_id,
                state=status.status,
                enqueued_at=_at(status.created_at),
            )
            for status in held
        ]

    def steps(self, workflow_id: str) -> list[StepRecord]:
        return [
            StepRecord(
                step_id=step.function_id,
                name=step.function_name,
                output=step.output,
                error=type(step.error).__name__ if step.error is not None else None,
            )
            for step in DBOS.list_workflow_steps(workflow_id)
        ]

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        def scheduled(scheduled_at: datetime, actual_at: datetime) -> None:
            job()

        DBOS.create_schedule(
            schedule_name=name,
            workflow_fn=DBOS.workflow(name=name)(scheduled),
            schedule=cron,
        )

    def step_id(self) -> int | None:
        return DBOS.step_id

    def configure(self, config: dict[str, Any]) -> None:
        DBOS(config=DBOSConfig(**config))  # type: ignore[typeddict-item]

    def start(self) -> None:
        DBOS.launch()


def _at(created_at: int | None) -> datetime:
    """The library's epoch milliseconds as the UTC instant every timestamp here is."""
    return datetime.fromtimestamp((created_at or 0) / 1000, tz=UTC)
