"""What one dispatch hands its harness process, for the agent and the senior alike (AD-5,
AD-10, AD-11): the environment `HarnessEnv` builds, the budget still left, and the extra
directory a dispatch standing in a submodule must reach."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from orchestrator.application.steps.context import (
    StepContext,
    require_cwd,
    require_env,
    require_harness_env,
    require_run,
    resolved_text,
)
from orchestrator.application.templates.agent_row import STORY_ID_KEY
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run


def environment(ctx: StepContext, attempt: Attempt, traceparent: str) -> dict[str, str]:
    """Exactly what `HarnessEnv` builds for this attempt (AD-5, AD-10)."""
    run_env = require_env(ctx)
    return require_harness_env(ctx)(
        attempt,
        run=require_run(ctx),
        project_slug=run_env.project_slug,
        project_env=run_env.project.env_vars,
        log_content=run_env.project.log_prompt_content,
        story_id=resolved_text(ctx.with_resolved, STORY_ID_KEY) or None,
        traceparent=traceparent,
    )


def remaining(run: Run) -> Decimal | None:
    """What the Run may still spend, or `None` when it has no budget (FR-17)."""
    return run.budget_usd - run.spend_usd if run.budget_usd is not None else None


def add_dirs(ctx: StepContext, dispatch_cwd: Path) -> tuple[Path, ...]:
    """The hub root for a dispatch standing in a submodule: the specs and `git -C` live there."""
    root = require_cwd(ctx)
    return () if dispatch_cwd == root else (root,)
