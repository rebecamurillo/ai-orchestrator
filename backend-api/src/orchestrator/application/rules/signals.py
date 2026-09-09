"""The questions asked of AD-13's signal table: is this signal admitted here, what does this
stop offer, and what does its gate record say.

The table itself — `Rule`, its predicates, its text builders, `VALID`, `INVALID` and the two
payload readers — is `rules/signals_table.py`, split out on line count alone when 6.7 added
the terminal narrowing below to a module already at 397 of its 400 lines. Every public name
of that module is re-exported here, so `apply_step_result.py`'s `REBASELINE_FAILED`,
`signal_run.py`'s `Rule`, `signal_effects.py`'s `signals.accepted_files` and every other
existing import of this module resolves exactly as it did.

`admitted_signals(park_kind, row_kind)` is the table read the other way: the set of actions a
stop offers, which is PRD §4.6's *Signals admitted* column and what the Run detail renders.
It answers from the park kind and the parked row's kind alone — see `signals_table.py`'s own
docstring for the two rules of the table that are written in a form that question can answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from orchestrator.application.rules.signals_table import (
    ACCEPTED,
    ACCEPTED_SEPARATOR,
    ANSWER_KEY,
    ANY_PARK,
    BUDGET_KEY,
    BUDGET_RAISED,
    BUDGET_TOO_LOW,
    FILES_KEY,
    INVALID,
    NON_TERMINAL,
    PARKED,
    REBASELINE_FAILED,
    TERMINAL_RESUMED,
    VALID,
    Rule,
    accepted_files,
    raised_budget,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict
from orchestrator.domain.statuses import TERMINAL_RUN, ParkKind, SignalKind
from orchestrator.domain.values import Signal

__all__ = [
    "ACCEPTED",
    "ACCEPTED_SEPARATOR",
    "ANSWER_KEY",
    "ANY_PARK",
    "BUDGET_KEY",
    "BUDGET_RAISED",
    "BUDGET_TOO_LOW",
    "FILES_KEY",
    "INVALID",
    "NON_TERMINAL",
    "PARKED",
    "REBASELINE_FAILED",
    "TERMINAL_RESUMED",
    "TERMINAL_SESSION_SIGNALS",
    "VALID",
    "Rule",
    "accepted_files",
    "admitted_signals",
    "raised_budget",
    "record_text",
    "row_at",
    "run_admitted_signals",
    "validate",
]

#: What a Run with a terminal session in progress offers instead of its stop's own actions
#: (FR-21, 6.7): the two the brief keeps, in `VALID`'s own order. `terminal_release` cannot
#: come out of `admitted_signals` — its `Rule.operator_action` is `False`, and flipping that
#: would offer a Release on every stop, session or no session — so it is named here, where
#: the Run's own `terminal_session` is what makes it true.
TERMINAL_SESSION_SIGNALS: tuple[SignalKind, ...] = ("cancel", "terminal_release")


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
        raise _refuse_extra(run, rule, signal)
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

    **A terminal session replaces the whole set** (6.7, FR-21). While `run.terminal_session`
    is true the Operator is working in the agent's own session in a terminal, and every
    action that would move the same row from here — Answer, Continue, Skip story, Skip epic,
    Retry — is dropped; `cancel` and `terminal_release` are what is left. It is read before
    the status tests below rather than after them, so the answer does not depend on which
    status a Run happens to be in while the flag is set.
    """
    if run.status in TERMINAL_RUN:
        return ()
    if run.terminal_session:
        return TERMINAL_SESSION_SIGNALS
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
    if rule.text_from is not None:
        built = rule.text_from(payload)
        if built:
            return built
    if rule.text_key is not None:
        supplied = payload.get(rule.text_key)
        if supplied:
            return str(supplied)
    return rule.text


def _refuse(run: Run, signal: Signal) -> Conflict:
    return Conflict(INVALID.format(kind=signal.kind, status=run.status, park=run.park_kind))


def _refuse_extra(run: Run, rule: Rule, signal: Signal) -> Conflict:
    """What `extra` refusing means: the table's own sentence where it has one, else `INVALID`.

    Only reached once every column has already matched, so a `budget_raise` on a `timeout`
    park still gets `INVALID` — there it is the park that is wrong, not the figure.
    """
    if rule.extra_refusal is None:
        return _refuse(run, signal)
    return Conflict(rule.extra_refusal.format(spend=f"{run.spend_usd:.2f}"))
