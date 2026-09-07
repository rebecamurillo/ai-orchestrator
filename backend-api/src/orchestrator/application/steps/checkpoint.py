"""The `checkpoint` kind: a declared stop for the Operator, and nothing else (AD-9).

There is exactly one thing to decide here, and the row itself already decided it: `label`
is `{...} · done checkpoint` for a `pause_after_item_when` and `{...} · before` for a
`pause_before_item_when` (`application/templates/rows.py::checkpoint_row`), so the reason
the Operator reads is the row's own last label segment — never recomputed, never a second
copy of what `AFTER_LABEL` already says.

This executor is never asked to resume one. AD-13's `continue` on a `checkpoint` row is
`checkpoint -> done` written by `signal_run` itself (`use_cases/signal_effects.py::_continue`),
before the walker ever re-queues the row; `skip_story` and `skip_epic` move it to `skipped`
the same way. By the time `execute` would run again, the row is already finished.
"""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext
from orchestrator.application.steps.registry import register
from orchestrator.application.templates.plan_model import LABEL_SEPARATOR
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Park, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "checkpoint"

#: What a `checkpoint` row always parks the Run with.
PARK_KIND: ParkKind = "checkpoint"


class CheckpointExecutor:
    """First execution only: park the Run, with the row's own label as the reason."""

    def execute(self, ctx: StepContext) -> StepResult:
        reason = ctx.row.label.rsplit(LABEL_SEPARATOR, 1)[-1]
        return StepResult(
            status="checkpoint",
            gate=ctx.row.gate,
            reason=reason,
            park=Park(kind=PARK_KIND, reason=reason, path=ctx.row.path),
        )


register(KIND, CheckpointExecutor())
