"""`timeout_min` and `stall_min` as a Template writes them: a count, or one `{{ }}`.

The expression is read against the frame's scope when the row is planned, so a Run's own
input can set a limit without a Template per limit. A value nobody bound is the same as a
key nobody wrote: the kind's default applies.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.application.templates.model import Step
from orchestrator.application.templates.plan_model import BAD_MINUTES, PlanError
from orchestrator.application.templates.substitute import resolve
from orchestrator.application.templates.table import MIN_COUNT

#: The keys a row's `with_resolved` carries the limits under. Only agent rows have a stall.
TIMEOUT_KEY = "timeout_min"
STALL_KEY = "stall_min"


def step_limits(step: Step, scope: Mapping[str, Any]) -> dict[str, int]:
    """The limits a row carries; a kind with no default and no declaration writes none."""
    meta = step.meta
    limits = {
        TIMEOUT_KEY: step_minutes(step.timeout_min, meta.timeout_default_min, scope, step),
        STALL_KEY: step_minutes(step.stall_min, meta.stall_default_min, scope, step),
    }
    return {key: value for key, value in limits.items() if value is not None}


def step_minutes(
    declared: int | str | None, default: int | None, scope: Mapping[str, Any], step: Step
) -> int | None:
    """The limit a row carries: the literal, the expression's positive integer, or the default."""
    if declared is None:
        return default
    value = resolve(declared, scope) if isinstance(declared, str) else declared
    if value is None or value == "":
        return default
    count = _count(value)
    if count is None:
        raise PlanError(reason=BAD_MINUTES, line=step.line, item=f"{step.id}: {value!r}")
    return count


def _count(value: Any) -> int | None:
    """A positive integer, or a string of digits holding one; nothing else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        value = int(text) if text.isascii() and text.isdigit() else None
    if isinstance(value, int) and value >= MIN_COUNT:
        return value
    return None
