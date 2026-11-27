"""What `step_close` does to the rows (AD-13 amended, 2026-11-22)."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from orchestrator.application.rules import session
from orchestrator.application.rules.signals_conversation import (
    CONVERSATION,
    SKIPPED_FORCED,
    is_forced,
)
from orchestrator.application.use_cases.signal_effect import CancelPlan, Effect, EffectFn
from orchestrator.application.use_cases.writers import WriterPorts, set_row
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import step_transition
from orchestrator.domain.values import Signal

__all__ = [
    "CANCELLED_TURN",
    "SKIPPED_FORCED",
    "SKIPPED_TURN",
    "closing_turns",
    "is_forced",
    "step_close",
]

SKIPPED_TURN = "step skipped"
CANCELLED_TURN = "Run cancelled"


def step_close(
    ports: WriterPorts,
    _run: Run,
    _rows: Sequence[StepRun],
    park_row: StepRun | None,
    _signal: Signal,
) -> Effect:
    """The conversation row goes `checkpoint → queued`; its next execute is a resumed one."""
    assert park_row is not None
    set_row(ports, park_row, status=step_transition(park_row.status, "continue"))
    return Effect(run_update={"senior_session": False})


def closing_turns(effect: EffectFn, reason: str) -> EffectFn:
    """`effect`, and while a conversation session is open also what stops it: the running
    turn's process group joins the caller's kill, queued turns close `error` with `reason`
    (their messages stay), and the Run's `senior_session` clears (AD-23 amended)."""

    def closing(
        ports: WriterPorts,
        run: Run,
        rows: Sequence[StepRun],
        park_row: StepRun | None,
        signal: Signal,
    ) -> Effect:
        done = effect(ports, run, rows, park_row, signal)
        if run.park_kind != CONVERSATION or not run.senior_session or park_row is None:
            return done
        turns = [
            attempt
            for attempt in ports.attempts.list_for_row(park_row.id)
            if attempt.role == session.SESSION_ROLE
        ]
        known = done.cancel_plan.pgids if done.cancel_plan is not None else ()
        pgids = known + tuple(
            dict.fromkeys(
                turn.pgid
                for turn in turns
                if turn.status == "running"
                and turn.ended_at is None
                and turn.pgid is not None
                and turn.pgid not in known
            )
        )
        for turn in turns:
            if turn.status == "queued":
                closed = {"status": "error", "ended_at": ports.clock.now(), "output_ref": reason}
                ports.attempts.mark_finished(turn.model_copy(update=closed))
        worktrees = done.cancel_plan.worktrees if done.cancel_plan is not None else ()
        return dataclasses.replace(
            done,
            run_update={**done.run_update, "senior_session": False},
            cancel_plan=CancelPlan(pgids=pgids, worktrees=worktrees),
        )

    return closing
