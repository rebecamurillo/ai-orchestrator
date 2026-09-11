"""`apply_step_result` (SPEC CAP-5): every completion transition, in one unit of work (AD-8).

The walker calls this with whatever the executor returned, and this module decides what that
means for the Attempt, the row, the successor and the Run — the executor decides nothing.
The order is AD-8's and it matters, because each step can change what the next one sees:

0. **Apply the result's `run_updates`.** `git.worktree`, `git.push` and `pr.link` change the
   Run itself — `worktree_path`, `worktrees[]`, `compare_urls[]` (AD-14) — and AD-8 gives an
   executor no way to write one. It returns the values and they are written here, first, in
   the same unit of work: the next row's environment is read after this commits, and
   `cancel` needs the worktree recorded even when the row that made it then failed.
1. **Close the Attempt.** `ended_at`, the status the row reached through it, `output_ref`,
   and `log_path` when the result names one — the spine puts that column on every row's
   attempt, and a kind that starts a process has no `AttemptRepository` to write it with.
   `exit_code`, `session_id` and the usage columns are not written here: `StepResult`
   carries none of them, and AD-8 has the `agent` executor record them through
   `AttemptRepository.mark_finished` the moment the harness exits, so a restart finds them.
2. **Write the row**: `result.status` through `step_transition`, `reason` beside it.
   `StepResult.gate` is deliberately not written back: the row's gate is what the planner
   recorded before the Run started (AD-7), and a completion is not allowed to re-decide how
   the step's success is judged.
3. **Route.** A redispatch goes back (bounded, AD-9); a `park` stops the Run for the
   Operator; a `retry` re-queues *this* row, counted and recorded (AD-9, FR-16); a
   finished row queues its successor, or ends the Run when it has none; an
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

**5.9's own trigger hangs here too, unconditionally.** The instant a Story frame's own
commit-guard row itself reaches `done`, `record_trajectory` runs inside the same unit of
work — the frame's last row, and the only point at which the trajectory's `end_sha` ("HEAD
after the commit-guard") is a fact. It is idempotent on `(run_id, frame)`, so a durable-step
replay of this same call records nothing twice (AD-19, AD-6).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import structlog

from orchestrator.application.rules.frames import rows_after
from orchestrator.application.rules.signals import REBASELINE_FAILED
from orchestrator.application.steps import COMMIT_KIND
from orchestrator.application.templates.plan_model import ON_FAIL_KEY
from orchestrator.application.use_cases.record_trajectory import record_trajectory
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

#: The park a redispatch turns into when the row it would go back to was never run. Stated
#: in `rules/signals.py`, which also reads it: the stop that reason names offers no second
#: *Skip story* (6.4), and a rules module may not import a use case to learn its own text.

#: What the gate record says when a redispatch fires.
REDISPATCHED = "verify failed, story re-dispatched {n}/{max}"

#: What it says when a Template's own `retry` fires — the reason the executor gave, and
#: which of the contract's attempts this is (AD-9: bounded, recorded, never silent).
RETRIED = "{reason} · retry {n}/{max}"


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
        _maybe_record_trajectory(ports, row)
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
    named: dict[str, Any] = {
        "ended_at": ports.clock.now(),
        "status": result.status,
        "output_ref": result.output_ref,
    }
    # Only when named: `agent` wrote its own through `mark_finished`, and this would blank it.
    if result.log_path is not None:
        named["log_path"] = result.log_path
    closed = attempt.model_copy(update=named)
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
        return _park(ports, run, row, park, attempt, payload=result.payload)
    if went_back:
        return run
    if result.retry is not None:
        _retry(ports, run, row, result, attempt)
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


def _retry(
    ports: WriterPorts, run: Run, row: StepRun, result: StepResult, attempt: Attempt | None
) -> None:
    """Run this row again, counted and recorded (AD-9, FR-16). No Run transition: the Run is
    still `running`, and `("error", "retry")` is the only pair the machine re-queues from —
    a result that carried a `retry` on any other status raises `InvalidTransition` here,
    which is a caller's bug rather than an outcome.

    The bound itself was already applied: the executor returned a `retry` only while the
    row's counter was below the contract's `max` (`application/rules/routing.py`), so this
    counts the attempt rather than deciding whether there is one.
    """
    retry = result.retry
    assert retry is not None  # `_route` calls this only when the result carries one
    count = row.retry_count + 1
    set_row(ports, row, status=step_transition(row.status, "retry"), retry_count=count)
    record(
        ports,
        run,
        Entry(
            event="retry_auto",
            actor="machine",
            path=row.path,
            text=RETRIED.format(reason=result.reason or "", n=count, max=retry.max),
            attempt_n=attempt.n if attempt is not None else None,
        ),
    )


def _park(  # noqa: PLR0913 — the park, the attempt it happened on and what it kept are one write
    ports: WriterPorts,
    run: Run,
    row: StepRun,
    park: Park,
    attempt: Attempt | None,
    *,
    payload: dict[str, Any],
) -> Run:
    """Stop the Run for the Operator, on this row when the park named none of its own.

    `payload` is the result's own (AD-17's hit list): the executor returns the values and
    this is where they are written, in the unit of work already open. Only the park path
    carries one — `retry_auto` and `redispatch` are records this module decides itself.
    """
    on_row = park if park.path is not None else park.model_copy(update={"path": row.path})
    return park_run(ports, run, on_row, attempt.n if attempt is not None else None, payload)


def _advance(ports: WriterPorts, run: Run, row: StepRun) -> Run:
    """Queue the successor of a finished row, or end the Run when it has none."""
    for candidate in rows_after(ports.steps.list_for_run(run.id), row.seq):
        if candidate.status == "skipped":
            continue
        if candidate.status == "planned":
            queue_row(ports, candidate)
        return run
    return finish_run(ports, run)


def budget_second_record(ports: WriterPorts, run: Run, row: StepRun, result: StepResult) -> None:
    """Epic 5's own `after_route` (AD-8, AD-11): a routed stop that is *also* over budget
    gets a second gate record, and `run.park_kind`/`park_path`/`park_reason` are rewritten
    to `budget` on top of it.

    `set_run` rather than `park_run`: the first park already moved the Run to `needs_you`
    (`_route` ran before this), and `RUN_TRANSITIONS` has no `(needs_you, "park")` pair —
    a second `run_transition` call would raise. The three park fields are "written
    together with the gate_record" every time (`domain/entities/run.py`'s own docstring),
    which this still does; it is only the *status* transition that does not repeat.
    """
    park = result.budget_park
    if park is None:
        return
    path = park.path or row.path
    updated = set_run(ports, run, park_kind=park.kind, park_path=path, park_reason=park.reason)
    record(ports, updated, Entry(event=park.kind, actor="machine", path=path, text=park.reason))


def _maybe_record_trajectory(ports: WriterPorts, row: StepRun) -> None:
    """5.9's own trigger: the frame's commit-guard row reaching `done` closes the Story.

    Gated on `row.kind` rather than the literal step id — `application/steps/__init__.py`'s
    own "a kind is named there or nowhere" (AD-9) — so a Template that names its commit row
    something other than `commit-guard` still triggers this correctly.
    """
    if row.kind != COMMIT_KIND or row.status != "done" or row.frame is None:
        return
    record_trajectory(
        row.run_id,
        row.frame,
        runs=ports.runs,
        steps=ports.steps,
        attempts=ports.attempts,
        gate_records=ports.records,
        git=ports.git,
        trajectories=ports.trajectories,
        clock=ports.clock,
    )


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
