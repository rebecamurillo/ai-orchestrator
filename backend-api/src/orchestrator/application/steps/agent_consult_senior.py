"""The senior's own process in a consult attempt (AD-10, AD-11, AD-14, AD-22): started in a
**new** session that is never resumed, its `pgid` committed before it is awaited, then the
finish and the spend recorded, all inside the attempt span. Split out of `agent_consult.py`
at the 400-line cap; what the senior's exit and decision come to stays there.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.application.steps import agent_env, agent_tail
from orchestrator.application.steps.context import (
    StepContext,
    committed,
    log_path,
    require_process,
    require_run,
)
from orchestrator.application.templates.rows import STALL_KEY
from orchestrator.application.use_cases.spend import record_attempt_spend
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import Harness, HarnessResult

#: The stall limit when the row declared none — the `agent` kind's own default (FR-10).
DEFAULT_STALL_MIN = 30


@dataclass(frozen=True)
class Senior:
    """One senior dispatch, decided before the span opens: the calls share these facts."""

    harness: Harness
    started: Attempt
    prompt: str
    tree: Path
    block: Mapping[str, Any]


def dispatch(ctx: StepContext, senior: Senior) -> tuple[HarnessResult, Run | None]:
    """The senior's process inside the attempt's span; an unwired tracer degrades to `""`."""
    tracer = ctx.ports.tracer
    if tracer is None:
        return _run(ctx, senior, "")
    with tracer.attempt_span(require_run(ctx), ctx.row, senior.started) as span:
        return _run(ctx, senior, span.traceparent)


def _run(ctx: StepContext, senior: Senior, traceparent: str) -> tuple[HarnessResult, Run | None]:
    """Start, commit the group, wait, record the finish and the spend (AD-8, AD-11, AD-14)."""
    handle = senior.harness.start(
        cwd=senior.tree,
        prompt=senior.prompt,
        env=agent_env.environment(ctx, senior.started, traceparent),
        model=senior.started.model,
        session_id=str(new_id()),
        budget_usd_remaining=agent_env.remaining(require_run(ctx)),
        timeout_min=senior.block.get("timeout_min"),
        log_path=log_path(ctx),
        stall_min=stall_min(ctx),
        add_dirs=agent_env.add_dirs(ctx, senior.tree),
    )
    running = senior.started.model_copy(
        update={"pgid": handle.pgid, "session_id": handle.session_id}
    )
    try:
        committed(ctx, lambda attempts: attempts.update(running))
    except BaseException:
        require_process(ctx).kill_group(handle.pgid)
        raise
    result = senior.harness.wait(handle)
    finished = running.model_copy(
        update={
            "ended_at": ctx.ports.clock.now(),
            "exit_code": result.exit_code,
            "session_id": result.session_id,
            "log_path": str(result.log_path),
            **agent_tail.usage(result),
        }
    )
    committed(ctx, lambda attempts: attempts.mark_finished(finished))
    agent_tail.record_facts(ctx, finished)
    if ctx.ports.spend_writes is None:
        return result, None
    with ctx.ports.spend_writes() as spend_ports:
        return result, record_attempt_spend(spend_ports, require_run(ctx), finished, result.usage)


def stall_min(ctx: StepContext) -> Any:
    """The row's stall limit in minutes, or the kind's default."""
    return ctx.with_resolved.get(STALL_KEY, DEFAULT_STALL_MIN)
