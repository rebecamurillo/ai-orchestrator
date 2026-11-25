"""The end of a merge-conflict step session when the stop is answered (story 8.4, AD-23).

`continue` and `retry` on an initiative Run's `merge_conflict` stop resume the `git.merge`
row; the senior lock would refuse them while the session is open, so each first ends it, once
no turn is pending.
"""

from __future__ import annotations

from orchestrator.application.rules import session
from orchestrator.application.rules.signals import VALID
from orchestrator.application.use_cases.signal_effects import TURN_RUNNING
from orchestrator.application.use_cases.writers import (
    Entry,
    WriterPorts,
    record,
    require_run,
    set_run,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict
from orchestrator.domain.statuses import Actor
from orchestrator.domain.values import Signal

RESUMING: frozenset[str] = frozenset({"continue", "retry"})


def end_for_resume(
    writers: WriterPorts, run: Run, park_row: StepRun | None, signal: Signal, actor: Actor
) -> Run:
    """The Run with its session ended by `actor`, or `run` itself when none applies."""
    if not (session.merge_session(run) and run.senior_session and signal.kind in RESUMING):
        return run
    if park_row is not None:
        attempts = writers.attempts.list_for_row(park_row.id)
        turns = session.session_attempts(attempts, writers.records.list_for_run(run.id))
        if session.turn_open(turns):
            raise Conflict(TURN_RUNNING)
    entry = Entry(
        event="session_end",
        actor=actor,
        path=run.park_path,
        text=VALID["session_end"].text,
    )
    record(writers, run, entry)
    set_run(writers, run, senior_session=False)
    return require_run(writers, run.id)
