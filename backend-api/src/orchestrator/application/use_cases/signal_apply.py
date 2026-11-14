"""`signal_run`'s two halves (story 4-1, AD-8): the writes inside a unit of work, and the
engine call after its commit.

`apply_signal` takes a Run its caller has already read under the row lock and writes
everything a signal writes, in `signal_run`'s order: the stale-stop refusal (AD-24),
`validate`, the `mode` default, the gate record, the effect, the Run's transition, and the
dependents of a cancelled Run. It opens no unit of work, commits nothing and calls no
engine, so a caller with its own writes in the same transaction (the chat reply's close)
commits them together. `finish_signal` is what follows a commit: the engine call, and the
enqueue of a done Run's dependents.

`signal_run` is lock, `apply_signal`, commit, `finish_signal`; its own module re-exports
every public name here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from orchestrator.application.rules.signals import Rule, record_text, validate
from orchestrator.application.use_cases.metric_calculations import enqueue_queued
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.signal_effects import EFFECTS, CancelPlan, Effect
from orchestrator.application.use_cases.writers import (
    Entry,
    WriterPorts,
    clear_park,
    enqueue_dependents,
    finish_run,
    park_dependents,
    record,
    set_run,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict, Invalid
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.statuses import Actor, run_transition
from orchestrator.domain.values import Signal

#: The status that means the Run carried on, and so that the engine has to be woken.
RUNNING = "running"

#: The kind whose engine call is `cancel` rather than `signal` (AD-13).
CANCEL = "cancel"

#: The two signal kinds that carry an optional `mode` key (story 3-3).
_MODE_KINDS: frozenset[str] = frozenset({"answer", "retry"})
#: The payload key and the two accepted values.
_MODE_KEY = "mode"
_MODE_SESSION = "session"
_MODE_RESTART = "restart"
_KNOWN_MODES: frozenset[str] = frozenset({_MODE_RESTART, _MODE_SESSION})

#: What a signal naming an earlier stop is told (AD-24).
STALE_STOP = "this signal names stop {stop}, and the Run is at stop {current}{where}"
STOP_WHERE = ": {kind}"
STOP_AT = " at {path}"


def _always_false(_: str) -> bool:
    return False


def _no_attempt(_: UUID) -> Attempt | None:
    return None


@dataclass(frozen=True)
class SignalPorts:
    """What `signal_run` writes and talks through: the shared writer ports, and the engine.

    `harness_is_resumable` and `latest_attempt_for_run` are the two callables that let
    `_check_mode` validate `mode="session"` without importing infrastructure (AD-2).  They
    default to `False`/`None` so callers that never send `mode="session"` need not wire them
    — the mode check short-circuits on `mode="restart"` (the implicit default) and never
    calls them.
    """

    writers: WriterPorts
    engine: WorkflowEngine
    harness_is_resumable: Callable[[str], bool] = field(default=_always_false)
    latest_attempt_for_run: Callable[[UUID], Attempt | None] = field(default=_no_attempt)
    #: Required when the `start` Signal may be sent (story 5-3). `None` degrades gracefully
    #: for every existing call site that predates this field and never sends `start`.
    preflight: PreflightPorts | None = None


@dataclass(frozen=True)
class SignalOutcome:
    """What the router answers with: the Run as it now stands, and what the caller must do."""

    run: Run
    #: True when the Run left `needs_you` for `running` and the engine was told.
    resumed: bool
    #: Set by `cancel` only: the process groups to kill and the worktrees to remove (4.9).
    cancel_plan: CancelPlan | None = None


@dataclass(frozen=True)
class Applied:
    """What `apply_signal` wrote, for `finish_signal` to act on after the commit."""

    run: Run
    rule: Rule
    effect: Effect


def apply_signal(
    ports: SignalPorts, run: Run, signal: Signal, *, actor: Actor | None = None
) -> Applied:
    """Every write of one signal on a Run read under its row lock; `actor` overrides the
    table's. Refusals raise before anything is written."""
    writers = ports.writers
    refuse_stale_stop(run, signal)
    rows = writers.steps.list_for_run(run.id)
    park_row = _park_row(rows, run.park_path)
    rule = validate(run, park_row, signal, rows)
    _check_mode(ports, run, signal)
    record(
        writers,
        run,
        Entry(
            event=signal.kind,
            actor=actor or rule.actor,
            path=run.park_path,
            text=record_text(rule, signal.payload),
            payload=signal.payload,
        ),
    )
    effect = EFFECTS[signal.kind](writers, run, rows, park_row, signal)
    run = _apply(writers, run, rule, effect)
    # Park dependents in the same UoW when this run reaches `cancelled` (story 5-4).
    if run.status == "cancelled":
        park_dependents(writers, run)
    return Applied(run=run, rule=rule, effect=effect)


