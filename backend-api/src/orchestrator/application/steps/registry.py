"""The executor registry: the one place a `kind` becomes behaviour (AD-9).

`KIND_META` says what a kind *is*; this table says what runs it. They are separate because
they are populated at different times: every kind has metadata from the moment the planner
can expand it, while an executor arrives with the story that implements the kind. 4.7 lands
`plan.check`, `shell` and `checkpoint`, 4.8 the six git kinds, Epic 5 the `agent` — each by
calling `register` beside its module and adding nothing to the walker.

`execute` is the whole seam the walker dispatches through, and it never raises:

- **A kind with no executor is a park, not a skip.** `misconfigured · no executor for kind
  {kind}` stops the Run for the Operator with the reason written on it. The alternative —
  treating the row as done, or letting the walker's step raise — would either advance a Run
  that ran nothing or leave a Run `queued` with a dead workflow behind it and no reason
  anywhere. Until 4.7 lands the first executor this is what every row does, which is why it
  is a described outcome with a test rather than an assertion that cannot fire.
- **A result that reports no completion is refused the same way.** `planned`, `queued` and
  `running` are not outcomes a row can end in; `apply_step_result` would raise on one, inside
  a durable step, leaving the Run `running` with nothing recorded. `misreported {status}` is
  the park instead.
- **Every exception an executor raises becomes `internal · internal: {ExceptionClass}`.**
  The class name and nothing else: an exception message can carry a path, a command line or
  a token, and this string is written to `run.park_reason` and shown on the Run detail
  (AD-5). The traceback goes to the log, where the Operator's own `docker compose logs`
  finds it.

Both refusals report `error` with the row's own gate, because the gate is what the planner
recorded before the Run started (AD-7) and a failure does not re-decide it.
"""

from __future__ import annotations

import structlog

from orchestrator.application.steps.context import StepContext, StepExecutor
from orchestrator.domain.statuses import ParkKind
from orchestrator.domain.values import Park, StepResult

log = structlog.get_logger(__name__)

#: The park a row whose kind nothing implements stops the Run with.
NO_EXECUTOR = "no executor for kind {kind}"

#: The park an executor that raised stops the Run with — the class, never the message.
INTERNAL = "internal: {name}"

#: The park a result reporting a status no row can end in stops the Run with.
MISREPORTED = "misreported {status}"

#: The statuses a row can end an execution in. The rest are not completions at all.
COMPLETIONS: frozenset[str] = frozenset({"done", "blocked", "checkpoint", "error", "skipped"})

#: What the log line an executor's exception leaves is called.
EXECUTOR_RAISED = "executor raised"

#: One executor per kind. Empty until 4.7: `register` is how a kind fills its row.
EXECUTORS: dict[str, StepExecutor] = {}


def register(kind: str, executor: StepExecutor) -> None:
    """Bind one kind to the executor that runs it. A kind is registered once."""
    if kind in EXECUTORS:
        raise ValueError(f"{kind} already has an executor")
    EXECUTORS[kind] = executor


def executor_for(kind: str) -> StepExecutor | None:
    """The executor registered for this kind, or `None` — the honest answer, not a stub."""
    return EXECUTORS.get(kind)


def execute(ctx: StepContext) -> StepResult:
    """Run one row through its kind's executor, reporting every failure as a result."""
    executor = executor_for(ctx.row.kind)
    if executor is None:
        return _refused(ctx, "misconfigured", NO_EXECUTOR.format(kind=ctx.row.kind))
    try:
        result = executor.execute(ctx)
    except Exception as error:
        log.exception(EXECUTOR_RAISED, path=ctx.row.path, kind=ctx.row.kind)
        return _refused(ctx, "internal", INTERNAL.format(name=type(error).__name__))
    if result.status not in COMPLETIONS:
        return _refused(ctx, "internal", MISREPORTED.format(status=result.status))
    return result


def _refused(ctx: StepContext, kind: ParkKind, reason: str) -> StepResult:
    """One shape for both refusals: the row errored, and the Run stops on this reason."""
    return StepResult(
        status="error",
        gate=ctx.row.gate,
        reason=reason,
        park=Park(kind=kind, reason=reason, path=ctx.row.path),
    )
