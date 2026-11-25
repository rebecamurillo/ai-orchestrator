"""What a conversation stop and the interactive gate admit (AD-13 amended, 2026-11-22).

Pure predicates and one `Rule` for `signals_table`, kept apart from it because that module
sits at its line cap and imports this one: nothing here may import `signals_table`. Nor
`rules/lane.py`, which `use_cases/announce.py` cannot reach without an import cycle, so the
conversation row kind is spelled by the park kind's own string.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from orchestrator.application.rules.signal_rule import Rule
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Signal

CONVERSATION: ParkKind = "conversation"
MERGE_CONFLICT: ParkKind = "merge_conflict"

#: The row role of the spec workflow's gate.
SPEC_GATE_ROLE = "spec-gate"

#: The payload key a deliberate skip of a conversation stop carries.
FORCED_KEY = "forced"

#: The reason and gate-record text of a forced skip.
SKIPPED_FORCED = "skipped, forced"

#: What a `step_close` that names no stop is refused with.
STEP_CLOSE_REFUSAL = "step_close needs the stop it answers"

SkipPredicate = Callable[[Run, StepRun | None, Signal, Sequence[StepRun]], bool]


def is_forced(signal: Signal) -> bool:
    """True only for a literal `forced: true`; `"true"` or `1` is not a deliberate force."""
    return signal.payload.get(FORCED_KEY) is True


def gate_locked(run: Run, row: StepRun | None) -> bool:
    """An interactive Run's `spec-gate` row is never skipped; a `walk` Run's keeps its skips."""
    return run.lane == "interactive" and row is not None and row.role == SPEC_GATE_ROLE


def skip_step_admitted(
    run: Run, row: StepRun | None, signal: Signal, _rows: Sequence[StepRun]
) -> bool:
    """A conversation stop admits only a forced skip that names its stop."""
    if gate_locked(run, row):
        return False
    if run.park_kind == CONVERSATION:
        return is_forced(signal) and signal.stop is not None
    return True


def no_gate_skip(predicate: SkipPredicate) -> SkipPredicate:
    """Wrap a frame predicate: refused on a locked gate and on a conversation stop."""

    def admitted(run: Run, row: StepRun | None, signal: Signal, rows: Sequence[StepRun]) -> bool:
        if gate_locked(run, row) or run.park_kind == CONVERSATION:
            return False
        return predicate(run, row, signal, rows)

    return admitted


def forced_text(payload: dict[str, Any]) -> str | None:
    """`skipped, forced` for a forced skip, `None` to keep the ordinary sentence."""
    return SKIPPED_FORCED if payload.get(FORCED_KEY) is True else None


def _states_its_stop(
    _run: Run, _row: StepRun | None, signal: Signal, _rows: Sequence[StepRun]
) -> bool:
    return signal.stop is not None


def continue_admitted(
    run: Run, _row: StepRun | None, _signal: Signal, _rows: Sequence[StepRun]
) -> bool:
    """`continue` answers a `merge_conflict` stop only on an initiative Run (story 8.4)."""
    return run.park_kind != MERGE_CONFLICT or run.initiative_id is not None


STEP_CLOSE = Rule(
    park_kinds=frozenset({CONVERSATION}),
    row_kinds=frozenset({CONVERSATION}),
    row_statuses=frozenset({"checkpoint"}),
    extra=_states_its_stop,
    extra_refusal=STEP_CLOSE_REFUSAL,
    run_event="step_close",
    actor="machine",
    text="step closed",
    operator_action=False,
)
