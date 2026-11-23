"""What `step_close` does to the rows (AD-13 amended, 2026-11-22)."""

from __future__ import annotations

from collections.abc import Sequence

from orchestrator.application.rules.signals_conversation import (
    SKIPPED_FORCED,
    is_forced,
)
from orchestrator.application.use_cases.signal_effect import Effect
from orchestrator.application.use_cases.writers import WriterPorts, set_row
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import step_transition
from orchestrator.domain.values import Signal

__all__ = ["SKIPPED_FORCED", "is_forced", "step_close"]


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
