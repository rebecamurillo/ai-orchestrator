"""The walker: the durable loop that executes a Run's rows, one at a time, exactly once.

Every rule this loop needs is in `application/use_cases/walk.py`; what is here is the
durability. `build_walk` declares seven durable steps and the workflow that calls them, and
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
   and loops. A message carrying a `stop` other than the Run's current `park_seq` (read in the
   `current_stop` step) was written for an earlier stop: it is logged and discarded, and the
   walk waits again. A message with no stop is taken as it is. After a message that resumes
   (never `cancel`), the walk waits until `open_turns` finds no session turn still running.
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

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

import structlog

from orchestrator.application.steps import StepPorts
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.use_cases import walk
from orchestrator.application.use_cases.calculate_metrics import CalculationPorts
from orchestrator.application.use_cases.initiative_advance import AdvancePorts
from orchestrator.application.use_cases.walk import Held, WalkPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.statuses import GateEvent
from orchestrator.domain.values import StepResult
from orchestrator.infrastructure.dbos.config import HUMAN_TOPIC, STEP_ID, WORKFLOW_ID
from orchestrator.infrastructure.dbos.facade import DurableEngine

log = structlog.get_logger(__name__)

#: How a step reaches its own `WriterPorts`: one session, opened and closed per step.
OpenPorts = Callable[[], AbstractContextManager[WriterPorts]]

#: How a step reaches one Run's environment (4.8). Resolved here, before the executor runs,
#: so an executor is handed a value and never a repository (AD-8, AD-9).
ReadEnvironment = Callable[[UUID], RunEnvironment | None]

#: The status that means the walk goes on. Every other status a result can leave ends it.
RUNNING = "running"

#: The status that means the Run is waiting for the Operator (AD-13).
NEEDS_YOU = "needs_you"

#: The status the 30-day deadline leaves the Run in when nothing beat it.
FAILED = "failed"

#: The status an operator `cancel` signal leaves the Run in.
CANCELLED = "cancelled"

#: The key the Operator's signal travels under in a `recv` message.
SIGNAL_KIND = "kind"

#: The key a signal's stop travels under in a `recv` message, and what is logged when a
#: message naming an earlier stop is dropped.
STOP = "stop"
STALE_SIGNAL = "stale signal discarded"

#: The wake-up that never waits for a killed turn, and what is logged once when a wait starts.
CANCEL_KIND = "cancel"
WAITING_FOR_KILLED_TURN = "waiting for killed turn"

#: What the walker logs when a message arrives carrying no signal kind it can read.
UNREADABLE = "unreadable resume message"

#: What the walker logs when it starts and when it stops walking one Run.
WALK_STARTED = "walk started"
WALK_ENDED = "walk ended"

#: The status `deps.run_finished` reacts to (4.10) — `failed` and `cancelled` leave a
#: Repository's clone check exactly as informative as it already was.
DONE = "done"

#: `done`, `failed` and `cancelled` — the module docstring's own point 6. What `on_terminal`
#: (SPEC CAP-8) fires on; `run_finished`'s own gate above stays `DONE`-only, untouched.
TERMINAL = frozenset({DONE, FAILED, CANCELLED})

#: What the walker logs when the completion hook itself raises — a best-effort refresh of a
#: Repository's clone check, never a reason to jeopardise a status transition that is
#: already durable by the time this call is made.
RUN_FINISHED_HOOK_FAILED = "run finished hook failed"

#: What the walker logs when the readiness hook itself raises (SPEC CAP-8) — the same
#: best-effort tolerance `RUN_FINISHED_HOOK_FAILED` states, for the second hook.
ON_TERMINAL_HOOK_FAILED = "on terminal hook failed"

#: How long an `attempt_row` step waits before it asks again while the instance is held (AD-30).
HOLD_POLL_SECONDS = 5

#: What the walker logs once when a step starts waiting on a hold.
HELD_FOR_UPGRADE = "held for upgrade"


@dataclass(frozen=True)
class WalkerDeps:
    """What the walker's steps are built from, all of it decided in the composition root."""

    open_ports: OpenPorts
    step_ports: StepPorts
    human_wait_seconds: int
    #: `None` in a process that resolves no environment — every unit test whose executors
    #: need none. The git kinds refuse with a wiring error rather than guessing (4.8).
    read_environment: ReadEnvironment | None = None
    #: The completion hook (4.10): called with a Run's id whenever a step of this walk
    #: leaves it `done`. `None` in every process that wires no such effect — every unit test
    #: among them, and any process built before this hook existed.
    run_finished: Callable[[UUID], None] | None = None
    #: The readiness hook (SPEC CAP-8): called with a Run's id whenever a step of this walk
    #: leaves it in *any* terminal status. Independent of `run_finished`, whose `DONE`-only
    #: gate is a frozen test (`_finish`'s own docstring says which). `None` where none is wired.
    on_terminal: Callable[[UUID], None] | None = None
    #: How a step waits on a hold; a test replaces it.
    sleep: Callable[[float], None] = time.sleep
    #: The metrics calculation's scope (epic 2 story 5); `None` where no job is wired.
    calculation_writes: Callable[[], AbstractContextManager[CalculationPorts]] | None = None
    #: The initiative advance's scope; `None` where no workflow is wired.
    advance_writes: Callable[[], AbstractContextManager[AdvancePorts]] | None = None


