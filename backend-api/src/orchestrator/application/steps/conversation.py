"""The `conversation` kind: a step the Operator talks through with the agent a package names.

First execute: the row parks the Run `conversation`, or ends itself outside the round
(AD-15 amended "The round"). Resumed on `step_close`, or on the `continue` after its own
`protected_path` park, it runs the close check (AD-17 amended, R1), then routes the row's step
file (AD-38 "Resumed execute"): `done` ends the row, anything else parks the conversation again.
"""

from __future__ import annotations

from collections.abc import Mapping

from orchestrator.application.rules import protected_paths, routing, session
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
    require_workspace,
)
from orchestrator.application.steps.registry import register
from orchestrator.application.story_file import StoryFile, parse
from orchestrator.application.use_cases.conversation_close import close_hits
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Park, StepResult

KIND = CONVERSATION_KIND

PARK_KIND: ParkKind = "conversation"

NOT_IN_ROUND = "not in this round"

#: The resume records that end the conversation: her word, and her `continue` past a park.
CLOSE_EVENTS = ("step_close", "continue")

NOT_CLOSED_STATUS = (
    "step not closed · {file} has status {word}, the done content is status {done}"
    " · the step stays open"
)
NOT_CLOSED_NO_STATUS = (
    "step not closed · {file} has no status, the done content is status {done}"
    " · the step stays open"
)
NOT_CLOSED_MISSING = (
    "step not closed · {file} is missing, the done content is status {done} · the step stays open"
)
DONE_SEPARATOR = " or "


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
        return _route_step_file(ctx)
    reason = git_commit.PROTECTED.format(paths=git_commit.PATH_SEPARATOR.join(hits))
    park = Park(kind="protected_path", reason=reason, path=row.path)
    return StepResult(
        status="error",
        gate=row.gate,
        reason=reason,
        park=park,
        payload=protected_paths.hits_payload(hits),
    )


def _route_step_file(ctx: StepContext) -> StepResult:
    row = ctx.row
    expect = ctx.with_resolved.get("expect")
    declared = expect if isinstance(expect, Mapping) else {}
    files = [str(p) for p in declared.get("files") or ()]
    path = files[0] if files else ""
    text = require_workspace(ctx, ctx.cwd).read(path) if path else None
    story = parse(path, text) if text is not None else None
    contract = routing.RouteContract(
        success=tuple(str(w) for w in declared.get("success") or ()),
        blocked=tuple(str(w) for w in declared.get("blocked") or ()),
    )
    routed = routing.route(
        story,
        (path,) if text is not None else (),
        0,
        False,
        0,
        None,
        contract=contract,
        gate=row.gate,
        path=row.path,
    )
    if routed.status == "done":
        return StepResult(status="done", gate=row.gate)
    reason = _not_closed(path, text, story, contract.success)
    park = Park(kind=PARK_KIND, reason=reason, path=row.path)
    return StepResult(status="checkpoint", gate=row.gate, reason=reason, park=park)


def _not_closed(
    path: str, text: str | None, story: StoryFile | None, success: tuple[str, ...]
) -> str:
    done = DONE_SEPARATOR.join(success)
    if text is None:
        return NOT_CLOSED_MISSING.format(file=path, done=done)
    if story is None:
        return NOT_CLOSED_NO_STATUS.format(file=path, done=done)
    return NOT_CLOSED_STATUS.format(file=path, word=story.status, done=done)


register(KIND, ConversationExecutor())
