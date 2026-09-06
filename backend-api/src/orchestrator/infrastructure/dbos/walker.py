"""The walker: the durable loop that executes a Run's rows, one at a time, exactly once.

Every rule this loop needs is in `application/use_cases/walk.py`; what is here is the
durability. `build_walk` declares five durable steps and the workflow that calls them, and
the workflow's body is deliberately tiny: each branch tests a value a step returned, so a
replay after a restart takes the same branch it took before it. Nothing here reads a clock,
a database or an environment outside a step (AD-6).

The loop, once:

1. `next_row` — the `seq` to run, or `None` when there is nothing queued.
2. With a row: `attempt_row` — the Attempt and the executor, together, so an interrupted
   execution is re-attempted rather than silently continued (`walk.py` says why) — then
   `apply_result`, AD-8's writer, answering with the Run's new status.
3. Without one: `close_run`, which finishes the Run or parks it on the row that stalled it.
   Its answer is a status like any other, and that is the point: a Run `close_run` parked is
   `needs_you`, so it goes to the same wait an executor's park goes to. A walk that returned
   there instead would leave a Run stopped for an Operator whose signal has nothing left to
   deliver to.
4. On `needs_you`, the Run's single `recv` on `human:{run_id}` (AD-13). The slot and the
   Repository partition are held for the whole wait, which is what AD-12 asks for. A message
   is the Operator's signal — already applied and committed by `signal_run` before the engine
   was told — so the walker only carries its kind forward as the next row's `resume_signal`
   and loops.
5. A `recv` that returns `None` is the deadline, and `expire` decides what that means: the
   Run fails `parked 30 days`, unless a signal won the race, in which case it answers with
   the status that signal left and the walk carries on rather than abandoning a Run that is
   running again.
6. Any status but `running` and `needs_you` ends the walk: `done`, `failed` and `cancelled`
   are terminal.

`cancel` is the engine's own: `DBOS.cancel_workflow` makes the next step raise. A walk
waiting in `recv` has no next step, so the adapter sends on the same topic to end the wait —
see `adapter.py`. A result already in flight is absorbed by `apply_step_result`'s late-result
rule.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

from orchestrator.application.steps import StepPorts
from orchestrator.application.use_cases import walk
from orchestrator.application.use_cases.walk import WalkPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.statuses import GateEvent
from orchestrator.domain.values import StepResult
from orchestrator.infrastructure.dbos.config import HUMAN_TOPIC, STEP_ID, WORKFLOW_ID
from orchestrator.infrastructure.dbos.facade import DurableEngine

log = structlog.get_logger(__name__)

#: How a step reaches its own `WriterPorts`: one session, opened and closed per step.
OpenPorts = Callable[[], AbstractContextManager[WriterPorts]]

#: The status that means the walk goes on. Every other status a result can leave ends it.
RUNNING = "running"

#: The status that means the Run is waiting for the Operator (AD-13).
NEEDS_YOU = "needs_you"

#: The status the 30-day deadline leaves the Run in when nothing beat it.
FAILED = "failed"

#: The key the Operator's signal travels under in a `recv` message.
SIGNAL_KIND = "kind"

#: What the walker logs when a message arrives carrying no signal kind it can read.
UNREADABLE = "unreadable resume message"

#: What the walker logs when it starts and when it stops walking one Run.
WALK_STARTED = "walk started"
WALK_ENDED = "walk ended"


@dataclass(frozen=True)
class WalkerDeps:
    """What the walker's steps are built from, all of it decided in the composition root."""

    open_ports: OpenPorts
    step_ports: StepPorts
    human_wait_seconds: int


def build_walk(engine: DurableEngine, deps: WalkerDeps) -> Callable[[str], None]:
    """Declare the walker's five steps and its workflow on `engine`, and return the workflow.

    Each step is its own small factory so that this function stays a composition and the
    library's decorators are applied in exactly one place per step.
    """
    steps = _Steps(
        next_row=engine.step(_next_row(deps)),
        attempt_row=engine.step(_attempt_row(engine, deps)),
        apply_result=engine.step(_apply_result(deps)),
        close_run=engine.step(_close_run(deps)),
        expire=engine.step(_expire(deps)),
    )
    return engine.workflow(_walk(engine, deps, steps))