def build_walk(engine: DurableEngine, deps: WalkerDeps) -> Callable[[str], None]:
    """Declare the walker's seven steps and its workflow on `engine`, and return the workflow.

    Each step is its own small factory so that this function stays a composition and the
    library's decorators are applied in exactly one place per step.
    """
    steps = _Steps(
        next_row=engine.step(_next_row(deps)),
        attempt_row=engine.step(_attempt_row(engine, deps)),
        apply_result=engine.step(_apply_result(deps)),
        close_run=engine.step(_close_run(deps)),
        expire=engine.step(_expire(deps)),
        open_turns=engine.step(_open_turns(deps)),
        current_stop=engine.step(_current_stop(deps)),
    )
    return engine.workflow(_walk(engine, deps, steps))


@dataclass(frozen=True)
class _Steps:
    """The seven durable steps a walk is made of, already declared on the engine."""

    next_row: Callable[[str], int | None]
    attempt_row: Callable[[str, int, str | None], dict[str, Any]]
    apply_result: Callable[[str, int, dict[str, Any]], str]
    close_run: Callable[[str], str]
    expire: Callable[[str], str]
    open_turns: Callable[[str], int]
    current_stop: Callable[[str], int]


def _walk(engine: DurableEngine, deps: WalkerDeps, steps: _Steps) -> Callable[[str], None]:
    """The workflow body: seven calls and four branches, each on a value a step returned."""

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
                message = _receive(engine, deps, steps, run_id)
                if message is not None:
                    resume = _kind(message, run_id)
                    if resume != CANCEL_KIND:
                        _settle(deps, steps, run_id)
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


def _walk_ports(deps: WalkerDeps, ports: WriterPorts, run_id: str | None = None) -> WalkPorts:
    """One step's writers, paired with the executors' ports the composition root built.

    `run_id` is passed only by the step that runs an executor. That is the one step whose
    ports must carry this Run's own environment, and resolving it here — rather than in
    `application/use_cases/walk.py` — is what keeps the executor reading a frozen value
    instead of a repository (AD-8).
    """
    step = deps.step_ports
    if run_id is not None and deps.read_environment is not None:
        step = replace(step, run_env=deps.read_environment(UUID(run_id)))
    return WalkPorts(writers=ports, step=step)


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
        waited = False
        while True:
            with deps.open_ports() as ports:
                result = walk.attempt_row(
                    _walk_ports(deps, ports, run_id), UUID(run_id), seq, reference, _event(resume)
                )
            if not isinstance(result, Held):
                return result.model_dump(mode="json")
            if not waited:
                log.info(HELD_FOR_UPGRADE, run_id=run_id, seq=seq)
                waited = True
            deps.sleep(HOLD_POLL_SECONDS)

    return attempt_row


