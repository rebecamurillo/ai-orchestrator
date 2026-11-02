"""Reading why an `agent` attempt failed, for `agent_tail._route` (CAP-5).

The classification is `rules/provider_failure.py`'s; this module only decides when to ask
and where to look.

**An attempt that exited cleanly is never read**, so a `done` Story file with exit 0 and an
agent that wrote about rate limits cost nothing here. The log is read through the `LogReader`
port, its last lines only, and only when the result object named nothing.
"""

from __future__ import annotations

from orchestrator.application.rules import provider_failure
from orchestrator.application.steps.context import StepContext
from orchestrator.domain.ports.harness import HarnessResult


def provider_reason(ctx: StepContext, result: HarnessResult) -> str | None:
    """The `provider error: …` sentence for a failed attempt, or `None` for any other."""
    if not result.exit_code:
        return None
    found = provider_failure.from_raw(result.raw_result)
    if found is not None or ctx.ports.logs is None:
        return found
    tail = ctx.ports.logs.tail(str(result.log_path), provider_failure.LOG_LINES)
    return provider_failure.from_log(tail)
