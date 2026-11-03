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

Steps 1 to 4 are `signal_apply.py::apply_signal`, inside the caller's unit of work, and
step 5 is its `finish_signal`, after the commit (story 4-1); this module locks, applies,
commits and finishes.

The brief's prose lists "the `terminal_*` kinds" among those that do not resume, while its
own table and AD-8's Run diagram both give `terminal_resume` `needs_you → running`, and
AD-13 describes its effect as happening "in the resumed engine step". The spine binds: the
rule implemented is *the engine is told exactly when the Run reaches `running`*.

`cancel`'s worktree and process effects are not done here. AD-13 lists them, but the `Git`
and `ProcessRunner` ports arrive in 4.7 and 4.8; `CancelPlan{pgids, worktrees}` carries
everything the caller needs and 4.9 acts on it.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.preflight.model import PreflightRequest
from orchestrator.application.rules.signals import validate
from orchestrator.application.use_cases.preflight import preflight_and_plan
from orchestrator.application.use_cases.signal_apply import (
    CANCEL,
    RUNNING,
    STALE_STOP,
    STOP_AT,
    STOP_WHERE,
    Applied,
    SignalOutcome,
    SignalPorts,
    _always_false,
    _no_attempt,
    apply_signal,
    finish_signal,
    refuse_stale_stop,
)
from orchestrator.application.use_cases.writers import Entry, record, require_run, set_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal

__all__ = [
    "CANCEL",
    "DEPENDENCY",
    "RUNNING",
    "STALE_STOP",
    "START",
    "STOP_AT",
    "STOP_WHERE",
    "Applied",
    "SignalOutcome",
    "SignalPorts",
    "_always_false",
    "_no_attempt",
    "apply_signal",
    "finish_signal",
    "refuse_stale_stop",
    "signal_run",
]

#: The signal that enqueues a saved Run on Operator request (story 5-3).
START = "start"

#: The park kind that means the Run is waiting for a predecessor (story 5-4).
DEPENDENCY = "dependency"


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
        run = require_run(writers, run_id, lock=True)
        applied = apply_signal(ports, run, signal)
        writers.uow.commit()
    return finish_signal(ports, run_id, signal, applied)


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
        run = require_run(writers, run_id, lock=True)
        refuse_stale_stop(run, signal)
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
        run = require_run(writers, run_id, lock=True)
        refuse_stale_stop(run, signal)
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
