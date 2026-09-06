"""`apply_step_result` (SPEC CAP-5): every completion transition, in one unit of work (AD-8).

The walker calls this with whatever the executor returned, and this module decides what that
means for the Attempt, the row, the successor and the Run — the executor decides nothing.
The order is AD-8's and it matters, because each step can change what the next one sees:

0. **Apply the result's `run_updates`.** `git.worktree`, `git.push` and `pr.link` change the
   Run itself — `worktree_path`, `worktrees[]`, `compare_urls[]` (AD-14) — and AD-8 gives an
   executor no way to write one. It returns the values and they are written here, first, in
   the same unit of work: the next row's environment is read after this commits, and
   `cancel` needs the worktree recorded even when the row that made it then failed.
1. **Close the Attempt.** `ended_at`, the status the row reached through it, `output_ref`.
   `exit_code`, `session_id` and the usage columns are not written here: `StepResult` carries
   none of them, and AD-8 has the `agent` executor record them through
   `AttemptRepository.mark_finished` the moment the harness exits, so a restart finds them.
2. **Write the row**: `result.status` through `step_transition`, `reason` beside it.
   `StepResult.gate` is deliberately not written back: the row's gate is what the planner
   recorded before the Run started (AD-7), and a completion is not allowed to re-decide how
   the step's success is judged.
3. **Route.** A redispatch goes back (bounded, AD-9); a `park` stops the Run for the
   Operator; a finished row queues its successor, or ends the Run when it has none; an
   `error` row is routed by its own `on_fail` — `fail` ends the Run `failed`, `continue`
   queues the successor exactly as a finished row does, and `escalate` (the action the DSL
   gives a row that declared none) writes nothing here, because an executor that escalates
   returns the `Park` that says why. A Run left with no runnable row is the walker's own
   `close_run` to report (`use_cases/walk.py`), not a silent stall.

Two rules are worth stating on their own:

**A cancelled Run absorbs a late result.** If the Run is not `running` when the result
arrives, nothing is written at all and one line is logged. The walker's step may well have
been mid-flight when `signal_run` cancelled the Run; the alternative — writing to a
terminal Run — is exactly the double write AD-8 exists to prevent.

**The successor walk reads through `skipped` rows.** AD-8's step diagram says a row is
queued when its predecessor is "done *or skipped*", and `epic@1` over an already-done Story
ends in four consecutive `skipped` rows, so a successor rule that looked only at `seq + 1`
would stall the Run. The walk stops — writing nothing — at the first row that is neither
`planned` nor `skipped`: such a row is already past `planned`, and the only way to reach it
is the walker's own re-walk after a redispatch, which owns it.

`after_route(run, row, result)` is Epic 5's seam: the budget rule's second gate record and
the `park_kind = budget` rewrite hang there. Nothing in Epic 4 passes it.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import structlog

from orchestrator.application.rules.frames import rows_after
from orchestrator.application.templates.plan_model import ON_FAIL_KEY
from orchestrator.application.use_cases.writers import (
    FINISHED,
    Entry,
    WriterPorts,
    finish_run,
    park_run,
    queue_row,
    record,
    require_row,
    require_run,
    set_row,
    set_run,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import (
    InvalidTransition,
    StepEvent,
    StepStatus,
    run_transition,
    step_transition,
)
from orchestrator.domain.values import Park, Redispatch, RunUpdates, StepResult

log = structlog.get_logger(__name__)

#: What Epic 5 hangs the budget's own record on (AD-8). Epic 4 never passes one.
AfterRoute = Callable[[Run, StepRun, StepResult], None]

#: The status a Run has to be in for a result to mean anything.
RUNNING = "running"

#: The `on_fail` action that ends the Run rather than parking it (FR-9).
FAIL = "fail"

#: The `on_fail` action that carries on to the successor as though the row had passed
#: (AD-9). The row keeps its `error` status and its reason: what `continue` decides is
#: where the Run goes next, not whether the step succeeded.
CONTINUE = "continue"

#: The line a result arriving after `cancel` leaves, and nothing else (AD-8, FR-20).
LATE_RESULT = "late result ignored"

#: The event each reportable result status is applied as. A result reporting `planned`,
#: `queued` or `running` is not a completion at all, which is what the refusal below says.
RESULT_EVENTS: dict[StepStatus, StepEvent] = {
    "done": "done",
    "blocked": "blocked",
    "checkpoint": "checkpoint",
    "error": "error",
    "skipped": "skip",
}

#: The park a redispatch turns into once the Template's bound is used up (AD-9).
VERIFY_FAILED = "verify failed {n}/{n}"

#: The park a redispatch turns into when the row it would go back to was never run.
REBASELINE_FAILED = "re-baseline failed after skip"

#: What the gate record says when a redispatch fires.
REDISPATCHED = "verify failed, story re-dispatched {n}/{max}"


def apply_step_result(
    ports: WriterPorts,
    run_id: UUID,
    seq: int,
    result: StepResult,
    *,
    after_route: AfterRoute | None = None,
) -> None:
    """Apply one executor result to the Attempt, the row, the successor and the Run."""
    with ports.uow:
        run = require_run(ports, run_id)
        if run.status != RUNNING:
            log.info(LATE_RESULT, run_id=str(run_id), seq=seq, status=run.status)
            return
        run = _apply_run_updates(ports, run, result)
        row = require_row(ports, run_id, seq)
        attempt = _close_attempt(ports, row, result)
        row = set_row(
            ports,
            row,
            status=step_transition(row.status, _event(result.status)),
            reason=result.reason,
        )
        run = _route(ports, run, row, result, attempt)
        if after_route is not None:
            after_route(run, row, result)
        ports.uow.commit()


def _apply_run_updates(ports: WriterPorts, run: Run, result: StepResult) -> Run:
    """The Run's own columns a result asked for, and only the ones it named (AD-8, AD-14).

    `getattr` over the fields rather than `model_dump`: the values are entities the Run
    stores as entities (`Worktree`), and dumping them here would write dictionaries into a
    `model_copy` that does not validate them back.
    """
    updates = result.run_updates
    if updates is None:
        return run
    named = {
        field: getattr(updates, field)
        for field in RunUpdates.model_fields
        if getattr(updates, field) is not None
    }
    return set_run(ports, run, **named)


def _event(status: StepStatus) -> StepEvent:
    """The step event this result status is applied as, or the refusal naming the token."""
    event = RESULT_EVENTS.get(status)
    if event is None:
        raise InvalidTransition(f"a step result cannot report {status}")
    return event


def _close_attempt(ports: WriterPorts, row: StepRun, result: StepResult) -> Attempt | None:
    """The finish half of the row's latest Attempt, or `None` for a row that never ran."""
    attempt = ports.attempts.get_latest(row.id)
    if attempt is None:
        return None
    closed = attempt.model_copy(
        update={
            "ended_at": ports.clock.now(),
            "status": result.status,
            "output_ref": result.output_ref,
        }
    )
    ports.attempts.mark_finished(closed)
    return closed


