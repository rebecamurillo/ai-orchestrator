"""The walk, as rules: what runs next, what a row's execution needs, and how a Run ends.

The durable engine owns *when* these run and *that they run once* (AD-6); this module owns
*what they mean*, so the walker in `infrastructure/dbos/walker.py` is a loop over five calls
and holds no rule of its own. Nothing here writes a status directly: `next_row` and
`close_run` reach AD-8's transitions through `writers.py`, exactly as the three status
writers do, and `run_row` writes nothing at all.

**`next_row` is the only thing that starts a plan.** Every row a Run is created with is
`planned` (AD-7): the planner expands the whole tree before the Run exists, and
`apply_step_result` queues a *successor*, so the first row of a plan has nothing behind it
to queue it. That is this function's first job, and it is deliberately narrow — the plan's
first `planned` row is queued only when no row of the Run is in any other unfinished status.
A Run parked on an `error` row has rows further down that are still `planned`, and queueing
one of those would run past the stop the Operator has not answered yet.

**`close_run` is what "nothing to run" means.** A Run whose rows are all `done` or
`skipped` is finished. A Run with no queued row *and* an unfinished one is stalled — the row
is `error` with an `on_fail` nothing routes, or `blocked` with no signal — and a stall is
reported as an `internal` park naming the row, not as a Run quietly reaching `done`. A Run
that is no longer `running` when the walk reaches this point is neither: `cancel` moved it
while a step was in flight, and both machine transitions here would raise. It is reported as
it stands, the way `apply_step_result` reports a late result.

**`attempt_row` is one durable step, on purpose.** The Attempt is opened and the executor
runs inside the same step, so a backend killed mid-execution re-executes both after the
restart: `start_attempt` finds the row `running` with an Attempt that never ended, closes it
and opens the next one (FR-12). Splitting them would make the start a *recorded* step, which
replay would hand back unchanged — the interrupted row would silently continue as Attempt 1,
and the count the Operator reads would say the kill never happened. The brief left the exact
recovery sequence to this story's spec checkpoint; this is it.

**A verify failure is resolved here for the same reason `frame_start_sha` is.** A row a
`verify` step sent back needs three facts about a *different* row — its command, its exit
code and the tail of its log (FR-10) — and AD-9 closes `StepContext`'s field list. This is
the only place holding both the row and the repositories, so it reads them once and hands
them over as a frozen `VerifyFailure` on `RunEnvironment`; the executor reads a value and
never a repository (AD-8).

**`run_row` reads; the executor does the work.** It opens one unit of work to assemble the
`StepContext` and closes it *before* the executor runs, because an executor holds a process
for minutes (FR-10) and a database session held across that is a connection nothing can use
and a transaction nothing can see past.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

import structlog

from orchestrator.application.rules.frames import rows_in_frame
from orchestrator.application.steps import StepContext, StepPorts, execute
from orchestrator.application.steps.context import VerifyFailure
from orchestrator.application.templates.plan_model import (
    ON_FAIL_KEY,
    REDISPATCH_TARGET_SEQ,
)
from orchestrator.application.templates.rows import COMMAND_KEY
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.start_attempt import start_attempt
from orchestrator.application.use_cases.writers import (
    FINISHED,
    WriterPorts,
    expire_run,
    finish_run,
    park_run,
    queue_row,
    require_row,
    require_run,
)
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.statuses import GateEvent, RunStatus
from orchestrator.domain.values import Park, StepResult

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WalkPorts:
    """What a walk reaches: the writers' four repositories, and the executors' own ports.

    One bundle rather than two arguments, for the reason `WriterPorts` is one: the walker
    passes the same pair to every call, and a signature that took them apart would let a
    caller pair a Run's writers with another Run's ports.
    """

    writers: WriterPorts
    step: StepPorts


#: The statuses a row may be in while the plan's first row is still waiting to be queued:
#: `planned` is every row of a Run that has not started, and the two finished ones are what
#: a re-walk after a park has left behind it.
STARTABLE: frozenset[str] = frozenset({"planned", "done", "skipped"})

#: The park a Run with no runnable row stops on, naming the row that stopped it.
STALLED = "no runnable step: {path} is {status}"

#: The line a `recv` expiry leaves when the Run is no longer parked (a signal won the race).
NOT_PARKED = "expiry ignored"

#: The status a Run has to be in for the `recv` expiry to mean anything (AD-13).
NEEDS_YOU = "needs_you"

#: The status a Run has to be in for either of `close_run`'s two endings to apply.
RUNNING = "running"

#: The line a close that arrives after the Run already moved leaves, and nothing else.
LATE_CLOSE = "close ignored"

#: How much of a failed `verify` row's log the Story file is handed back (FR-10). Enough to
#: show what failed, bounded so a prepare commit never carries a whole build log.
VERIFY_LOG_LINES = 200


def next_row(ports: WalkPorts, run_id: UUID) -> int | None:
    """The `seq` of the row to run now, queueing the plan's first row when nothing is."""
    writers = ports.writers
    with writers.uow:
        row = writers.steps.first_queued(run_id)
        if row is None:
            row = _start_the_plan(writers, run_id)
        writers.uow.commit()
    return row.seq if row is not None else None


