"""The `agent` kind's *Accept* branch (AD-9, AD-17): the tail re-run over the previous attempt,
dispatching nothing. Split out of `agent_tail.py` at the 400-line cap.

Two records accept a `protected_path` park's files: the Operator's `continue`, and the
senior's `senior_accept` (story 1-8), which `rules/consult.py::delivers` hands only to the
attempt right after the consult, so an acceptance is re-checked once and never again.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.rules.consult import ACCEPT_EVENT
from orchestrator.application.rules.signals import accepted_files
from orchestrator.application.steps import agent_tail
from orchestrator.application.steps.context import StepContext
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import StepResult

#: The records whose files an Accept re-checks the previous attempt with.
ACCEPTING_EVENTS = frozenset({agent_tail.CONTINUE_EVENT, ACCEPT_EVENT})


def re_check(ctx: StepContext) -> StepResult | None:
    """The Accept branch (AD-9): an accepting record carrying files re-runs the tail,
    dispatching nothing. `None` for every other resume, which is the ordinary dispatch.

    The park was answered by accepting the paths, so the work the row was doing is already
    in the worktree — re-dispatching would ask the harness to do it again, and would put a
    WIP commit and a prepare commit in front of a range the check is about to read. What is
    left is the check and the routing, over the *previous* attempt's own two SHAs, with
    `run.accepted_paths` — which `signal_run` or `apply_consult` has already extended —
    excluded.

    The discriminator is `StepContext` alone, as AD-9 requires: the event plus a payload that
    carries files. A `continue` on a `checkpoint` park carries none, and a row whose first
    attempt was resumed has no range to re-read.
    """
    signal, previous = ctx.resume_signal, ctx.previous_attempt
    if signal is None or signal.event not in ACCEPTING_EVENTS or previous is None:
        return None
    if not accepted_files(signal.payload):
        return None
    return agent_tail.tail(ctx, previous, _reported(previous))


def _reported(attempt: Attempt) -> HarnessResult:
    """What the dispatch that parked already reported, rebuilt from its own attempt row.

    The Accept branch runs no harness, and `tail` takes what one returned: the exit code and
    the log are the attempt's columns (AD-8's `mark_finished` wrote them), so the routing
    reads exactly what it read the first time. `usage` is left out on purpose — the spend of
    that dispatch was recorded against that dispatch, and 5.7 must not count it twice.
    """
    return HarnessResult(
        session_id=attempt.session_id or "",
        exit_code=attempt.exit_code,
        log_path=Path(attempt.log_path or ""),
    )