@dataclass(frozen=True)
class _Steps:
    """The five durable steps a walk is made of, already declared on the engine."""

    next_row: Callable[[str], int | None]
    attempt_row: Callable[[str, int, str | None], dict[str, Any]]
    apply_result: Callable[[str, int, dict[str, Any]], str]
    close_run: Callable[[str], str]
    expire: Callable[[str], str]


def _walk(engine: DurableEngine, deps: WalkerDeps, steps: _Steps) -> Callable[[str], None]:
    """The workflow body: five calls and four branches, each on a value a step returned."""

    def run_walk(run_id: str) -> None:
        log.info(WALK_STARTED, run_id=run_id)
        resume: str | None = None
        while True:
            seq = steps.next_row(run_id)
            if seq is None:
                status = steps.close_run(run_id)
            else:
                status = steps.apply_result(run_id, seq, steps.attempt_row(run_id, seq, resume))
            resume = None
            if status == NEEDS_YOU:
                message = engine.recv(HUMAN_TOPIC.format(run_id=run_id), deps.human_wait_seconds)
                if message is not None:
                    resume = _kind(message, run_id)
                    continue
                status = steps.expire(run_id)
                if status == RUNNING:
                    # a signal arrived as the deadline passed: `expire` wrote nothing and the
                    # Run is running again, so the walk goes on rather than abandoning it
                    continue
            if status != RUNNING:
                log.info(WALK_ENDED, run_id=run_id, status=status)
                return

    return run_walk


def _walk_ports(deps: WalkerDeps, ports: WriterPorts) -> WalkPorts:
    """One step's writers, paired with the executors' ports the composition root built."""
    return WalkPorts(writers=ports, step=deps.step_ports)


def _next_row(deps: WalkerDeps) -> Callable[[str], int | None]:
    def next_row(run_id: str) -> int | None:
        with deps.open_ports() as ports:
            return walk.next_row(_walk_ports(deps, ports), UUID(run_id))

    return next_row


def _attempt_row(
    engine: DurableEngine, deps: WalkerDeps
) -> Callable[[str, int, str | None], dict[str, Any]]:
    def attempt_row(run_id: str, seq: int, resume: str | None) -> dict[str, Any]:
        reference = {WORKFLOW_ID: run_id, STEP_ID: engine.step_id()}
        with deps.open_ports() as ports:
            result = walk.attempt_row(
                _walk_ports(deps, ports), UUID(run_id), seq, reference, _event(resume)
            )
        return result.model_dump(mode="json")

    return attempt_row


def _apply_result(deps: WalkerDeps) -> Callable[[str, int, dict[str, Any]], str]:
    def apply_result(run_id: str, seq: int, result: dict[str, Any]) -> str:
        with deps.open_ports() as ports:
            applied = StepResult.model_validate(result)
            return walk.apply_result(_walk_ports(deps, ports), UUID(run_id), seq, applied)

    return apply_result


def _close_run(deps: WalkerDeps) -> Callable[[str], str]:
    def close_run(run_id: str) -> str:
        with deps.open_ports() as ports:
            return walk.close_run(_walk_ports(deps, ports), UUID(run_id))

    return close_run


def _expire(deps: WalkerDeps) -> Callable[[str], str]:
    def expire(run_id: str) -> str:
        with deps.open_ports() as ports:
            return walk.expire(_walk_ports(deps, ports), UUID(run_id))

    return expire


def _kind(message: object, run_id: str) -> str | None:
    """The signal kind a message carries, or `None` when it carries nothing the walker reads.

    The message is the engine's, not a caller's, and the only sender is `signal.model_dump()`
    in the adapter — but a message the walker cannot read must not raise inside the workflow
    body, where there is no step to record it and nothing to park the Run with. An
    unreadable one resumes the row with no `resume_signal`, which is what a row whose signal
    had no worktree effect gets anyway.
    """
    kind = message.get(SIGNAL_KIND) if isinstance(message, dict) else None
    if kind is None:
        log.info(UNREADABLE, run_id=run_id)
        return None
    return str(kind)


def _event(resume: str | None) -> GateEvent | None:
    """The signal kind a `recv` message carried, as the gate-record event it was written as.

    Not validated against `SIGNAL_KINDS`: the only reader is `walk._resume_signal`, which
    looks the kind up among the Run's own gate records and answers `None` when it finds
    none. A kind this system never wrote matches no record, which is the same answer.
    """
    if resume is None:
        return None
    event: GateEvent = resume  # type: ignore[assignment]
    return event