def _start_the_plan(ports: WriterPorts, run_id: UUID) -> StepRun | None:
    """Queue the first `planned` row, but only on a Run that is not stopped on one."""
    rows = ports.steps.list_for_run(run_id)
    if any(row.status not in STARTABLE for row in rows):
        return None
    planned = next((row for row in rows if row.status == "planned"), None)
    return queue_row(ports, planned) if planned is not None else None


def attempt_row(
    ports: WalkPorts,
    run_id: UUID,
    seq: int,
    engine_ref: dict[str, Any],
    resume_event: GateEvent | None = None,
) -> StepResult:
    """Open the row's Attempt, then run it — the pair the durable step re-executes whole."""
    start_attempt(ports.writers, run_id, seq, engine_ref=engine_ref)
    return run_row(ports, run_id, seq, resume_event)


def run_row(
    ports: WalkPorts,
    run_id: UUID,
    seq: int,
    resume_event: GateEvent | None = None,
) -> StepResult:
    """Execute one row through its kind's executor and report what it returned.

    `step_span` wraps the width of `execute` only, opened after the unit of work that reads
    the context has already closed — the tracer is never called from inside a transaction.
    `WalkPorts.step.tracer` is `None` for every frozen ports construction predating this
    story (AD-11's own "no tracer wired" degrade), which is why the `Run` is read once,
    here, rather than through a second repository call inside the `if`.
    """
    with ports.writers.uow:
        run = require_run(ports.writers, run_id)
        context = _context(ports, run, seq, resume_event)
    tracer = context.ports.tracer
    if tracer is None:
        return execute(context)
    with tracer.step_span(run, context.row, context.attempt):
        return execute(context)


def _context(
    ports: WalkPorts,
    run: Run,
    seq: int,
    resume_event: GateEvent | None,
) -> StepContext:
    """AD-9's own field list, read out of the Run the walker is standing in."""
    writers = ports.writers
    run_id = run.id
    row = require_row(writers, run_id, seq)
    attempts = writers.attempts.list_for_row(row.id)
    if not attempts:
        raise NotFound(f"no attempt on step {seq} of run {run_id}")
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=run.worktree_path,
        frame_start_sha=_frame_start_sha(writers, run_id, row),
        previous_attempt=attempts[-2] if len(attempts) > 1 else None,
        attempt=attempts[-1],
        resume_signal=_resume_signal(writers, run_id, resume_event),
        ports=_step_ports(ports, run_id, row),
    )


def _step_ports(ports: WalkPorts, run_id: UUID, row: StepRun) -> StepPorts:
    """The executors' ports, plus whatever this row alone needs resolving (FR-10).

    The same object for every row that was not sent back, which is almost all of them: a
    `replace` only happens when there is something to put in it.
    """
    environment = ports.step.run_env
    failure = _verify_failure(ports, run_id, row)
    if environment is None or failure is None:
        return ports.step
    return replace(ports.step, run_env=replace(environment, verify_failure=failure))