def finish_signal(
    ports: SignalPorts, run_id: UUID, signal: Signal, applied: Applied
) -> SignalOutcome:
    """After the commit: tell the engine, and enqueue a done Run's dependents."""
    run, rule, effect = applied.run, applied.rule, applied.effect
    resumed = effect.resume and rule.run_event is not None and run.status == RUNNING
    _tell_the_engine(ports, run_id, signal, resumed=resumed, finished=effect.finished)
    # Two-phase enqueue for done dependents after signal (e.g. skip-to-done, story 5-4).
    if run.status == "done":
        enqueue_dependents(ports.writers, ports.writers.engine, run)
    # `ports.engine`, not `writers.engine`: the signal providers open writers without one
    enqueue_queued(ports.engine, ports.writers.calculations, run)
    return SignalOutcome(run=run, resumed=resumed, cancel_plan=effect.cancel_plan)


def refuse_stale_stop(run: Run, signal: Signal) -> None:
    """Refuse, before anything is written, a signal naming a stop other than the current one."""
    if signal.stop is None or signal.stop == run.park_seq:
        return
    where = STOP_WHERE.format(kind=run.park_kind) if run.park_kind else ""
    if run.park_path:
        where += STOP_AT.format(path=run.park_path)
    raise Conflict(STALE_STOP.format(stop=signal.stop, current=run.park_seq, where=where))


def _check_mode(ports: SignalPorts, run: Run, signal: Signal) -> None:
    """Refuse an unknown or unavailable `mode` before any gate record is written (story 3-3).

    Runs only for `answer` and `retry` — the two kinds that carry `mode`. An absent `mode`
    defaults to `"session"` when reply_available is True, else `"restart"` (story 4,
    2026-09-25); the default is written into `signal.payload` so `_planned` reads it and the
    gate record captures it. A present `"restart"` is always accepted. `"session"` is
    accepted only when the run's harness supports resume *and* the latest attempt recorded a
    session_id — the two facts that together define reply_available (AD-10).
    """
    if signal.kind not in _MODE_KINDS:
        return
    if _MODE_KEY not in signal.payload:
        attempt = ports.latest_attempt_for_run(run.id)
        reply_available = (
            attempt is not None
            and attempt.session_id is not None
            and ports.harness_is_resumable(attempt.harness or "")
        )
        signal.payload[_MODE_KEY] = _MODE_SESSION if reply_available else _MODE_RESTART
    mode = signal.payload[_MODE_KEY]
    if mode not in _KNOWN_MODES:
        raise Invalid(f"unknown mode: {mode}")
    if mode != _MODE_SESSION:
        return
    attempt = ports.latest_attempt_for_run(run.id)
    if attempt is None or attempt.session_id is None:
        raise Invalid("mode 'session' not available: no session recorded")
    if not ports.harness_is_resumable(attempt.harness or ""):
        raise Invalid("mode 'session' not available: harness does not support resume")


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


def _tell_the_engine(
    ports: SignalPorts, run_id: UUID, signal: Signal, *, resumed: bool, finished: bool
) -> None:
    """Wake the Run's `recv`, or stop its workflow — after the writes are durable.

    `finished` is a signal that ended the Run itself (a Continue on the plan's final
    checkpoint row — story 4-5's `done-checkpoint` is the shipped case, and a skip with
    nothing left to run is another): nothing remains to walk, but the workflow parked in
    `recv` would otherwise sleep out `HUMAN_WAIT_SECONDS` holding its queue slot (AD-12),
    so it is stopped the same way a cancel stops one. A run that was never enqueued (a
    dependency park) has no workflow; `engine.cancel` swallows that case by contract.
    """
    if signal.kind == CANCEL or finished:
        ports.engine.cancel(run_id)
    elif resumed:
        ports.engine.signal(run_id, signal)
