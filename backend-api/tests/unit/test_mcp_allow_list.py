"""The MCP tool set against the allow-list of REST operations (AD-34).

Every tool makes exactly one call; the call is matched to an operationId through the
application's own OpenAPI document, and an operation outside `ALLOWED_OPERATION_IDS` — or one
no template matches — fails. The list itself may never hold a maintenance operation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast
from urllib.parse import quote

import pytest

from orchestrator.infrastructure.mcp.client import API_PREFIX, InProcessApi
from orchestrator.infrastructure.mcp.facade import ToolFailure
from orchestrator.infrastructure.mcp.tools import ALLOWED_OPERATION_IDS, Tool, build_tools
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app

ID = "01a06887-79ab-759b-97a0-71c32ad939c2"
HOSTILE = "../instance/hold?x="
FORBIDDEN_FAMILIES = ("/api/v1/instance", "/api/v1/kit")
FORBIDDEN_FRAGMENTS = ("/readiness", "/probe")
#: Story 2 of epic 2, 2026-11-12 (AD-34): validate_template, save_template, reload_templates join.
#: Story 3 of epic 2, 2026-11-12 (AD-34): validate_spec_folder joins.
#: Story 4 of epic 2, 2026-11-12 (AD-34): list_models joins.
#: Story 5 of epic 2, 2026-11-12 (AD-34): read_guide joins (index and page).
TWENTY_THREE = 23

PLACEHOLDERS: dict[str, dict[str, Any]] = {
    "version": {},
    "list_models": {"harness": "claude"},
    "read_guide": {"id": "connect"},
    "list_templates": {},
    "get_template": {"name": "repo-init", "version": 2},
    "list_projects": {},
    "list_queue": {},
    "create_project": {"body": {}},
    "update_project": {"project_id": ID, "body": {}},
    "add_repository": {"project_id": ID, "body": {}},
    "check_clone": {"repository_id": ID},
    "init_repository": {"repository_id": ID},
    "validate_template": {"name": "fixture", "yaml": ""},
    "save_template": {"name": "fixture", "yaml": ""},
    "reload_templates": {},
    "validate_spec_folder": {"files": {}},
    "preflight_run": {"body": {}},
    "create_run": {"body": {}},
    "send_signal": {"run_id": ID, "kind": "continue"},
    "get_run": {"run_id": ID},
    "get_run_detail": {"run_id": ID},
    "wait_run_events": {"run_id": ID},
}

NEW_PATH_TOOLS = {
    "update_project": ("project_id", {"body": {}}),
    "add_repository": ("project_id", {"body": {}}),
    "check_clone": ("repository_id", {}),
    "init_repository": ("repository_id", {}),
}


class RecordingApi:
    """Records `(method, path)`; answers `{}`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(("GET", API_PREFIX + path))
        return {}

    async def get_open(self, path: str) -> str:
        self.calls.append(("GET", path))
        return ""

    async def post(self, path: str, body: Any = None) -> Any:
        self.calls.append(("POST", API_PREFIX + path))
        return {}

    async def put(self, path: str, body: Any = None) -> Any:
        self.calls.append(("PUT", API_PREFIX + path))
        return {}


def _tools(recorder: RecordingApi) -> list[Tool]:
    return build_tools(cast(InProcessApi, recorder))


def _regex(template: str) -> re.Pattern[str]:
    pattern = re.escape(template)
    pattern = re.sub(r"\\\{[^}:]+:path\\\}", ".+", pattern)
    return re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", pattern) + "$")


def operation_id(paths: dict[str, Any], method: str, path: str) -> str | None:
    """The operationId of the most literal template matching the call, if any."""
    candidates: list[tuple[int, str]] = []
    for template, operations in paths.items():
        operation = operations.get(method.lower())
        reaches = _regex(template).match(path) or _regex(API_PREFIX + template).match(path)
        if operation and reaches:
            literal = sum(1 for part in template.split("/") if part and "{" not in part)
            candidates.append((literal, operation["operationId"]))
    return max(candidates)[1] if candidates else None