def _verify_failure(ports: WalkPorts, run_id: UUID, row: StepRun) -> VerifyFailure | None:
    """Why the `verify` row redispatched to this one failed, or `None` when none did.

    The target is matched on `seq` rather than on a kind: `on_fail: {redispatch: …}` is the
    only thing that sends a Run backwards (AD-9), and the planner already resolved it to
    this row's number (`templates/plan_model.py`). A `verify` row that never recorded an
    attempt still names its command — the Operator can read that even with no code to show.
    """
    if row.redispatch_count == 0:
        return None
    writers = ports.writers
    sender = next(
        (entry for entry in writers.steps.list_for_run(run_id) if _redispatches_to(entry, row.seq)),
        None,
    )
    if sender is None:
        return None
    attempts = writers.attempts.list_for_row(sender.id)
    latest = attempts[-1] if attempts else None
    reader = ports.step.logs
    tail = reader.tail(latest.log_path, VERIFY_LOG_LINES) if reader and latest else []
    return VerifyFailure(
        command=str(sender.with_resolved.get(COMMAND_KEY) or ""),
        exit_code=latest.exit_code if latest is not None else None,
        log_tail=tuple(tail),
    )


def _redispatches_to(row: StepRun, seq: int) -> bool:
    """Whether this row's own `on_fail` is a redispatch aimed at `seq` (AD-9)."""
    action = row.with_resolved.get(ON_FAIL_KEY)
    return isinstance(action, Mapping) and action.get(REDISPATCH_TARGET_SEQ) == seq


def _frame_start_sha(ports: WriterPorts, run_id: UUID, row: StepRun) -> str | None:
    """The commit the row's Story frame started at: its first row's first attempt (AD-9)."""
    if row.frame is None:
        return None
    # the row itself is in its own frame and the caller has already required an Attempt on
    # it, so this walk always finds one; `None` is what a frame whose first attempt recorded
    # no commit reports, not a frame that has not run
    return next(
        (
            attempts[0].start_sha
            for entry in rows_in_frame(ports.steps.list_for_run(run_id), row.frame)
            if (attempts := ports.attempts.list_for_row(entry.id))
        ),
        None,
    )


def _resume_signal(
    ports: WriterPorts, run_id: UUID, resume_event: GateEvent | None
) -> GateRecord | None:
    """The record `signal_run` wrote for the signal that resumed this row (AD-9)."""
    if resume_event is None:
        return None
    records = ports.records.list_for_run(run_id)
    return next((line for line in reversed(records) if line.event == resume_event), None)


def apply_result(ports: WalkPorts, run_id: UUID, seq: int, result: StepResult) -> RunStatus:
    """Apply one result through AD-8's writer, and report where the Run now stands."""
    apply_step_result(ports.writers, run_id, seq, result)
    return require_run(ports.writers, run_id).status


def close_run(ports: WalkPorts, run_id: UUID) -> RunStatus:
    """End a Run that has nothing queued: `done` when every row finished, parked when not."""
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id)
        if run.status != RUNNING:
            log.info(LATE_CLOSE, run_id=str(run_id), status=run.status)
            return run.status
        stalled = next(
            (row for row in writers.steps.list_for_run(run_id) if row.status not in FINISHED),
            None,
        )
        if stalled is None:
            run = finish_run(writers, run)
        else:
            reason = STALLED.format(path=stalled.path, status=stalled.status)
            run = park_run(writers, run, Park(kind="internal", reason=reason, path=stalled.path))
        writers.uow.commit()
    return run.status


def expire(ports: WalkPorts, run_id: UUID) -> RunStatus:
    """The 30-day `recv` reached its deadline: the Run fails, unless a signal beat it."""
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id)
        if run.status != NEEDS_YOU:
            log.info(NOT_PARKED, run_id=str(run_id), status=run.status)
            return run.status
        run = expire_run(writers, run)
        writers.uow.commit()
    return run.status
