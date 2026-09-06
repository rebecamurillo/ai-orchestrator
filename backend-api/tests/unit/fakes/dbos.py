"""In-memory `DurableEngine` — the one fake for the engine facade (AD-18). Reuse it.

The walker is a loop of decorated functions, so the only way to test it without a Postgres
is to be the thing that decorates them: this fake's `workflow` and `step` return the
function untouched and record that it was declared, which makes the walk an ordinary call
and its steps ordinary functions. Everything else is a list a test reads back — what was
enqueued, sent, cancelled, scheduled, and in which order the launch did its three things.

`recv` pops from `messages`, oldest first, and answers `None` once they run out, which is
exactly what the library does when the deadline passes. That is how the park-and-resume and
the thirty-day expiry are both driven from a list of dictionaries.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from orchestrator.infrastructure.dbos.facade import QueuedWorkflow, StepRecord

#: The step id the fake hands out, incremented per step call so two attempts differ.
FIRST_STEP_ID = 1


class FakeDurableEngine:
    """Records every call; runs nothing durably, because nothing here is durable."""

    def __init__(
        self,
        messages: list[Any] | None = None,
        queued: list[QueuedWorkflow] | None = None,
        steps: list[StepRecord] | None = None,
    ) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.declared: list[tuple[str, str]] = []
        self.enqueued: list[tuple[str, str, str]] = []
        self.sent: list[tuple[str, Any, str]] = []
        self.cancelled: list[str] = []
        self.scheduled: list[tuple[str, str, Callable[[], None]]] = []
        self.recvs: list[tuple[str, int]] = []
        self.configured: dict[str, Any] | None = None
        self.messages = list(messages or [])
        self._queued = list(queued or [])
        self._steps = list(steps or [])
        self._step_id = FIRST_STEP_ID

    def workflow(self, function: Any) -> Any:
        self.declared.append(("workflow", function.__name__))
        return function

    def step(self, function: Any) -> Any:
        self.declared.append(("step", function.__name__))
        return function

    def register_queue(self, name: str, *, concurrency: int) -> None:
        self.calls.append(("register_queue", (name, concurrency)))

    def enqueue(self, queue: str, workflow: Any, run_id: str, *, partition_key: str) -> None:
        self.calls.append(("enqueue", (queue, run_id, partition_key)))
        self.enqueued.append((queue, run_id, partition_key))

    def send(self, workflow_id: str, message: Any, topic: str) -> None:
        self.calls.append(("send", (workflow_id, topic)))
        self.sent.append((workflow_id, message, topic))

    def recv(self, topic: str, timeout_seconds: int) -> Any:
        self.recvs.append((topic, timeout_seconds))
        return self.messages.pop(0) if self.messages else None

    def cancel(self, workflow_id: str) -> None:
        self.calls.append(("cancel", workflow_id))
        self.cancelled.append(workflow_id)

    def queued(self, queue: str) -> list[QueuedWorkflow]:
        self.calls.append(("queued", queue))
        return list(self._queued)

    def steps(self, workflow_id: str) -> list[StepRecord]:
        self.calls.append(("steps", workflow_id))
        return list(self._steps)

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        self.calls.append(("schedule", (name, cron)))
        self.scheduled.append((name, cron, job))

    def step_id(self) -> int | None:
        current = self._step_id
        self._step_id += 1
        return current

    def configure(self, config: dict[str, Any]) -> None:
        self.calls.append(("configure", config))
        self.configured = config

    def start(self) -> None:
        self.calls.append(("start", None))


def a_queued_workflow(workflow_id: str, state: str, at: datetime) -> QueuedWorkflow:
    """One row of what the engine says its queue is holding."""
    return QueuedWorkflow(workflow_id=workflow_id, state=state, enqueued_at=at)
