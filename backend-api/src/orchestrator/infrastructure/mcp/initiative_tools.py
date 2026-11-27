"""The tools that let the operator's own agent drive an initiative and speak for her in its
conversation steps (Operator ruling 2026-11-27, AD-23 and AD-38 amended).

Her agent never does a step's work: the step persona inside the instance does, and the
orchestrator keeps the sequence, the step files, the gate, the merge and the build. Reopen has
no tool on purpose: she reopens a step on the board.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from orchestrator.infrastructure.mcp import tools
from orchestrator.infrastructure.mcp.client import InProcessApi
from orchestrator.infrastructure.mcp.facade import ToolFailure

#: Starts every message sent through `post_session_message`. It is the proxy record of decision
#: 2a: the transcript, the step log and the board show the message came from her agent, and a
#: close word under it is hers, said by her agent. No column holds it, so it is never stripped.
AGENT_PREFIX = "[the operator's agent] "

POLL_S = 2.0
WAIT_MIN_S = 1
WAIT_MAX_S = 120

type Sleep = Callable[[float], Awaitable[None]]


def initiative_tools(api: InProcessApi, sleep: Sleep = asyncio.sleep) -> list[tools.Tool]:
    """What reads, creates, cancels and moves an initiative, its step session, and the wait."""
    return [*_initiative_actions(api), *_session_tools(api), _wait_tool(api, sleep)]


def _initiative_actions(api: InProcessApi) -> list[tools.Tool]:
    async def list_initiatives(project_id: str | None = None, filter: str = "ongoing") -> Any:
        """Every initiative with its computed status, newest change first.

        `filter` is `ongoing`, `needs_you` or `all`; `project_id` narrows to one Project.
        """
        params = {"filter": filter}
        if project_id is not None:
            params["project_id"] = tools._path_id("project_id", project_id)
        return await api.get("/initiatives", params)

    async def get_initiative(initiative_id: str) -> Any:
        """One initiative: its workflows with their steps and turns, its Runs, its stop.

        `park_seq` is the stop `start_next` names. Reading it here marks nothing as seen: the
        board's own view does that for her.
        """
        return await api.get(f"/initiatives/{tools._path_id('initiative_id', initiative_id)}")

    async def create_initiative(body: dict[str, Any]) -> Any:
        """Create an initiative and start its spec Run: `{project_id, name, first_message}`.

        `name` becomes the slug of the hub branch `spec/{slug}`; `first_message` is the first
        turn of the first conversation step, so write it from what the operator asked for. Read
        `read_package` and the Project's run defaults first: a budget is hers, never invented.
        """
        return await api.post("/initiatives", body)

    async def cancel_initiative(initiative_id: str) -> Any:
        """Cancel every live Run of the initiative and delete its `spec/{slug}` branch.

        Irreversible: only on the operator's own word.
        """
        iid = tools._path_id("initiative_id", initiative_id)
        return await api.post(f"/initiatives/{iid}/cancel")

    async def start_next(initiative_id: str, park_seq: int) -> Any:
        """Force the next conversation step, leaving the open one unclosed.

        `park_seq` is the initiative's `park_seq` you read with the stop: a moved stop refuses
        with 409. A step closes on its close word in the session; this skips that word, so use
        it only when the operator asked for it.
        """
        iid = tools._path_id("initiative_id", initiative_id)
        return await api.post(f"/initiatives/{iid}/start-next", {"park_seq": park_seq})

    return [list_initiatives, get_initiative, create_initiative, cancel_initiative, start_next]


def _session_tools(api: InProcessApi) -> list[tools.Tool]:
    async def get_session(run_id: str) -> Any:
        """The session open on a Run's stop: every turn, its message, the persona's reply.

        On an initiative, `run_id` is the current Run that `wait_initiative` names.
        """
        return await api.get(f"/runs/{tools._path_id('run_id', run_id)}/session")

    async def post_session_message(run_id: str, text: str) -> Any:
        """Send the open session one message on the operator's behalf; it is queued as a turn.

        The message is stored as `[the operator's agent] <text>`, so everyone reading the step
        sees it came from her agent. Answer only from what she said or what you know of her
        app; escalate business scope, priorities, any budget and anything irreversible to her.
        You may send a step's close word when the step's files hold what she asked for: it
        counts as hers, recorded as said by her agent, and you tell her which step you closed.
        """
        if not text.strip():
            raise ToolFailure("text must not be blank")
        rid = tools._path_id("run_id", run_id)
        return await api.post(f"/runs/{rid}/session/messages", {"text": AGENT_PREFIX + text})

    async def retry_session(run_id: str) -> Any:
        """Restart the session's last failed turn, resuming the same harness session.

        Refused unless the last turn failed. Retry once; a second failure goes to the operator.
        """
        return await api.post(f"/runs/{tools._path_id('run_id', run_id)}/session/retry")

    return [get_session, post_session_message, retry_session]


def _wait_tool(api: InProcessApi, sleep: Sleep) -> tools.Tool:
    async def wait_initiative(initiative_id: str, wait: int = 60, since: str | None = None) -> Any:
        """Wait up to `wait` seconds (1..120) for the initiative to move, instead of polling.

        Answers at once when `since` is absent or differs from the initiative's state, and
        `changed: false` when the wait ran out. Pass the `since` of the previous answer, or a
        change between two calls is missed. On `attention: your_turn`, read `get_session` for
        the current Run and answer with `post_session_message`.
        """
        path = f"/initiatives/{tools._path_id('initiative_id', initiative_id)}"
        remaining = float(min(max(int(wait), WAIT_MIN_S), WAIT_MAX_S))
        detail = await api.get(path)
        while digest(detail) == since and remaining > 0:
            step = min(POLL_S, remaining)
            await sleep(step)
            remaining -= step
            detail = await api.get(path)
        return compact(detail, changed=digest(detail) != since)

    return wait_initiative


def _current(detail: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The workflow at `current_position` and its step named `current_step`; `{}` where absent."""
    position = detail.get("current_position")
    workflows = detail.get("workflows") or []
    workflow = next((w for w in workflows if w.get("position") == position), {})
    named = detail.get("current_step")
    step = next((s for s in workflow.get("steps") or [] if s.get("id") == named), {})
    return workflow, step


def _view(detail: dict[str, Any]) -> dict[str, Any]:
    workflow, step = _current(detail)
    turns = step.get("turns") or []
    replied = [turn for turn in turns if turn.get("reply")]
    return {
        "initiative_status": detail.get("status"),
        "attention": detail.get("attention"),
        "reason": detail.get("reason"),
        "park_seq": detail.get("park_seq"),
        "updated_at": detail.get("updated_at"),
        "run_id": workflow.get("run_id"),
        "workflow": workflow.get("workflow"),
        "run_status": workflow.get("status"),
        "step": detail.get("current_step"),
        "step_status": step.get("status"),
        "park_kind": step.get("park_kind"),
        "park_reason": step.get("park_reason"),
        "turns": len(turns),
        "last_turn_status": turns[-1].get("status") if turns else None,
        "last_reply": replied[-1]["reply"] if replied else None,
    }


def digest(detail: dict[str, Any]) -> str:
    """A short hash of what the operator's agent acts on; equal digests mean nothing moved."""
    text = json.dumps(_view(detail), sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def compact(detail: dict[str, Any], *, changed: bool) -> dict[str, Any]:
    """The wait's answer: the new `since`, whether it moved, and the current Run and step."""
    return {"since": digest(detail), "changed": changed, **_view(detail)}