#: Not a `type` statement: scripts/check_test_pairs.py parses tests on the system python3 (3.9).
Builder = Callable[[RecordingApi], list[Tool]]


async def violations(build: Builder, allowed: frozenset[str], paths: dict[str, Any]) -> list[str]:
    """One fresh recorder per tool, so a second call is counted against the tool that made it."""
    found: list[str] = []
    for index, name in enumerate(tool.__name__ for tool in build(RecordingApi())):
        recorder = RecordingApi()
        await build(recorder)[index](**PLACEHOLDERS.get(name, {}))
        if len(recorder.calls) != 1:
            found.append(f"{name}: made {len(recorder.calls)} calls")
            continue
        method, path = recorder.calls[0]
        found.extend(_check(name, method, path, allowed, paths))
    return found


def _check(
    name: str, method: str, path: str, allowed: frozenset[str], paths: dict[str, Any]
) -> list[str]:
    found = operation_id(paths, method, path)
    if found is None:
        return [f"{name}: {method} {path} matches no operation"]
    if found not in allowed:
        return [f"{name}: {method} {path} is {found}, not in the allow-list"]
    return []


@pytest.fixture
def paths(env: dict[str, str]) -> dict[str, Any]:
    app = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
    return cast(dict[str, Any], app.openapi()["paths"])


def test_every_tool_has_placeholders() -> None:
    assert set(PLACEHOLDERS) == {tool.__name__ for tool in _tools(RecordingApi())}


async def test_every_tool_makes_one_call_to_an_allowed_operation(paths: dict[str, Any]) -> None:
    assert await violations(_tools, ALLOWED_OPERATION_IDS, paths) == []
    assert len(ALLOWED_OPERATION_IDS) == TWENTY_THREE


async def test_a_tool_calling_an_unlisted_operation_is_reported(paths: dict[str, Any]) -> None:
    def with_hold(recorder: RecordingApi) -> list[Tool]:
        async def hold() -> Any:
            return await recorder.post("/instance/hold", {})

        return [*_tools(recorder), hold]

    found = await violations(with_hold, ALLOWED_OPERATION_IDS, paths)

    assert len(found) == 1
    assert "hold" in found[0]
    assert "/api/v1/instance/hold" in found[0]


async def test_a_call_matching_no_operation_is_a_violation(paths: dict[str, Any]) -> None:
    def with_ghost(recorder: RecordingApi) -> list[Tool]:
        async def ghost() -> Any:
            return await recorder.get("/no-such-route")

        return [ghost]

    assert len(await violations(with_ghost, ALLOWED_OPERATION_IDS, paths)) == 1


def maintenance(allowed: frozenset[str], paths: dict[str, Any]) -> list[str]:
    """The allowed operationIds whose path is a maintenance one. OpenAPI paths carry the prefix."""
    by_id = {
        operation["operationId"]: path
        for path, operations in paths.items()
        for operation in operations.values()
    }
    return [
        f"{operation_id_}: {by_id[operation_id_]}"
        for operation_id_ in sorted(allowed)
        if by_id[operation_id_].startswith(FORBIDDEN_FAMILIES)
        or any(fragment in by_id[operation_id_] for fragment in FORBIDDEN_FRAGMENTS)
    ]


def _ids(paths: dict[str, Any]) -> set[str]:
    return {op["operationId"] for operations in paths.values() for op in operations.values()}


def test_the_allow_list_holds_no_maintenance_operation(paths: dict[str, Any]) -> None:
    assert ALLOWED_OPERATION_IDS <= _ids(paths)
    assert maintenance(ALLOWED_OPERATION_IDS, paths) == []


def test_a_maintenance_operation_in_the_allow_list_is_reported(paths: dict[str, Any]) -> None:
    held = paths["/api/v1/instance/hold"]["post"]["operationId"]

    found = maintenance(ALLOWED_OPERATION_IDS | {held}, paths)

    assert found == [f"{held}: /api/v1/instance/hold"]


