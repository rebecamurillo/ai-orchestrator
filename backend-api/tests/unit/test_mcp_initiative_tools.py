"""The initiative and session tools over `/mcp` (Operator ruling 2026-11-27, MCP initiative tools):
one call each, a UUID-checked path, the agent prefix on every message, and the composed wait."""

from __future__ import annotations

from typing import Any, cast

import pytest

from orchestrator.infrastructure.mcp import build_tools
from orchestrator.infrastructure.mcp.client import InProcessApi
from orchestrator.infrastructure.mcp.facade import ToolFailure
from orchestrator.infrastructure.mcp.initiative_tools import (
    AGENT_PREFIX,
    POLL_S,
    WAIT_MAX_S,
    compact,
    digest,
    initiative_tools,
)
from tests.unit.test_mcp_endpoint import Recorder

ID = "01a06887-79ab-759b-97a0-71c32ad939c2"
RUN = "01a06887-79ab-759b-97a0-71c32ad939c3"
HOSTILE = ("not-a-uuid", "../instance/hold?x=", "")


def tools(recorder: Recorder) -> dict[str, Any]:
    return {t.__name__: t for t in initiative_tools(InProcessApi(recorder, lambda: "tok"))}


class ScriptedApi:
    """Answers each GET with the next detail of a script (the last one repeats); records calls."""

    def __init__(self, *answers: dict[str, Any]) -> None:
        self.answers = list(answers) or [{}]
        self.calls: list[tuple[str, str, Any]] = []

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(("GET", path, params))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    async def post(self, path: str, body: Any = None) -> Any:
        self.calls.append(("POST", path, body))
        return {}


class Sleeper:
    def __init__(self) -> None:
        self.slept: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


def scripted(api: ScriptedApi, sleeper: Sleeper | None = None) -> dict[str, Any]:
    built = initiative_tools(cast(InProcessApi, api), sleeper or Sleeper())
    return {t.__name__: t for t in built}


def a_detail(*, attention: str | None = "your_turn", reply: str = "Which users?") -> dict[str, Any]:
    return {
        "status": "waiting for her",
        "attention": attention,
        "reason": "",
        "park_seq": 3,
        "updated_at": "2026-11-27T09:00:00Z",
        "current_position": 1,
        "current_step": "product",
        "workflows": [
            {"position": 2, "workflow": "build", "run_id": None, "status": None, "steps": []},
            {
                "position": 1,
                "workflow": "spec",
                "run_id": RUN,
                "status": "needs_you",
                "steps": [
                    {"id": "intake", "status": "done", "turns": []},
                    {
                        "id": "product",
                        "status": "waiting for her",
                        "park_kind": "conversation",
                        "park_reason": None,
                        "turns": [
                            {"status": "done", "reply": reply},
                            {"status": "queued", "reply": ""},
                        ],
                    },
                ],
            },
        ],
    }


# ── one call each ────────────────────────────────────────────────────────────────────────

ONE_CALL = [
    ("list_initiatives", {}, ("GET", "/api/v1/initiatives", "filter=ongoing")),
    (
        "list_initiatives",
        {"project_id": ID, "filter": "all"},
        ("GET", "/api/v1/initiatives", f"filter=all&project_id={ID}"),
    ),
    ("get_initiative", {"initiative_id": ID}, ("GET", f"/api/v1/initiatives/{ID}", "")),
    ("create_initiative", {"body": {"name": "n"}}, ("POST", "/api/v1/initiatives", "")),
    (
        "cancel_initiative",
        {"initiative_id": ID},
        ("POST", f"/api/v1/initiatives/{ID}/cancel", ""),
    ),
    (
        "start_next",
        {"initiative_id": ID, "park_seq": 3},
        ("POST", f"/api/v1/initiatives/{ID}/start-next", ""),
    ),
    ("get_session", {"run_id": RUN}, ("GET", f"/api/v1/runs/{RUN}/session", "")),
    (
        "post_session_message",
        {"run_id": RUN, "text": "yes"},
        ("POST", f"/api/v1/runs/{RUN}/session/messages", ""),
    ),
    ("retry_session", {"run_id": RUN}, ("POST", f"/api/v1/runs/{RUN}/session/retry", "")),
    ("wait_initiative", {"initiative_id": ID}, ("GET", f"/api/v1/initiatives/{ID}", "")),
]