def _route(
    ports: WriterPorts,
    run: Run,
    row: StepRun,
    result: StepResult,
    attempt: Attempt | None,
) -> Run:
    """Where the Run goes now: back, parked, on to the successor, done, or failed.

    A result carrying both a `redispatch` and a `park` routes backwards: the brief applies
    the redispatch (c) before it reads `result.park` (d), and an exhausted redispatch has
    its own park to raise. No shipped executor returns both.
    """
    park, went_back = result.park, False
    if result.redispatch is not None:
        park, went_back = _redispatch(ports, run, row, result.redispatch, attempt)
    if park is not None:
        return _park(ports, run, row, park, attempt)
    if went_back:
        return run
    if row.status in FINISHED:
        return _advance(ports, run, row)
    if row.status == "error":
        return _on_fail(ports, run, row, result)
    return run


def _on_fail(ports: WriterPorts, run: Run, row: StepRun, result: StepResult) -> Run:
    """An errored row's own routing (AD-9), read off the row the planner resolved."""
    action = row.with_resolved.get(ON_FAIL_KEY)
    if action == FAIL:
        return _fail(ports, run, row, result)
    if action == CONTINUE:
        return _advance(ports, run, row)
    return run


def _redispatch(
    ports: WriterPorts,
    run: Run,
    row: StepRun,
    redispatch: Redispatch,
    attempt: Attempt | None,
) -> tuple[Park | None, bool]:
    """Send the Run back to an earlier row, or say why it cannot (AD-9's two bounds)."""
    target = require_row(ports, run.id, redispatch.target_seq)
    if target.status == "skipped":
        return Park(kind="verify_failed", reason=REBASELINE_FAILED, path=row.path), False
    if target.redispatch_count >= redispatch.max:
        total = redispatch.max + 1
        reason = VERIFY_FAILED.format(n=total)
        return Park(kind="verify_failed", reason=reason, path=row.path), False
    count = target.redispatch_count + 1
    set_row(
        ports,
        target,
        status=step_transition(target.status, "redispatch"),
        redispatch_count=count,
    )
    record(
        ports,
        run,
        Entry(
            event="redispatch",
            actor="machine",
            path=row.path,
            text=REDISPATCHED.format(n=count, max=redispatch.max),
            attempt_n=attempt.n if attempt is not None else None,
        ),
    )
    return None, True


def _park(ports: WriterPorts, run: Run, row: StepRun, park: Park, attempt: Attempt | None) -> Run:
    """Stop the Run for the Operator, on this row when the park named none of its own."""
    on_row = park if park.path is not None else park.model_copy(update={"path": row.path})
    return park_run(ports, run, on_row, attempt.n if attempt is not None else None)


def _advance(ports: WriterPorts, run: Run, row: StepRun) -> Run:
    """Queue the successor of a finished row, or end the Run when it has none."""
    for candidate in rows_after(ports.steps.list_for_run(run.id), row.seq):
        if candidate.status == "skipped":
            continue
        if candidate.status == "planned":
            queue_row(ports, candidate)
        return run
    return finish_run(ports, run)


def _fail(ports: WriterPorts, run: Run, row: StepRun, result: StepResult) -> Run:
    """`on_fail: fail`: the Run ends `failed`, and the record carries the row's reason."""
    failed = set_run(
        ports,
        run,
        status=run_transition(run.status, "fail"),
        ended_at=ports.clock.now(),
    )
    record(
        ports,
        failed,
        Entry(event="failed", actor="machine", path=row.path, text=result.reason or ""),
    )
    return failed
