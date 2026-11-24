"""The tools that prepare a Project's build Run (story 1 of epic 6)."""

from __future__ import annotations

from typing import Any

from orchestrator.infrastructure.mcp import tools
from orchestrator.infrastructure.mcp.client import InProcessApi


def package_tools(api: InProcessApi) -> list[tools.Tool]:
    """What sets a Project's run defaults."""

    async def set_run_defaults(project_id: str, body: dict[str, Any]) -> Any:
        """Set the defaults a Project's build Run starts with.

        The body is `{default_budget_usd, default_harness, default_model, default_autonomy,
        default_senior_model}`: the five keys are replaced together, an omitted key is refused and
        `null` clears one. `default_autonomy` is `auto` or `checkpoints`. Never invent a budget:
        leave it `null` unless the operator stated one.
        """
        pid = tools._path_id("project_id", project_id)
        return await api.put(f"/projects/{pid}/run-defaults", body)

    return [set_run_defaults]
