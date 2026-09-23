"""The walk, as rules: what runs next, what a row's execution needs, and how a Run ends.

The durable engine owns *when* these run and *that they run once* (AD-6); this module owns
*what they mean*, so the walker in `infrastructure/dbos/walker.py` is a loop over five calls
and holds no rule of its own. Nothing here writes a status directly: `next_row` and
`close_run` reach AD-8's transitions through `writers.py`, exactly as the three status
writers do, and `run_row` writes nothing at all.

**`next_row` is the only thing that starts a plan**, and deliberately narrow: every row a
Run is created with is `planned` (AD-7), and `apply_step_result` queues a *successor*, so
the plan's first row is queued only when no row of the Run is in any other unfinished
status — a Run parked on `error` has `planned` rows further down a queue here would skip.

**It also answers with a row an Operator's signal resumed in place.** Most resumed rows go
back on the queue, but AD-13 gives `continue` on a `plan_stale` or `protected_path` park the
transition `error → running → routed status`: the row is written `running` by `signal_run`
and is expected to run once more (`steps/plan_check.py` has the branch that answers `done`
on a `continue` resume signal). Nothing put it on the queue, and nothing can — AD-8's Step
diagram has no route from `running` to `queued` — so this is where such a row is found.
Without it the walk fell straight through to `close_run`, which read the same row as a stall
and parked `internal`, a park that admits no signal but `cancel`.

**And with the `verify` row a redispatch sent it back from** (6.8) — the same stall one row
later, and FR-10's own second turn, which had never happened. `_sent_back` says why.

**`close_run` is what "nothing to run" means.** All `done`/`skipped` rows finishes the Run;
no queued row plus an unfinished one is a stall, reported as an `internal` park naming the
row rather than a Run quietly reaching `done`. A Run no longer `running` here is neither —
`cancel` moved it mid-step — and is reported as it stands, the way a late result is.

**`attempt_row` is one durable step, on purpose**: the Attempt opens and the executor runs
inside it, so a backend killed mid-execution re-executes both after restart —
`start_attempt` closes the row's never-ended Attempt and opens the next one (FR-12), where a
split start would replay unchanged and leave the interrupted attempt silently uncounted.

**A verify failure and a frame's anchors are resolved here for the same reason
`frame_start_sha` is**: a row a `verify` step sent back needs facts about a *different* row
(FR-10), AD-17's rule needs every row of the Story frame, and AD-9 closes `StepContext`'s
field list. Read once, here — the only place holding both the rows and the repositories —
and handed over as frozen values on `RunEnvironment`/`StepPorts` (AD-8). The frame half of
that reading lives in `walk_frame.py`, which this module is at the 400-line cap without;
the seam is exactly the sentence above, and nothing else moved with it.

**`run_row` reads; the executor does the work**, in a unit of work closed *before* the
executor runs — a process held for minutes (FR-10) cannot hold a session too.

**`apply_result` always binds `apply_step_result`'s own `after_route`** to 5.7's
`budget_second_record`, unconditionally (that module's own docstring names the seam).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

import structlog

from orchestrator.application.steps import StepContext, StepPorts, execute
from orchestrator.application.steps.context import VerifyFailure
from orchestrator.application.templates.plan_model import (
    ON_FAIL_KEY,
    REDISPATCH_TARGET_SEQ,
)
from orchestrator.application.templates.rows import COMMAND_KEY
from orchestrator.application.use_cases.apply_step_result import (
    AfterRoute,
    apply_step_result,
    budget_second_record,
)
from orchestrator.application.use_cases.start_attempt import start_attempt
from orchestrator.application.use_cases.walk_frame import (
    WalkFrame,
    frame_anchors,
    frame_start_sha,
    read_frame,
)
from orchestrator.application.use_cases.writers import (
    FINISHED,
    WriterPorts,
    enqueue_dependents,
    expire_run,
    finish_run,
    park_dependents,
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

#: The status a row a redispatch sent the walk back from is left in — see `_sent_back`.
ERROR = "error"

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
            row = _resumed_in_place(writers, run_id)
        if row is None:
            row = _sent_back(writers, run_id)
        if row is None:
            row = _start_the_plan(writers, run_id)
        writers.uow.commit()
    return row.seq if row is not None else None


def _resumed_in_place(ports: WriterPorts, run_id: UUID) -> StepRun | None:
    """The row an Operator's signal left `running`, or `None` when there is none.

    Asked only after `first_queued` came back empty, so the queue is still what decides the
    order. Between two turns of the walk no row of a Run is `running` for any other reason:
    the row the previous turn executed was written out of `running` by `apply_step_result`
    before the loop came back here, and a row left `running` by a killed backend is the one
    the replayed durable step re-executes rather than one this call is asked about.
    """
    rows = ports.steps.list_for_run(run_id)
    return next((row for row in rows if row.status == RUNNING), None)


def _sent_back(ports: WriterPorts, run_id: UUID) -> StepRun | None:
    """The row a redispatch sent the walk back from, once its target has finished (FR-10).

    `on_fail: {redispatch, max}` is the second half of FR-10: a failed `verify` sends the
    Run back to the Story's `build` row, the agent gets its file back at `in-progress` with
    `## Verify Failure`, and the gate then runs **again** — AD-9's "exhaustion parks the
    Run" is only reachable if it does.

    Nothing put it back on the queue. `apply_step_result::_redispatch` writes the *target*
    `queued` and deliberately leaves every row between it and the sender as it stands
    (AD-9); the sender itself is the row the caller has just written `error`. When the
    re-dispatched target finishes, `_advance` looks at its successor — the sender — sees a
    row that is neither `planned` nor `skipped`, and correctly declines to touch it. So the
    walk fell through to `close_run`, which reads an unfinished row as a stall and parks
    `internal`: a stop that admits no signal but `cancel`. Every Run whose quality gate
    failed once was unrecoverable, and the `verify failed {n}/{n}` park AD-9 specifies could
    never be reached at all.

    This is `_resumed_in_place`'s twin, one row later in the same walk and for the same
    reason. `queue_row` reaches AD-8's own `("error", "retry") -> "queued"` pair, so no new
    transition is invented; the bound stays `redispatch_count` on the target, which
    `_redispatch` has already counted, and this call adds nothing to it.

    **Only while the Run is `running`, and that guard is the whole of the bound here.** An
    exhausted redispatch leaves exactly the same rows behind — the target `done`, the gate
    `error` — and differs only in that `_redispatch` parked the Run on it. `_start_the_plan`
    keeps a parked Run still by reading the rows (`STARTABLE`), which cannot tell these two
    states apart, so this one reads the Run itself: without it, `verify failed 2/2` would
    resume of its own accord and the Operator's stop would never hold.
    """
    if require_run(ports, run_id).status != RUNNING:
        return None
    rows = ports.steps.list_for_run(run_id)
    done = [row.seq for row in rows if row.status in FINISHED]
    for row in rows:
        if row.status == ERROR and any(_redispatches_to(row, seq) for seq in done):
            return queue_row(ports, row)
    return None


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
    frame = read_frame(writers, run_id, row)
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=run.worktree_path,
        frame_start_sha=frame_start_sha(frame.attempts),
        previous_attempt=attempts[-2] if len(attempts) > 1 else None,
        attempt=attempts[-1],
        resume_signal=_resume_signal(writers, run_id, resume_event),
        ports=_step_ports(ports, run, row, frame),
    )


def _step_ports(ports: WalkPorts, run: Run, row: StepRun, frame: WalkFrame) -> StepPorts:
    """The executors' ports, plus whatever this row alone needs resolving (FR-10, AD-17).

    A walker that resolved no environment is handed over unchanged: there is nowhere to put a
    frame's facts, and the executor refuses with the wiring error `require_env` names.

    **Only a row inside a Story frame is given the rule.** AD-17 is frame-scoped: its frozen
    test set is that frame's first attempt's, and outside a frame there is no agent range at
    all — so all that would be left of the check is "anything staged whose basename is
    `AGENTS.md`". `repo-init@1`'s `bmad.install` row stages exactly that, written by the
    orchestrator, and would park a Run on the system's own file.
    """
    environment = ports.step.run_env
    if environment is None:
        return ports.step
    failure = _verify_failure(ports, run.id, row)
    if row.frame is None:
        return replace(ports.step, run_env=replace(environment, verify_failure=failure))
    rule = frame_anchors(ports.step.git, run, environment, frame, row)
    return replace(
        ports.step,
        run_env=replace(environment, anchors=rule.anchors, verify_failure=failure),
        protected_paths=rule,
    )


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
    apply_step_result(ports.writers, run_id, seq, result, after_route=_budget_hook(ports.writers))
    return require_run(ports.writers, run_id).status


def _budget_hook(writers: WriterPorts) -> AfterRoute:
    """5.7's `after_route`, bound to this call's own writers."""
    return lambda run, row, result: budget_second_record(writers, run, row, result)


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
    if run.status == "done":  # two-phase: commit first, enqueue after (story 5-4)
        enqueue_dependents(writers, writers.engine, run)
    return run.status


def expire(ports: WalkPorts, run_id: UUID) -> RunStatus:
    """The 30-day `recv` reached its deadline: the Run fails, unless a signal beat it."""
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id)
        if run.status != NEEDS_YOU:
            log.info(NOT_PARKED, run_id=str(run_id), status=run.status)
            return run.status
        # Dependency parks never expire — they resolve when the predecessor terminates (story 5-4).
        if run.park_kind == "dependency":
            log.info("dependency park — expiry skipped", run_id=str(run_id))
            return run.status
        run = expire_run(writers, run)
        park_dependents(writers, run)  # park dependents in same UoW (story 5-4)
        writers.uow.commit()
    return run.status
