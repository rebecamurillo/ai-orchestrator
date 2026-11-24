"""The tools that prepare a Project's build Run: run defaults and initiative folder."""

from __future__ import annotations

from typing import Any

from orchestrator.infrastructure.mcp import tools
from orchestrator.infrastructure.mcp.client import InProcessApi


def package_tools(api: InProcessApi) -> list[tools.Tool]:
    """What sets a Project's run defaults and a Repository's initiative folder."""

    async def set_run_defaults(project_id: str, body: dict[str, Any]) -> Any:
        """Set the defaults a Project's build Run starts with.

        The body is `{default_budget_usd, default_harness, default_model, default_autonomy,
        default_senior_model}`: the five keys are replaced together, an omitted key is refused and
        `null` clears one. `default_autonomy` is `auto` or `checkpoints`. Never invent a budget:
        leave it `null` unless the operator stated one.
        """
        pid = tools._path_id("project_id", project_id)
        return await api.put(f"/projects/{pid}/run-defaults", body)

    async def set_initiative_folder(repository_id: str, body: dict[str, Any]) -> Any:
        """Set the folder where every initiative of a Repository lives.

        The body is `{initiative_folder}`: one or more `[A-Za-z0-9._-]` segments joined by `/`, with
        no `.` or `..` segment and no leading or trailing `/`. A Run's `initiative_folder` must
        equal it or lie under it, and an omitted one is bound to it.
        """
        rid = tools._path_id("repository_id", repository_id)
        return await api.put(f"/repositories/{rid}/initiative-folder", body)

    return [set_run_defaults, set_initiative_folder]
