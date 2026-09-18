"""AD-13's signal table, as data: what each Signal is admitted on, and what it records.

The table half of `rules/signals.py`, split out of it on line count alone when 6.7 added the
terminal narrowing to a module that was at 397 of its 400 lines — the seam that module's own
docstring already named: the table (`Rule`, its predicates, its text builders, `VALID`)
against the questions asked of it (`validate`, `admitted_signals`, `run_admitted_signals`,
`record_text`, `row_at`). Every public name here is re-exported by `rules/signals.py`, so no
existing import moved, and the paragraphs below are the ones that were written there.

`signal_run` validates against `VALID` **before** it touches a state machine. That order is
the reason `InvalidTransition` is not a `DomainError` (4.1): an operator sending a signal
the table refuses gets a `Conflict` — 409 with `INVALID` below — and never reaches a
transition function, so a raised `InvalidTransition` always means a bug rather than a
described outcome.

Two rules of the table are written in a form `admitted_signals(park_kind, row_kind)` — the
same table read the other way, in `rules/signals.py` — can answer from the park kind and the
parked row's kind alone:

- **`retry` lists `protected_path` among its park kinds.** The brief writes the rule as
  "`park_kind ∈ {timeout, push_rejected, misconfigured, internal, verify_failed}` or park
  row `error`". Every park kind whose row is left `error` is already in that set except
  `protected_path` — and `plan_stale` (row `error`, Continue and Cancel only) and `budget`
  (which keeps the row's routed status, so possibly `error`) would both be wrongly admitted
  by the "or park row `error`" half. AD-13 calls PRD §4.6 "the reason-text and
  admitted-signal contract", so the park-kind set is the one written here.
- **The `∉` rows are stored expanded.** `skip_story` and `skip_epic` are stated as
  exclusions; `PARK_KINDS` minus the excluded set is the same rule and is one lookup.

What the columns cannot say is written as `Rule.extra`: a raised budget has to exceed the
spend, a skip has to have a frame to act on, and the terminal kinds turn on
`run.terminal_session`. Each is a named predicate, so the table stays readable.

`raised_budget` and `accepted_files` — the two payload readers — live here rather than with
the questions, because `_budget_raised_text` and `_accepted_text` call them: splitting them
the other way would make the two modules import each other.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from orchestrator.application.rules.frames import EPIC_TEMPLATE, epic_frame, story_frame
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import (
    PARK_KINDS,
    RUN_STATUSES,
    TERMINAL_RUN,
    Actor,
    ParkKind,
    RunEvent,
    RunStatus,
    SignalKind,
    StepStatus,
)
from orchestrator.domain.values import Signal

#: The `Run.status` values a signal that is not `cancel` is sent to.
PARKED: frozenset[RunStatus] = frozenset({"needs_you"})

#: Every non-terminal Run status — what `cancel` and the terminal kinds are admitted in.
#: Derived rather than listed, so a new Run status is admitted or refused by AD-8's own
#: two tables and never by a copy of them that went stale here.
NON_TERMINAL: frozenset[RunStatus] = frozenset(RUN_STATUSES) - TERMINAL_RUN

#: Every park kind: the rules whose admission does not depend on why the Run stopped.
ANY_PARK: frozenset[ParkKind] = frozenset(PARK_KINDS)

#: The payload key a raised budget arrives under.
BUDGET_KEY = "budget_usd"

#: The payload key an Answer's text arrives under.
ANSWER_KEY = "text"

#: The payload key `continue` on a `protected_path` park carries the accepted files under.
FILES_KEY = "files"

#: The sentence a raised budget's own gate record carries (AD-13). It names the new figure
#: rather than the fact that a person raised it, at the two decimal places
#: `rules/budget.py::forced` already renders a budget park's own reason to.
BUDGET_RAISED = "budget raised to ${budget}"

#: What a `budget_raise` that does not clear the spend is refused with. `Rule.extra_refusal`
#: is why this reaches the Operator instead of `INVALID`: the table's columns all admit the
#: signal here, and `_raises_the_budget` alone says no, so the sentence that says *why* is
#: the useful one (NFR-8).
BUDGET_TOO_LOW = "new budget must exceed spend ${spend}"

#: The sentence a `continue` that accepted files carries (FR-31, 6.6): the paths, in the
#: order they arrived. A `continue` at a `checkpoint` or `plan_stale` park accepts none and
#: keeps the fixed phrase instead.
ACCEPTED = "accepted: {paths}"
ACCEPTED_SEPARATOR = ", "

#: What `terminal_resume`'s own gate record says (FR-21, 6.7), verbatim from the brief. Two
#: clean polls are the whole reason the Run moved, so the sentence names them: the Story file
#: read `done` and the worktree held nothing uncommitted, twice, thirty seconds apart.
TERMINAL_RESUMED = "story file done and tree clean, resumed by terminal"

#: The park reason `apply_step_result` leaves when a skipped Story's re-baseline fails —
#: AD-9's redispatch onto a target that was never run (`use_cases/apply_step_result.py`
#: imports it from here, so the sentence has one definition and this module can read it
#: without importing a use case). It is stated here because it is an *admission* fact:
#: PRD §4.6 is "the reason-text and admitted-signal contract", and the Story that park is
#: about has already been skipped, so `skip_story` has nothing left to skip.
REBASELINE_FAILED = "re-baseline failed after skip"


@dataclass(frozen=True)
class Rule:
    """When one `Signal.kind` is admitted, and what its gate record says."""

    #: The park kinds this signal is admitted on, read only while the Run is `needs_you`.
    park_kinds: frozenset[ParkKind]
    #: The Run statuses it is admitted in.
    run_statuses: frozenset[RunStatus] = PARKED
    #: The parked row's `kind`, or `None` when any kind is admitted.
    row_kinds: frozenset[str] | None = None
    #: The parked row's `status`, or `None` when any status is admitted.
    row_statuses: frozenset[StepStatus] | None = None
    #: What the table states in words rather than in columns; `None` when it states nothing.
    extra: Callable[[Run, StepRun | None, Signal], bool] | None = None
    #: The refusal `extra` alone earns, where the table has a better sentence than `INVALID`.
    #: Formatted with the Run, so a `budget_raise` can name the spend it has to beat.
    extra_refusal: str | None = None
    #: The Run transition this signal applies, or `None` when the Run's status is unchanged.
    run_event: RunEvent | None = None
    #: Who the gate record names.
    actor: Actor = "operator"
    #: The sentence the gate record carries when the payload supplies none.
    text: str = ""
    #: The payload key whose value is the gate record's text instead of `text`.
    text_key: str | None = None
    #: The gate record's text, built from the payload — for a sentence that has to quote a
    #: *validated* value, which is what `text_key` (the payload's own string, verbatim)
    #: cannot do. `None` from the builder falls through to `text`.
    text_from: Callable[[dict[str, Any]], str | None] | None = None
    #: True for the actions a person takes on the Run detail — what `admitted_signals`
    #: answers with. The terminal kinds are driven by the browser and the poll job.
    operator_action: bool = True


def _raised_budget(payload: dict[str, Any]) -> Decimal | None:
    """The `budget_usd` a `budget_raise` carries, or `None` when it carries no number."""
    try:
        return Decimal(str(payload[BUDGET_KEY]))
    except KeyError, InvalidOperation, ValueError:
        return None


def _raises_the_budget(run: Run, _row: StepRun | None, signal: Signal) -> bool:
    """AD-13: a raised budget has to be a real number, more than the Run has spent.

    `is_finite` is not decoration: `Decimal("NaN") > spend` *raises* `InvalidOperation`,
    which would leave the operator with a 500 where the table promises a 409, and
    `Decimal("Infinity")` would be accepted as a budget no spend can ever exceed.
    """
    budget = _raised_budget(signal.payload)
    return budget is not None and budget.is_finite() and budget > run.spend_usd


def _has_story_frame(run: Run, _row: StepRun | None, _signal: Signal) -> bool:
    """`skip_story` needs a `…stories[n]` frame under `park_path` to skip."""
    return run.park_path is not None and story_frame(run.park_path) is not None


def _has_epic_frame(run: Run, _row: StepRun | None, _signal: Signal) -> bool:
    """`skip_epic` needs an `epics[n]` frame — or a Run that is itself one epic."""
    if run.template_name == EPIC_TEMPLATE:
        return True
    return run.park_path is not None and epic_frame(run.park_path) is not None


def _budget_raised_text(payload: dict[str, Any]) -> str:
    """`budget raised to $60.00`, off the validated figure rather than the payload's string.

    `raised_budget` asserts the payload holds a number, which is safe here for
    `signal_run`'s own reason: the table is validated first and unconditionally, so a
    payload that reaches a gate record has already cleared `_raises_the_budget`.
    """
    return BUDGET_RAISED.format(budget=f"{raised_budget(payload):.2f}")


def _accepted_text(payload: dict[str, Any]) -> str | None:
    """`accepted: tests/api/test_runs.py` for an Accept, `None` for every other `continue`.

    One kind, two sentences: AD-13 gives `continue` three park kinds, and only the
    `protected_path` one carries files. `None` is what falls the record back to
    "continued by the operator" for the other two, which is what they still mean.
    """
    files = accepted_files(payload)
    if not files:
        return None
    return ACCEPTED.format(paths=ACCEPTED_SEPARATOR.join(files))


def _is_saved(run: Run, _row: StepRun | None, _signal: Signal) -> bool:
    """The run has not been enqueued yet — `engine_ref` is the empty dict (AD-6, story 5-3)."""
    return not run.engine_ref


def _no_terminal_session(run: Run, _row: StepRun | None, _signal: Signal) -> bool:
    return not run.terminal_session


def _in_terminal_session(run: Run, _row: StepRun | None, _signal: Signal) -> bool:
    return run.terminal_session


def raised_budget(payload: dict[str, Any]) -> Decimal:
    """The validated `budget_usd` of a `budget_raise`.

    Asserted rather than re-checked: `validate` refuses a `budget_raise` whose payload
    carries no number at all, so a `None` here would be a caller that skipped validation —
    the same invariant `create_run` states about its own plan.
    """
    budget = _raised_budget(payload)
    assert budget is not None
    return budget


def accepted_files(payload: dict[str, Any]) -> tuple[str, ...]:
    """The files a `continue` on a `protected_path` park accepted, in the order they came.

    A payload that is not a sequence of files accepts none: a bare string would otherwise
    be spread one character per "file" into `run.accepted_paths`, and anything else would
    raise where the table describes no outcome.
    """
    supplied = payload.get(FILES_KEY)
    if not isinstance(supplied, list | tuple):
        return ()
    return tuple(str(entry) for entry in supplied)


#: AD-13's table. Every `Signal.kind` there is has exactly one row here.
#: The order matches `SIGNAL_KINDS` in `domain/statuses.py` exactly; both are tested
#: against each other in `test_signal_rules.py` and `test_signals_table.py`.
VALID: dict[SignalKind, Rule] = {
    "answer": Rule(
        park_kinds=frozenset({"blocked", "checkpoint"}),
        row_kinds=frozenset({"agent"}),
        run_event="answer",
        text="answer from the operator",
        text_key=ANSWER_KEY,
    ),
    "continue": Rule(
        park_kinds=frozenset({"checkpoint", "protected_path", "plan_stale"}),
        run_event="continue",
        text="continued by the operator",
        text_from=_accepted_text,
    ),
    "retry": Rule(
        park_kinds=frozenset(
            {
                "timeout",
                "push_rejected",
                "misconfigured",
                "internal",
                "verify_failed",
                "protected_path",
            }
        ),
        run_event="retry",
        text="retried by the operator",
    ),
    "skip_story": Rule(
        park_kinds=ANY_PARK - frozenset({"budget", "plan_stale", "push_rejected"}),
        extra=_has_story_frame,
        run_event="skip_story",
        text="story skipped by the operator",
    ),
    "skip_epic": Rule(
        park_kinds=ANY_PARK - frozenset({"budget", "plan_stale"}),
        extra=_has_epic_frame,
        run_event="skip_epic",
        text="epic skipped by the operator",
    ),
    "budget_raise": Rule(
        park_kinds=frozenset({"budget"}),
        extra=_raises_the_budget,
        extra_refusal=BUDGET_TOO_LOW,
        run_event="budget_raise",
        text="budget raised by the operator",
        text_from=_budget_raised_text,
    ),
    "cancel": Rule(
        park_kinds=ANY_PARK,
        run_statuses=NON_TERMINAL,
        run_event="cancel",
        text="cancelled by the operator",
    ),
    "terminal_start": Rule(
        park_kinds=ANY_PARK,
        extra=_no_terminal_session,
        text="terminal session started",
        operator_action=False,
    ),
    "terminal_release": Rule(
        park_kinds=ANY_PARK,
        run_statuses=NON_TERMINAL,
        extra=_in_terminal_session,
        text="terminal session released",
        operator_action=False,
    ),
    "terminal_resume": Rule(
        park_kinds=frozenset({"blocked"}),
        row_statuses=frozenset({"blocked"}),
        extra=_in_terminal_session,
        run_event="terminal_resume",
        actor="terminal",
        # the brief's own sentence (6.7, FR-21), and it states the *evidence* rather than
        # the act: `terminal_poll` is this kind's only sender, and what a person reads two
        # days later wants to say why the Run started again, not merely that it did
        text=TERMINAL_RESUMED,
        operator_action=False,
    ),
    # story 5-3: start a saved Run (engine_ref={}) on Operator request. operator_action=True
    # because it is the Operator who pushes Start; run_event=None because the status stays
    # "queued" until `_start_saved_run` calls engine.enqueue and writes engine_ref.
    "start": Rule(
        park_kinds=frozenset(),
        run_statuses=frozenset({"queued"}),
        run_event=None,
        extra=_is_saved,
        extra_refusal="run is already enqueued",
        operator_action=True,
        text="",
    ),
}

#: The refusal sentence, verbatim from the brief.
INVALID = "signal {kind} invalid for status {status} / park {park}"
