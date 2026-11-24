"""The tools that prepare a Project's build Run: run defaults, initiative folder, package."""

from __future__ import annotations

from typing import Any

from orchestrator.infrastructure.mcp import tools
from orchestrator.infrastructure.mcp.client import InProcessApi


def package_tools(api: InProcessApi) -> list[tools.Tool]:
    """What sets a Project's run defaults, a Repository's initiative folder and a Project's
    package."""

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

    async def install_package(project_id: str, body: dict[str, Any]) -> Any:
        """Install a package on a Project from a branch of its hub repository.

        The body is `{repository_id, path, ref}`: `path` is the package's folder in the hub and
        `ref` a branch. The call reads `package.yaml` and the templates it names at that branch,
        stores them only if every check passes, and otherwise refuses with every error named
        by file and reason. Initiatives already started keep their sequence.
        """
        pid = tools._path_id("project_id", project_id)
        return await api.put(f"/projects/{pid}/package", body)

    async def read_package(project_id: str) -> Any:
        """Read a Project's installed package: the record, its declaration and the hub."""
        pid = tools._path_id("project_id", project_id)
        return await api.get(f"/projects/{pid}/package")

    async def remove_package(project_id: str) -> Any:
        """Remove a Project's installed package record; no template version is deleted.

        Refused while initiatives of the package are open.
        """
        pid = tools._path_id("project_id", project_id)
        return await api.delete(f"/projects/{pid}/package")

    return [
        set_run_defaults,
        set_initiative_folder,
        install_package,
        read_package,
        remove_package,
    ]