@pytest.mark.parametrize("name", sorted(NEW_PATH_TOOLS))
async def test_a_path_id_that_is_not_a_uuid_is_refused_before_any_call(name: str) -> None:
    argument, extra = NEW_PATH_TOOLS[name]
    recorder = RecordingApi()
    tool = next(t for t in _tools(recorder) if t.__name__ == name)

    with pytest.raises(ToolFailure, match=argument):
        await tool(**{argument: HOSTILE}, **extra)

    assert recorder.calls == []


#: Epic 2 retro R1/R2, operator ruling park 6, 2026-11-12: every path tool, hostile arguments,
#: asserted on what the transport receives after httpx normalises the URL.
PATH_TOOLS: dict[str, tuple[str, dict[str, Any], str, str]] = {
    "get_template": ("name", {"version": 2}, "/api/v1/templates/{}/2", "repo-init"),
    "send_signal": ("run_id", {"kind": "continue"}, "/api/v1/runs/{}/signals", ID),
    "get_run": ("run_id", {}, "/api/v1/runs/{}", ID),
    "get_run_detail": ("run_id", {}, "/api/v1/runs/{}/detail", ID),
    "wait_run_events": ("run_id", {"wait": 0}, "/api/v1/runs/{}/events", ID),
    "update_project": ("project_id", {"body": {}}, "/api/v1/projects/{}", ID),
    "add_repository": ("project_id", {"body": {}}, "/api/v1/projects/{}/repositories", ID),
    "check_clone": ("repository_id", {}, "/api/v1/repositories/{}/clone-check", ID),
    "init_repository": ("repository_id", {}, "/api/v1/repositories/{}/init", ID),
}
HOSTILE_SEGMENTS = (
    "..",
    "../health",
    "a/../../instance/activity",
    "%2e%2e",
    "a/b",
    "a\\b",
    "a?x=1",
    "a#f",
    "",
)


class TransportRecorder:
    """An ASGI app behind the real `InProcessApi`: records the path the transport delivers."""

    def __init__(self) -> None:
        self.received: list[tuple[str, bytes]] = []

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.received.append((scope["path"], scope["raw_path"]))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def _path_tool(recorder: TransportRecorder, name: str) -> Tool:
    tools = build_tools(InProcessApi(recorder, lambda: "tok"))
    return next(t for t in tools if t.__name__ == name)


@pytest.mark.parametrize("value", HOSTILE_SEGMENTS)
@pytest.mark.parametrize("name", sorted(PATH_TOOLS))
async def test_a_hostile_path_argument_never_leaves_its_one_segment(name: str, value: str) -> None:
    argument, extra, template, _ = PATH_TOOLS[name]
    recorder = TransportRecorder()

    try:
        await _path_tool(recorder, name)(**{argument: value}, **extra)
    except ToolFailure:
        assert recorder.received == []
        return

    encoded = quote(value, safe="")
    assert recorder.received == [(template.format(value), template.format(encoded).encode())]


@pytest.mark.parametrize("name", sorted(PATH_TOOLS))
async def test_a_valid_path_argument_reaches_its_template(name: str) -> None:
    argument, extra, template, valid = PATH_TOOLS[name]
    recorder = TransportRecorder()

    await _path_tool(recorder, name)(**{argument: valid}, **extra)

    assert recorder.received == [(template.format(valid), template.format(valid).encode())]


async def test_read_guide_without_an_id_reads_the_index(paths: dict[str, Any]) -> None:
    recorder = RecordingApi()
    tool = next(t for t in _tools(recorder) if t.__name__ == "read_guide")

    await tool()

    assert recorder.calls == [("GET", "/llms.txt")]
    assert operation_id(paths, "GET", "/llms.txt") == "read_index_llms_txt_get"
    assert "read_index_llms_txt_get" in ALLOWED_OPERATION_IDS
