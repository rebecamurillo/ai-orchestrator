"""AD-13's signal table, as data: what each Signal is admitted on, and what it records.

`signal_run` validates against `VALID` **before** it touches a state machine. That order is
the reason `InvalidTransition` is not a `DomainError` (4.1): an operator sending a signal
the table refuses gets a `Conflict` — 409 with the sentence below — and never reaches a
transition function, so a raised `InvalidTransition` always means a bug rather than a
described outcome.

`admitted_signals(park_kind, row_kind)` is the same table read the other way: the set of
actions a stop offers, which is PRD §4.6's *Signals admitted* column and what the Run detail
will render (Epic 4.15). It answers from the park kind and the parked row's kind alone, so
two rules of the table are written here in a form that question can answer:

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
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from orchestrator.application.rules.frames import EPIC_TEMPLATE, epic_frame, story_frame
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict
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
    #: The Run transition this signal applies, or `None` when the Run's status is unchanged.
    run_event: RunEvent | None = None
    #: Who the gate record names.
    actor: Actor = "operator"
    #: The sentence the gate record carries when the payload supplies none.
    text: str = ""
    #: The payload key whose value is the gate record's text instead of `text`.
    text_key: str | None = None
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


def _no_terminal_session(run: Run, _row: StepRun | None, _signal: Signal) -> bool:
    return not run.terminal_session


def _in_terminal_session(run: Run, _row: StepRun | None, _signal: Signal) -> bool:
    return run.terminal_session


#: AD-13's table. Every `Signal.kind` there is has exactly one row here.
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
        run_event="budget_raise",
        text="budget raised by the operator",
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
        text="resumed from the terminal session",
        operator_action=False,
    ),
}

#: The refusal sentence, verbatim from the brief.
INVALID = "signal {kind} invalid for status {status} / park {park}"


def validate(run: Run, park_row: StepRun | None, signal: Signal) -> Rule:
    """The `Rule` for this signal here, or `Conflict` (409) naming why it does not apply."""
    rule = VALID[signal.kind]
    if run.status not in rule.run_statuses:
        raise _refuse(run, signal)
    if run.status in PARKED and (run.park_kind is None or run.park_kind not in rule.park_kinds):
        raise _refuse(run, signal)
    if rule.row_kinds is not None and (park_row is None or park_row.kind not in rule.row_kinds):
        raise _refuse(run, signal)
    if rule.row_statuses is not None and (
        park_row is None or park_row.status not in rule.row_statuses
    ):
        raise _refuse(run, signal)
    if rule.extra is not None and not rule.extra(run, park_row, signal):
        raise _refuse(run, signal)
    return rule


def admitted_signals(park_kind: ParkKind, row_kind: str) -> tuple[SignalKind, ...]:
    """The operator actions this stop offers — PRD §4.6's *Signals admitted*, in table order.

    The park kind and the parked row's kind are all it reads, so it answers a Run detail
    that has both. `validate` stays the authority: it also checks the frame a skip needs,
    the budget a raise has to exceed and the terminal session, none of which this knows.
    """
    return tuple(
        kind
        for kind, rule in VALID.items()
        if rule.operator_action
        and PARKED <= rule.run_statuses
        and park_kind in rule.park_kinds
        and (rule.row_kinds is None or row_kind in rule.row_kinds)
    )


def row_at(rows: Sequence[StepRun], path: str | None) -> StepRun | None:
    """The row `path` names, or `None` — a Run that is not parked on one names none."""
    return next((row for row in rows if row.path == path), None)


def run_admitted_signals(run: Run, park_row_kind: str | None) -> tuple[SignalKind, ...]:
    """One Run's own *Signals admitted*, for the read model 4.9 adds to `RunSummaryOut`.

    `admitted_signals(park_kind, row_kind)` answers "what does this stop admit"; a Run
    detail asks a wider question — what does *this Run*, right now, offer the Operator —
    which also has to answer for a Run that is not parked at all: `[cancel]` while it runs
    (AD-13: `cancel` applies to every non-terminal status), and nothing once it is terminal.
    `park_row_kind` is the parked row's `kind`, or `None` when the caller has not looked it
    up (`RunSummaryOut`'s list view does not, and answers conservatively without it).

    **One stop is narrower than its park kind** (6.4, FR-20): a `verify_failed` park whose
    reason is `REBASELINE_FAILED` is the re-baseline of a Story the Operator has *already*
    skipped, so it offers Retry, Skip epic and Cancel run — not a second Skip story, which
    would find nothing left to skip and merely re-queue the row Retry re-queues. `validate`
    is deliberately not narrowed with it: AD-13's table is keyed on the park *kind*, and a
    `skip_story` posted here is admissible and harmless. This is what the stop *offers*.
    """
    if run.status in TERMINAL_RUN:
        return ()
    if run.status != "needs_you":
        return ("cancel",)
    if run.park_kind is None:
        return ()
    offered = admitted_signals(run.park_kind, park_row_kind or "")
    if run.park_reason == REBASELINE_FAILED:
        return tuple(kind for kind in offered if kind != "skip_story")
    return offered


def record_text(rule: Rule, payload: dict[str, Any]) -> str:
    """What the gate record says: the payload's own words where it has any, else the phrase."""
    if rule.text_key is not None:
        supplied = payload.get(rule.text_key)
        if supplied:
            return str(supplied)
    return rule.text


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


def _refuse(run: Run, signal: Signal) -> Conflict:
    return Conflict(INVALID.format(kind=signal.kind, status=run.status, park=run.park_kind))