def _apply_result(deps: WalkerDeps) -> Callable[[str, int, dict[str, Any]], str]:
    def apply_result(run_id: str, seq: int, result: dict[str, Any]) -> str:
        with deps.open_ports() as ports:
            applied = StepResult.model_validate(result)
            status = walk.apply_result(_walk_ports(deps, ports), UUID(run_id), seq, applied)
        _finish(deps, run_id, status)
        return status

    return apply_result


def _close_run(deps: WalkerDeps) -> Callable[[str], str]:
    def close_run(run_id: str) -> str:
        with deps.open_ports() as ports:
            status = walk.close_run(_walk_ports(deps, ports), UUID(run_id))
        _finish(deps, run_id, status)
        return status

    return close_run


def _finish(deps: WalkerDeps, run_id: str, status: str) -> None:
    """The two completion hooks (4.10, SPEC CAP-8), run from inside the step that just left
    the Run `done` or otherwise terminal.

    Not a declared step of its own: the walk's step sequence is pinned by
    `test_dbos_walker.py::test_the_walk_declares_five_steps_and_one_workflow`.

    Each call is best-effort — its own failure is logged and swallowed rather than raised,
    because by the time either runs the Run's own status is already durable, and retrying
    the step that reached it over a hook that only refreshes a read model would risk
    re-applying a transition that already happened.

    `run_finished`'s own `DONE`-only gate is exactly what it always was:
    `tests/unit/test_dbos_walker_on_finished.py::
    test_the_hook_is_not_called_when_the_run_does_not_reach_done` pins it, names no
    successor story, and this function still returns before calling it for anything else.
    `on_terminal` is a second, independent call on the wider `TERMINAL` set, not a second
    effect folded into that gate.
    """
    if status == DONE:
        _call(deps.run_finished, run_id, RUN_FINISHED_HOOK_FAILED)
    if status in TERMINAL:
        _call(deps.on_terminal, run_id, ON_TERMINAL_HOOK_FAILED)


def _call(hook: Callable[[UUID], None] | None, run_id: str, failure_key: str) -> None:
    """One completion hook, called if wired, its own failure logged and swallowed."""
    if hook is None:
        return
    try:
        hook(UUID(run_id))
    except Exception:
        log.exception(failure_key, run_id=run_id)


def _expire(deps: WalkerDeps) -> Callable[[str], str]:
    def expire(run_id: str) -> str:
        with deps.open_ports() as ports:
            return walk.expire(_walk_ports(deps, ports), UUID(run_id))

    return expire


def _open_turns(deps: WalkerDeps) -> Callable[[str], int]:
    def open_turns(run_id: str) -> int:
        with deps.open_ports() as ports:
            return walk.open_turns(_walk_ports(deps, ports), UUID(run_id))

    return open_turns


def _settle(deps: WalkerDeps, steps: _Steps, run_id: str) -> None:
    """Poll until no session turn of the Run is running; each answer is a recorded step."""
    count = steps.open_turns(run_id)
    if count:
        log.info(WAITING_FOR_KILLED_TURN, run_id=run_id, count=count)
    while count:
        deps.sleep(HOLD_POLL_SECONDS)
        count = steps.open_turns(run_id)


def _current_stop(deps: WalkerDeps) -> Callable[[str], int]:
    def current_stop(run_id: str) -> int:
        with deps.open_ports() as ports:
            return walk.current_stop(_walk_ports(deps, ports), UUID(run_id))

    return current_stop


def _stop(message: object) -> int | None:
    """The stop a message carries, or `None` when it names none the walker can read."""
    stop = message.get(STOP) if isinstance(message, dict) else None
    return stop if isinstance(stop, int) else None


def _receive(engine: DurableEngine, deps: WalkerDeps, steps: _Steps, run_id: str) -> object | None:
    """The next message for the Run's current stop, or `None` at the deadline.

    A message whose stop is not the Run's current one was written for an earlier stop and
    must not land on this one; each new wait gets the full deadline.
    """
    while True:
        message = engine.recv(HUMAN_TOPIC.format(run_id=run_id), deps.human_wait_seconds)
        stop = _stop(message)
        if message is None or stop is None:
            return message
        current = steps.current_stop(run_id)
        if stop == current:
            return message
        log.info(STALE_SIGNAL, run_id=run_id, stop=stop, current_stop=current)


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
