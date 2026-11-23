"""The round and the first turn of a conversation step (AD-15 amended; owner B8, 2026-11-22).

Pure: both read the Run's inputs and the planned rows, nothing else.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.domain.entities.step_run import StepRun

STEP_KEY = "step"
ROUND_STEPS_INPUT = "round_steps"
FIRST_TURN_INPUT = "first_turn"
PROMPTS_KEY = "prompts"
OPEN_KEY = "open"


def round_list(inputs: Mapping[str, Any]) -> tuple[str, ...]:
    """The step names of the round, in the order written; empty when every step runs."""
    raw = str(inputs.get(ROUND_STEPS_INPUT) or "")
    return tuple(name for name in (part.strip() for part in raw.split(",")) if name)


def _step_of(row: StepRun) -> str:
    return str(row.with_resolved.get(STEP_KEY) or "")


def round_skips(row: StepRun, inputs: Mapping[str, Any]) -> bool:
    """A non-empty round leaves out every conversation step it does not name."""
    names = round_list(inputs)
    return bool(names) and _step_of(row) not in names


def round_names_no_step(rows: Sequence[StepRun], inputs: Mapping[str, Any]) -> bool:
    """A non-empty round that matches no conversation row of the plan."""
    names = round_list(inputs)
    steps = {_step_of(row) for row in rows if row.kind == CONVERSATION_KIND}
    return bool(names) and not steps.intersection(names)


def first_turn(row: StepRun, rows: Sequence[StepRun], inputs: Mapping[str, Any]) -> str:
    """The Run's `first_turn` where it applies to this row, else the row's `prompts.open`."""
    text = str(inputs.get(FIRST_TURN_INPUT) or "")
    if text.strip() and _takes_first_turn(row, rows, inputs):
        return text
    prompts = row.with_resolved.get(PROMPTS_KEY) or {}
    return str(prompts.get(OPEN_KEY) or "")


def _takes_first_turn(row: StepRun, rows: Sequence[StepRun], inputs: Mapping[str, Any]) -> bool:
    names = round_list(inputs)
    if names:
        return _step_of(row) in names
    first = min((entry.seq for entry in rows if entry.kind == CONVERSATION_KIND), default=None)
    return row.seq == first