@pytest.mark.parametrize(("name", "arguments", "expected"), ONE_CALL, ids=str)
async def test_a_tool_makes_exactly_that_one_call_with_the_bearer(
    name: str, arguments: dict[str, Any], expected: tuple[str, str, str]
) -> None:
    recorder = Recorder()

    await tools(recorder)[name](**arguments)

    assert recorder.calls == [expected]
    assert recorder.authorization == ["Bearer tok"]


def test_the_tools_list_in_order_and_reopen_has_none() -> None:
    names = [t.__name__ for t in initiative_tools(InProcessApi(object(), lambda: "t"))]

    assert names == [
        "list_initiatives",
        "get_initiative",
        "create_initiative",
        "cancel_initiative",
        "start_next",
        "get_session",
        "post_session_message",
        "retry_session",
        "wait_initiative",
    ]
    assert not any("reopen" in name for name in names)


def test_the_initiative_tools_follow_wait_run_events_in_the_tool_order() -> None:
    names = [t.__name__ for t in build_tools(InProcessApi(object(), lambda: "t"))]

    assert names[names.index("wait_run_events") + 1] == "list_initiatives"
    assert names[-1] == "wait_initiative"


async def test_start_next_sends_the_stop_it_names() -> None:
    api = ScriptedApi()

    await scripted(api)["start_next"](initiative_id=ID, park_seq=3)

    assert api.calls == [("POST", f"/initiatives/{ID}/start-next", {"park_seq": 3})]


async def test_get_initiative_never_marks_the_board_view() -> None:
    api = ScriptedApi()

    await scripted(api)["get_initiative"](initiative_id=ID)

    assert api.calls == [("GET", f"/initiatives/{ID}", None)]


# ── the proxy record ─────────────────────────────────────────────────────────────────────


async def test_every_message_is_stored_with_the_agent_prefix() -> None:
    api = ScriptedApi()

    await scripted(api)["post_session_message"](run_id=RUN, text="on valide")

    assert AGENT_PREFIX == "[the operator's agent] "
    assert api.calls == [
        ("POST", f"/runs/{RUN}/session/messages", {"text": "[the operator's agent] on valide"})
    ]


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
async def test_a_blank_message_is_refused_before_the_prefix_could_hide_it(blank: str) -> None:
    api = ScriptedApi()

    with pytest.raises(ToolFailure, match="blank"):
        await scripted(api)["post_session_message"](run_id=RUN, text=blank)

    assert api.calls == []


def test_the_docstrings_state_their_rules() -> None:
    docs = {
        name: " ".join((tool.__doc__ or "").lower().split())
        for name, tool in scripted(ScriptedApi()).items()
    }

    assert "never invented" in docs["create_initiative"]
    assert "irreversible" in docs["cancel_initiative"]
    assert "park_seq" in docs["start_next"]
    for phrase in ("[the operator's agent]", "close word", "escalate", "which step"):
        assert phrase in docs["post_session_message"], phrase
    assert "since" in docs["wait_initiative"]
    assert "your_turn" in docs["wait_initiative"]


# ── path ids ─────────────────────────────────────────────────────────────────────────────

PATH_TOOLS = {
    "list_initiatives": ("project_id", {}),
    "get_initiative": ("initiative_id", {}),
    "cancel_initiative": ("initiative_id", {}),
    "start_next": ("initiative_id", {"park_seq": 1}),
    "get_session": ("run_id", {}),
    "post_session_message": ("run_id", {"text": "ok"}),
    "retry_session": ("run_id", {}),
    "wait_initiative": ("initiative_id", {}),
}


