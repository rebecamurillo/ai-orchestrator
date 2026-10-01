"""The tools `/mcp` publishes: one REST operation each, and the rule that governs it.

Every docstring here is read by the agent that calls the tool — the SDK publishes it as the
tool's description — so each one states the same rule the `orchestrator` skill states for that
endpoint. The skill remains the floor: an operator whose harness speaks no MCP reads exactly
these rules in prose, and nothing here is a second source of truth for *how* the API behaves
(`infrastructure/mcp/client.py` says why).

Thin by construction: a tool parses nothing, decides nothing and writes no status (AD-8).

Three builders rather than one, in the order a session uses them — what this instance holds,
what starts and steers a Run, what watches one. The split is also what keeps each function
under the complexity limit `backend-api/AGENTS.md` sets, since a nested definition counts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from orchestrator.infrastructure.mcp.client import InProcessApi

#: What `build_tools` hands the server: named async callables, their signatures the schema.
type Tool = Callable[..., Awaitable[Any]]


def build_tools(api: InProcessApi) -> list[Tool]:
    """The whole tool set, bound to one in-process API client."""
    return [*_instance_tools(api), *_dispatch_tools(api), *_watch_tools(api)]


def _instance_tools(api: InProcessApi) -> list[Tool]:
    """What this instance is and what it holds."""

    async def version() -> Any:
        """What this instance is: its release, the kit it ships, and its BMAD and harness pins.

        Call this first. The kit installed in a project records the release it came from; when
        the two disagree, stop and say so rather than using an endpoint this instance may not
        have.
        """
        return await api.get("/version")

    async def list_templates() -> Any:
        """Every workflow Template this instance holds, with its versions.

        Templates are exemplars that evolve: read the list, never a remembered name or version.
        """
        return await api.get("/templates")

    async def get_template(name: str, version: int) -> Any:
        """One Template version — its declared inputs, defaults and steps.

        What a Run may be given is what the Template declares here; an input it does not
        declare is not passed.
        """
        return await api.get(f"/templates/{name}/{version}")

    async def list_projects() -> Any:
        """Every Project and the Repositories under it — where a Run's targeting comes from."""
        return await api.get("/projects")

    async def list_queue() -> Any:
        """What is running, what is waiting, and why each waiting Run is waiting."""
        return await api.get("/queue")

    return [version, list_templates, get_template, list_projects, list_queue]


def _dispatch_tools(api: InProcessApi) -> list[Tool]:
    """What starts a Run and what steers a parked one."""

    async def preflight_run(body: dict[str, Any]) -> Any:
        """Pre-flight a Run: every check that would refuse it, before anything is created.

        Always before `create_run`, and read every line: a `fail` line is a refusal to fix, not
        a warning to pass. `create_run` re-runs these checks and answers 409 on a `fail`.
        """
        return await api.post("/runs/preflight", body)

    async def create_run(body: dict[str, Any]) -> Any:
        """Create and enqueue a Run from a Template version.

        `budget_usd` is one human decision per Run: carry the number the operator gave, never
        invent, round or raise it. Pre-flight first.
        """
        return await api.post("/runs", body)

    async def send_signal(run_id: str, kind: str, payload: dict[str, Any] | None = None) -> Any:
        """Send one Signal to a parked Run.

        `kind` must be one of that Run's own `admitted_signals` — never a kind chosen from
        memory; anything else is refused with 409. A budget and a checkpoint are the operator's
        decisions and are never resolved on their behalf.
        """
        return await api.post(f"/runs/{run_id}/signals", {"kind": kind, "payload": payload or {}})

    return [preflight_run, create_run, send_signal]


def _watch_tools(api: InProcessApi) -> list[Tool]:
    """What a watcher reads, and how it waits."""

    async def get_run(run_id: str) -> Any:
        """One Run's state: status, spend, and the Signals it admits right now."""
        return await api.get(f"/runs/{run_id}")

    async def get_run_detail(run_id: str) -> Any:
        """Everything the Run screen shows: every step, the park, its attempts and its cost.

        This is what to read once a Run parks — the park payload is here, not in the events
        endpoint.
        """
        return await api.get(f"/runs/{run_id}/detail")

    async def wait_run_events(run_id: str, wait: int = 30, since: str | None = None) -> Any:
        """Wait up to `wait` seconds (0..30) for this Run to move, instead of polling.

        Answers as soon as `status` or `updated_at` changes, and `changed: false` when the wait
        ran out. Pass the `updated_at` of the previous answer as `since`, or a change made
        between two calls is missed. Then read `get_run_detail` to learn what happened.
        """
        return await api.get(f"/runs/{run_id}/events", {"wait": wait, "since": since})

    return [get_run, get_run_detail, wait_run_events]
