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
and handed over as frozen values on `RunEnvironment`/`StepPorts` (AD-8).

**`run_row` reads; the executor does the work**, in a unit of work closed *before* the
executor runs — a process held for minutes (FR-10) cannot hold a session too.

**`apply_result` always binds `apply_step_result`'s own `after_route`** to 5.7's
`budget_second_record`, unconditionally (that module's own docstring names the seam).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from orchestrator.application.rules import protected_paths
from orchestrator.application.rules.frames import rows_in_frame
from orchestrator.application.steps import StepContext, StepPorts, execute
from orchestrator.application.steps.context import RunEnvironment, VerifyFailure
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY
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
from orchestrator.domain.entities.attempt import Attempt
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

#: The Run input `initiative@1` binds its epic list under (AD-17's `{initiative_folder}`).
#: `epic@1` and `story@1` declare none, and a Run without one freezes no `epics.yaml`.
INITIATIVE_FOLDER_INPUT = "initiative_folder"


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
    frame = _frame(writers, run_id, row)
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=run.worktree_path,
        frame_start_sha=_frame_start_sha(frame.attempts),
        previous_attempt=attempts[-2] if len(attempts) > 1 else None,
        attempt=attempts[-1],
        resume_signal=_resume_signal(writers, run_id, resume_event),
        ports=_step_ports(ports, run, row, frame),
    )


def _step_ports(ports: WalkPorts, run: Run, row: StepRun, frame: _Frame) -> StepPorts:
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
    rule = _anchors(ports, run, environment, frame)
    return replace(
        ports.step,
        run_env=replace(environment, anchors=rule.anchors, verify_failure=failure),
        protected_paths=rule,
    )


@dataclass(frozen=True)
class _Frame:
    """One Story frame as the walker read it: its rows, and every attempt they recorded.

    Read once per row: three questions are asked of it — the commit the frame started at, the
    tests its first attempt froze, the ranges its dispatches recorded — over the same rows.
    """

    rows: tuple[StepRun, ...] = ()
    attempts: tuple[Attempt, ...] = ()


def _frame(ports: WriterPorts, run_id: UUID, row: StepRun) -> _Frame:
    """The row's frame, in plan order then attempt order; empty outside a frame (AD-9)."""
    if row.frame is None:
        return _Frame()
    rows = tuple(rows_in_frame(ports.steps.list_for_run(run_id), row.frame))
    return _Frame(
        rows=rows,
        attempts=tuple(
            attempt for entry in rows for attempt in ports.attempts.list_for_row(entry.id)
        ),
    )


def _anchors(
    ports: WalkPorts, run: Run, environment: RunEnvironment, frame: _Frame
) -> protected_paths.FrameAnchors:
    """AD-17's anchor set and the frame's agent ranges, resolved once for two readers.

    Here because this is the only place holding both the frame's rows and the repositories
    (AD-8). The tail reads the anchor set off `RunEnvironment`; the commit-guard reaches the
    whole object through the port it already calls.
    """
    return protected_paths.FrameAnchors(
        git=ports.step.git,
        worktree=Path(run.worktree_path or ""),
        anchors=protected_paths.build(
            spec_folders=_spec_folders(environment, frame.rows),
            initiative_folder=str(run.inputs.get(INITIATIVE_FOLDER_INPUT) or ""),
            frozen_test_files=_frozen_test_files(frame.attempts),
        ),
        ranges=_agent_ranges(frame.attempts),
    )


def _spec_folders(environment: RunEnvironment, rows: Sequence[StepRun]) -> tuple[str, ...]:
    """Every spec folder this frame touches: the Run's own input, and each row's resolved one."""
    folders = {environment.spec_folder or ""}
    folders.update(str(row.with_resolved.get(SPEC_FOLDER_KEY) or "") for row in rows)
    return tuple(sorted(folder for folder in folders if folder))


def _frozen_test_files(attempts: Sequence[Attempt]) -> tuple[str, ...]:
    """AD-17: the `frozen_test_files` of the frame's lowest-`n` attempt with a `start_sha`."""
    for attempt in attempts:
        if attempt.start_sha is not None:
            return attempt.frozen_test_files or ()
    return ()


def _agent_ranges(attempts: Sequence[Attempt]) -> tuple[tuple[str, str], ...]:
    """Every agent range the frame recorded: an attempt that started *and* came back.
    `end_sha` is written by the agent tail alone, so an attempt carrying both SHAs is a
    dispatch and nothing else — the scope AD-17 gives the commit-guard."""
    return tuple(
        (attempt.start_sha, attempt.end_sha)
        for attempt in attempts
        if attempt.start_sha is not None and attempt.end_sha is not None
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


def _frame_start_sha(attempts: Sequence[Attempt]) -> str | None:
    """The commit the row's Story frame started at, in AD-17's own words: the frame's
    lowest-`n` attempt that *has* a `start_sha`. Reading past the attempts that recorded none
    is the whole rule: a Story frame's first row is `git.sync`, which records no commit, so an
    answer taken from the first row that merely *has* an attempt would always be `None`."""
    return next((attempt.start_sha for attempt in attempts if attempt.start_sha is not None), None)


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