@pytest.mark.parametrize("hostile", HOSTILE)
@pytest.mark.parametrize("name", sorted(PATH_TOOLS))
async def test_a_non_uuid_path_id_is_refused_before_any_call(name: str, hostile: str) -> None:
    argument, extra = PATH_TOOLS[name]
    recorder = Recorder()

    with pytest.raises(ToolFailure, match=argument):
        await tools(recorder)[name](**{argument: hostile}, **extra)

    assert recorder.calls == []


# ── the wait ─────────────────────────────────────────────────────────────────────────────


async def test_without_since_the_wait_answers_at_once_with_the_compact_view() -> None:
    api, sleeper = ScriptedApi(a_detail()), Sleeper()

    answer = await scripted(api, sleeper)["wait_initiative"](initiative_id=ID)

    assert sleeper.slept == []
    assert answer == {
        "since": digest(a_detail()),
        "changed": True,
        "initiative_status": "waiting for her",
        "attention": "your_turn",
        "reason": "",
        "park_seq": 3,
        "updated_at": "2026-11-27T09:00:00Z",
        "run_id": RUN,
        "workflow": "spec",
        "run_status": "needs_you",
        "step": "product",
        "step_status": "waiting for her",
        "park_kind": "conversation",
        "park_reason": None,
        "turns": 2,
        "last_turn_status": "queued",
        "last_reply": "Which users?",
    }


async def test_an_unchanged_initiative_waits_out_the_time_and_says_unchanged() -> None:
    api, sleeper = ScriptedApi(a_detail()), Sleeper()

    answer = await scripted(api, sleeper)["wait_initiative"](
        initiative_id=ID, wait=5, since=digest(a_detail())
    )

    assert sleeper.slept == [2.0, 2.0, 1.0]
    assert len(api.calls) == len(sleeper.slept) + 1
    assert answer["changed"] is False
    assert answer["since"] == digest(a_detail())


async def test_a_change_during_the_wait_answers_on_the_poll_that_sees_it() -> None:
    before, after = a_detail(attention="answering"), a_detail(reply="Here is the PRD.")
    api, sleeper = ScriptedApi(before, before, after), Sleeper()

    answer = await scripted(api, sleeper)["wait_initiative"](
        initiative_id=ID, wait=60, since=digest(before)
    )

    assert sleeper.slept == [2.0, 2.0]
    assert answer["changed"] is True
    assert answer["since"] == digest(after) != digest(before)
    assert answer["last_reply"] == "Here is the PRD."


@pytest.mark.parametrize(("wait", "slept"), [(0, 1.0), (-5, 1.0), (1000, float(WAIT_MAX_S))])
async def test_the_wait_is_clamped_to_one_to_a_hundred_and_twenty(wait: int, slept: float) -> None:
    api, sleeper = ScriptedApi(a_detail()), Sleeper()

    await scripted(api, sleeper)["wait_initiative"](
        initiative_id=ID, wait=wait, since=digest(a_detail())
    )

    assert sum(sleeper.slept) == slept
    assert max(sleeper.slept) <= POLL_S


def test_a_detail_with_no_current_workflow_or_step_reads_as_nothing_running() -> None:
    view = compact({"status": "done", "current_position": 9, "workflows": []}, changed=True)

    assert view["run_id"] is None
    assert view["step_status"] is None
    assert view["turns"] == 0
    assert view["last_turn_status"] is None
    assert view["last_reply"] is None


def test_a_step_with_no_reply_yet_has_no_last_reply() -> None:
    detail = a_detail(reply="")

    assert compact(detail, changed=False)["last_reply"] is None


def test_the_digest_ignores_what_the_agent_does_not_act_on() -> None:
    detail = a_detail()
    detail["first_message"] = "something else"
    detail["last_opened_at"] = "2026-11-27T10:00:00Z"

    assert digest(detail) == digest(a_detail())
