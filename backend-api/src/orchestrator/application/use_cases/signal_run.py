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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from orchestrator.application.preflight.model import PreflightRequest
from orchestrator.application.rules.signals import Rule, record_text, validate
from orchestrator.application.use_cases.preflight import PreflightPorts, preflight_and_plan
from orchestrator.application.use_cases.signal_effects import EFFECTS, CancelPlan, Effect
from orchestrator.application.use_cases.writers import (
    Entry,
    WriterPorts,
    clear_park,
    enqueue_dependents,
    finish_run,
    park_dependents,
    record,
    require_run,
    set_run,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict, Invalid
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.statuses import run_transition
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


def _always_false(_: str) -> bool:
    return False


def _no_attempt(_: UUID) -> Attempt | None:
    return None


#: The signal that enqueues a saved Run on Operator request (story 5-3).
START = "start"

#: The park kind that means the Run is waiting for a predecessor (story 5-4).
DEPENDENCY = "dependency"


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


def signal_run(ports: SignalPorts, run_id: UUID, signal: Signal) -> SignalOutcome:
    """Apply one Operator signal to a Run, or refuse it with the reason (409/422)."""
    if signal.kind == START:
        return _start_saved_run(ports, run_id, signal)
    # Dependency-park `continue` needs its own two-phase enqueue flow (story 5-4):
    # park_path is None so EFFECTS["continue"] → _parked(None) would AssertionError.
    if signal.kind == "continue":
        _peek = ports.writers.runs.get(run_id)
        if _peek is not None and _peek.park_kind == DEPENDENCY:
            return _continue_dependency_run(ports, run_id, signal)
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id)
        rows = writers.steps.list_for_run(run_id)
        park_row = _park_row(rows, run.park_path)
        rule = validate(run, park_row, signal)
        _check_mode(ports, run, signal)
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
        # Park dependents in the same UoW when this run reaches `cancelled` (story 5-4).
        if run.status == "cancelled":
            park_dependents(writers, run)
        writers.uow.commit()
    resumed = effect.resume and rule.run_event is not None and run.status == RUNNING
    _tell_the_engine(ports, run_id, signal, resumed=resumed, finished=effect.finished)
    # Two-phase enqueue for done dependents after signal (e.g. skip-to-done, story 5-4).
    if run.status == "done":
        enqueue_dependents(writers, writers.engine, run)
    return SignalOutcome(run=run, resumed=resumed, cancel_plan=effect.cancel_plan)


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


def _preflight_req_from_run(run: Run) -> PreflightRequest:
    """Reconstruct `PreflightRequest` from a stored Run for the Probe re-read at start time.

    `run.inputs` always holds `base_branch`, `harness`, and `model` (set by `_inputs_dict`
    in `create_run`); extra keys are harmless for fail-line checks.
    """
    return PreflightRequest(
        template_name=run.template_name,
        template_version=run.template_version,
        project_id=run.project_id,
        repository_id=run.repository_id,
        base_branch=str(run.inputs.get("base_branch", "")),
        inputs=dict(run.inputs),
        harness=run.inputs.get("harness"),
        model=run.inputs.get("model"),
        budget_usd=run.budget_usd,
        re_review_done=run.re_review_done,
        # Exclude the saved Run itself so the branch-held check does not find it holding
        # its own branch — the Run is queued but not yet executing (story 5-3).
        exclude_run_id=run.id,
    )


def _continue_dependency_run(ports: SignalPorts, run_id: UUID, signal: Signal) -> SignalOutcome:
    """Enqueue a dependency-parked Run on Operator `continue` (story 5-4).

    Dedicated branch because `EFFECTS["continue"]` calls `_parked(park_row)` which asserts
    `park_row is not None`, but dependency parks have `park_path=None`, so `park_row` is
    `None`. This handler clears the park, resets status to `queued`, and enqueues the run
    via the engine — the same two-phase commit `_start_saved_run` uses for story 5-3.
    """
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id)
        validate(run, None, signal)
        record(
            writers,
            run,
            Entry(event="continue", actor="operator", path=None, text="", payload=signal.payload),
        )
        # Clear the dependency park and reset to `queued` so the engine starts it fresh.
        # `needs_you → queued` is not in RUN_TRANSITIONS (the machine only allows
        # `needs_you → running` via the "continue" event), so we write directly like
        # `park_dependents` does for the inverse direction (story 5-4 design note).
        # `after_run_ids` is deliberately NOT cleared (AD-13, spine amendment 2026-09-23):
        # the enqueue below writes an `engine_ref`, which is what resolution filters on, so
        # clearing would buy nothing and would erase the initiative's own DAG edge.
        run = set_run(
            writers,
            run,
            status="queued",
            park_kind=None,
            park_path=None,
            park_reason=None,
        )
        writers.uow.commit()
    # Enqueue outside the first commit so the Run row is durable before the engine sees it.
    partition_key = (
        f"{run.repository_id}:{run.partition_branch or run.inputs.get('base_branch', '')}"
    )
    engine_ref = ports.engine.enqueue(run.id, partition_key=partition_key)
    with writers.uow:
        run = set_run(writers, run, engine_ref=engine_ref)
        writers.uow.commit()
    return SignalOutcome(run=run, resumed=False)


def _start_saved_run(ports: SignalPorts, run_id: UUID, signal: Signal) -> SignalOutcome:
    """Enqueue a saved Run on Operator request (story 5-3, AD-6).

    Dedicated branch because:
    - The gate record event is `"started_by_operator"` (a `LifecycleEvent`), not `"start"`
      (the `SignalKind`) — a generic flow would record the wrong token.
    - The engine call is `enqueue`, not `signal` — `_tell_the_engine` has no place for it.
    - The Probe is re-read before enqueueing; consent is never checked (AD-13).
    """
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id)
        # Validate against the table: run_statuses={"queued"}, extra=_is_saved.
        # `validate` raises Conflict if the run is not queued or engine_ref is non-empty.
        # It runs BEFORE the preflight check so that a "start" sent to a non-queued Run
        # earns the table's own 409 rather than the missing-preflight error below.
        validate(run, None, signal)
        if ports.preflight is None:
            raise Conflict("start signal requires preflight; call site is missing it")
        # Re-read the Probe — the Operator could have left the tab open while something else
        # changed the Repository (e.g. another Run started on the same branch).
        preflighted = preflight_and_plan(ports.preflight, _preflight_req_from_run(run))
        failing = [line for line in preflighted.result.lines if line.status == "fail"]
        if failing:
            raise Conflict("; ".join(line.text for line in failing))
        # Record the gate event; the event is the lifecycle token, not the signal kind.
        record(
            writers,
            run,
            Entry(event="started_by_operator", actor="operator", path=None, text="", payload={}),
        )
        # `after_run_ids` is left untouched (AD-13, spine amendment 2026-09-23): the Run
        # gets an `engine_ref` below, and that — not an empty list — is what keeps a later
        # terminal transition from resolving it a second time.
        writers.uow.commit()
    # Enqueue outside the first commit so the Run row is durable before the engine sees it.
    partition_key = (
        f"{run.repository_id}:{run.partition_branch or run.inputs.get('base_branch', '')}"
    )
    engine_ref = ports.engine.enqueue(run.id, partition_key=partition_key)
    with writers.uow:
        run = set_run(writers, run, engine_ref=engine_ref)
        writers.uow.commit()
    return SignalOutcome(run=run, resumed=False)
