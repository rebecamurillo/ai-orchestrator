"""`signal_run` (SPEC CAP-5, AD-13): the one writer of every Operator transition (AD-8).

The shape is the same for all ten kinds and this module is that shape:

1. **Validate against the table first.** `application/rules/signals.py` decides whether the
   signal applies here, and refuses with `Conflict` — 409, `signal {kind} invalid for status
   {status} / park {kind}`. It runs before any state machine on purpose: `InvalidTransition`
   is not a `DomainError` (4.1), so a signal reaching one would be a 500 rather than the
   described refusal. Nothing is written on a refusal.
2. **Append the gate record**: the signal's kind as the event, the Operator as the actor
   (the poll job's `terminal_resume` says `terminal`), the payload's own words where it has
   any, and the whole payload kept beside them.
3. **Apply the effect** — `signal_effects` owns which rows move.
4. **Move the Run and clear the park.** A Run outside `needs_you` carries no `park_*`, so
   the three fields are cleared together with the status. `budget_raise` on a `blocked |
   checkpoint` row is the exception AD-13 names: the Run stays `needs_you` and its
   `park_kind` is rewritten to that row's status, so the earlier Question is still the
   Question.
5. **Tell the engine, after the commit.** `engine.signal` wakes the Run's single `recv`
   when *this signal* moved the Run to `running`; `cancel` calls `engine.cancel` instead.
   The kinds that apply no Run transition — `terminal_start`, `terminal_release` — and a
   held `budget_raise` call neither, and neither does a signal that left the Run `done`
   because the skip it applied consumed the last row. "This signal moved it" rather than
   "the Run is running" matters: `terminal_release` is admitted in every non-terminal
   status, so a Run that was already `running` would otherwise be woken by a signal that
   changed nothing about what it should execute.

The brief's prose lists "the `terminal_*` kinds" among those that do not resume, while its
own table and AD-8's Run diagram both give `terminal_resume` `needs_you → running`, and
AD-13 describes its effect as happening "in the resumed engine step". The spine binds: the
rule implemented is *the engine is told exactly when the Run reaches `running`*.

`cancel`'s worktree and process effects are not done here. AD-13 lists them, but the `Git`
and `ProcessRunner` ports arrive in 4.7 and 4.8; `CancelPlan{pgids, worktrees}` carries
everything the caller needs and 4.9 acts on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from orchestrator.application.rules.signals import Rule, record_text, validate
from orchestrator.application.use_cases.signal_effects import EFFECTS, CancelPlan, Effect
from orchestrator.application.use_cases.writers import (
    Entry,
    WriterPorts,
    clear_park,
    finish_run,
    record,
    require_run,
    set_run,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.statuses import run_transition
from orchestrator.domain.values import Signal

#: The status that means the Run carried on, and so that the engine has to be woken.
RUNNING = "running"

#: The kind whose engine call is `cancel` rather than `signal` (AD-13).
CANCEL = "cancel"


@dataclass(frozen=True)
class SignalPorts:
    """What `signal_run` writes and talks through: the shared writer ports, and the engine."""

    writers: WriterPorts
    engine: WorkflowEngine


@dataclass(frozen=True)
class SignalOutcome:
    """What the router answers with: the Run as it now stands, and what the caller must do."""

    run: Run
    #: True when the Run left `needs_you` for `running` and the engine was told.
    resumed: bool
    #: Set by `cancel` only: the process groups to kill and the worktrees to remove (4.9).
    cancel_plan: CancelPlan | None = None


def signal_run(ports: SignalPorts, run_id: UUID, signal: Signal) -> SignalOutcome:
    """Apply one Operator signal to a Run, or refuse it with the reason (409)."""
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id)
        rows = writers.steps.list_for_run(run_id)
        park_row = _park_row(rows, run.park_path)
        rule = validate(run, park_row, signal)
        record(
            writers,
            run,
            Entry(
                event=signal.kind,
                actor=rule.actor,
                path=run.park_path,
                text=record_text(rule, signal.payload),
                payload=signal.payload,
            ),
        )
        effect = EFFECTS[signal.kind](writers, run, rows, park_row, signal)
        run = _apply(writers, run, rule, effect)
        writers.uow.commit()
    resumed = effect.resume and rule.run_event is not None and run.status == RUNNING
    _tell_the_engine(ports, run_id, signal, resumed=resumed)
    return SignalOutcome(run=run, resumed=resumed, cancel_plan=effect.cancel_plan)


def _park_row(rows: list[StepRun], park_path: str | None) -> StepRun | None:
    """The row `run.park_path` names, or `None` for a Run that is not parked on one."""
    return next((row for row in rows if row.path == park_path), None)


def _apply(writers: WriterPorts, run: Run, rule: Rule, effect: Effect) -> Run:
    """The Run's own half of the signal: the status, the park fields, the listed extras."""
    update: dict[str, Any] = dict(effect.run_update)
    if effect.resume and rule.run_event is not None:
        update["status"] = run_transition(run.status, rule.run_event)
        update.update(clear_park())
    moved = set_run(writers, run, **update)
    if effect.finished:
        return finish_run(writers, moved)
    return moved


def _tell_the_engine(ports: SignalPorts, run_id: UUID, signal: Signal, *, resumed: bool) -> None:
    """Wake the Run's `recv`, or stop its workflow — after the writes are durable."""
    if signal.kind == CANCEL:
        ports.engine.cancel(run_id)
    elif resumed:
        ports.engine.signal(run_id, signal)
