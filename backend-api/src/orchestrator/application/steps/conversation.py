"""The `conversation` kind: a step the Operator talks through with the agent a package names.

First execute only: the row parks the Run `conversation`, or ends itself outside the round
(AD-15 amended "The round"). The `step_close` resumed execute is epic 5's.
"""

from __future__ import annotations

from orchestrator.application.rules.conversation import (
    ROUND_STEPS_INPUT,
    STEP_KEY,
    round_names_no_step,
    round_skips,
)
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.steps.context import StepContext, require_env
from orchestrator.application.steps.registry import register
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Park, StepResult

KIND = CONVERSATION_KIND

PARK_KIND: ParkKind = "conversation"

NOT_IN_ROUND = "not in this round"


class ConversationExecutor:
    """Park on the conversation, skip outside the round, or refuse a round naming no step."""

    def execute(self, ctx: StepContext) -> StepResult:
        row = ctx.row
        env = require_env(ctx)
        inputs = env.run.inputs if env.run else {}
        reason = f"conversation · {ctx.with_resolved.get(STEP_KEY)}"
        park = Park(kind=PARK_KIND, reason=reason, path=row.path)
        if ctx.resume_signal is not None:
            return StepResult(status="checkpoint", gate=row.gate, reason=reason, park=park)
        if round_names_no_step(env.plan_rows, inputs):
            why = f"{ROUND_STEPS_INPUT} {inputs.get(ROUND_STEPS_INPUT)} names no conversation step"
            stop = Park(kind="misconfigured", reason=why, path=row.path)
            return StepResult(status="error", gate=row.gate, reason=why, park=stop)
        if round_skips(row, inputs):
            return StepResult(status="skipped", gate=row.gate, reason=NOT_IN_ROUND)
        return StepResult(status="checkpoint", gate=row.gate, reason=reason, park=park)


register(KIND, ConversationExecutor())
