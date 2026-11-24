"""The `conversation` kind: a step the Operator talks through with the agent a package names.

First execute: the row parks the Run `conversation`, or ends itself outside the round
(AD-15 amended "The round"). Resumed on `step_close`, or on the `continue` after its own
`protected_path` park, it runs the close check (AD-17 amended, R1) and ends `done` or parks again.
"""

from __future__ import annotations

from orchestrator.application.rules import protected_paths, session
from orchestrator.application.rules.conversation import (
    ROUND_STEPS_INPUT,
    STEP_KEY,
    round_names_no_step,
    round_skips,
)
from orchestrator.application.steps import CONVERSATION_KIND, git_commit
from orchestrator.application.steps.context import (
    StepContext,
    require_attempt_writes,
    require_env,
    require_run,
)
from orchestrator.application.steps.registry import register
from orchestrator.application.use_cases.conversation_close import close_hits
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Park, StepResult

KIND = CONVERSATION_KIND

PARK_KIND: ParkKind = "conversation"

NOT_IN_ROUND = "not in this round"

#: The resume records that end the conversation: her word, and her `continue` past a park.
CLOSE_EVENTS = ("step_close", "continue")


class ConversationExecutor:
    """Park on the conversation, skip outside the round, or refuse a round naming no step."""

    def execute(self, ctx: StepContext) -> StepResult:
        row = ctx.row
        env = require_env(ctx)
        inputs = env.run.inputs if env.run else {}
        reason = f"conversation · {ctx.with_resolved.get(STEP_KEY)}"
        park = Park(kind=PARK_KIND, reason=reason, path=row.path)
        if ctx.resume_signal is not None and ctx.resume_signal.event in CLOSE_EVENTS:
            return _close(ctx)
        if ctx.resume_signal is not None:
            return StepResult(status="checkpoint", gate=row.gate, reason=reason, park=park)
        if round_names_no_step(env.plan_rows, inputs):
            why = f"{ROUND_STEPS_INPUT} {inputs.get(ROUND_STEPS_INPUT)} names no conversation step"
            stop = Park(kind="misconfigured", reason=why, path=row.path)
            return StepResult(status="error", gate=row.gate, reason=why, park=stop)
        if round_skips(row, inputs):
            return StepResult(status="skipped", gate=row.gate, reason=NOT_IN_ROUND)
        return StepResult(status="checkpoint", gate=row.gate, reason=reason, park=park)


def _close(ctx: StepContext) -> StepResult:
    row, run, env = ctx.row, require_run(ctx), require_env(ctx)
    with require_attempt_writes(ctx)() as w:
        turns = session.session_attempts(
            w.attempts.list_for_row(row.id), w.records.list_for_run(run.id)
        )
    hits = close_hits(ctx.ports.git, run, env.plan_rows, row, turns)
    if not hits:
        return StepResult(status="done", gate=row.gate)
    reason = git_commit.PROTECTED.format(paths=git_commit.PATH_SEPARATOR.join(hits))
    park = Park(kind="protected_path", reason=reason, path=row.path)
    return StepResult(
        status="error",
        gate=row.gate,
        reason=reason,
        park=park,
        payload=protected_paths.hits_payload(hits),
    )


register(KIND, ConversationExecutor())
