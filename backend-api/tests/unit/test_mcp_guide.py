"""The guide over `/mcp`: `read_guide`, `guide://{id}` resources and procedure prompts.

Story 5 of epic 2 (SPEC CAP-5; AD-32, AD-34). Each surface must return, byte for byte, what
the open route `/guide/{id}.md` serves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI, Response

from orchestrator.api.mcp_mount import guide_entries
from orchestrator.api.routers import guide, version
from orchestrator.infrastructure.mcp import InProcessApi, build_tools
from orchestrator.infrastructure.mcp.client import API_PREFIX, ApiRefusal
from orchestrator.infrastructure.mcp.facade import INSTRUCTIONS, ToolFailure
from orchestrator.infrastructure.mcp.tools import prompt_name
from orchestrator.tools import build_guide
from tests.unit.test_mcp_endpoint import Api, a_run, rpc

HTTP_OK = 200
CODE = "refusal-guide-unavailable"


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "source"
    (source / "runs").mkdir(parents=True)
    (source / "host").mkdir()
    (source / "connect.md").write_text(
        "---\ntitle: Connect\nkind: procedure\naudience: any\n---\nConnect body\n"
    )
    (source / "overview.md").write_text(
        "---\ntitle: Overview\nkind: page\naudience: any\n---\nOverview body\n"
    )
    (source / "runs" / "launch.md").write_text(
        "---\ntitle: Launch\nkind: procedure\naudience: any\n---\nLaunch body\n"
    )
    (source / "host" / "setup.md").write_text(
        "---\ntitle: Host setup\nkind: page\naudience: host\n---\n"
        "Local agent on the host or the user only.\n"
    )
    out = tmp_path / "build"
    assert (
        build_guide.main(
            [
                "--source",
                str(source),
                "--out",
                str(out),
                "--version-file",
                str(version.VERSION_FILE),
            ]
        )
        == 0
    )
    monkeypatch.setattr(guide, "GUIDE_DIR", out)
    return out


def pages(build: Path) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads((build / "guide-index.json").read_text())["pages"])


def procedures(build: Path) -> set[str]:
    return {p["id"] for p in pages(build) if p["kind"] == "procedure"}


async def call(client: httpx.AsyncClient, name: str, arguments: dict[str, Any]) -> Any:
    return await rpc(client, "tools/call", {"name": name, "arguments": arguments})


async def test_resources_list_every_page_and_read_what_the_open_route_serves(
    env: dict[str, str], built: Path
) -> None:
    api = Api(env, a_run())
    async with api.serving() as mcp, api.client(anonymous=True) as anon:
        listed = (await rpc(mcp, "resources/list"))["result"]["resources"]
        assert {r["uri"] for r in listed} == {f"guide://{p['id']}" for p in pages(built)}
        assert {r["mimeType"] for r in listed} == {"text/markdown"}
        for page in pages(built):
            open_text = (await anon.get(f"/guide/{page['id']}.md")).text
            read = await rpc(mcp, "resources/read", {"uri": f"guide://{page['id']}"})
            assert read["result"]["contents"][0]["text"] == open_text


async def test_read_guide_reads_the_index_and_every_page(env: dict[str, str], built: Path) -> None:
    api = Api(env, a_run())
    async with api.serving() as mcp, api.client(anonymous=True) as anon:
        index = await call(mcp, "read_guide", {})
        assert index["result"]["isError"] is False
        assert index["result"]["content"][0]["text"] == (await anon.get("/llms.txt")).text
        for page in pages(built):
            answer = await call(mcp, "read_guide", {"id": page["id"]})
            expected = (await anon.get(f"/guide/{page['id']}.md")).text
            assert answer["result"]["content"][0]["text"] == expected


async def test_each_procedure_is_a_prompt_and_no_page_is(env: dict[str, str], built: Path) -> None:
    api = Api(env, a_run())
    async with api.serving() as mcp, api.client(anonymous=True) as anon:
        listed = (await rpc(mcp, "prompts/list"))["result"]["prompts"]
        assert {p["name"] for p in listed} == {prompt_name(i) for i in procedures(built)}
        assert "runs.launch" in {p["name"] for p in listed}
        for page_id in procedures(built):
            got = (await rpc(mcp, "prompts/get", {"name": prompt_name(page_id)}))["result"]
            assert len(got["messages"]) == 1
            message = got["messages"][0]
            assert message["role"] == "user"
            assert message["content"]["text"] == (await anon.get(f"/guide/{page_id}.md")).text


@pytest.mark.parametrize("index", [None, "not json"])
async def test_without_a_build_there_is_no_resource_prompt_and_read_guide_refuses(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index: str | None
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    if index is not None:
        (empty / "guide-index.json").write_text(index)
    monkeypatch.setattr(guide, "GUIDE_DIR", empty)
    api = Api(env, a_run())
    async with api.serving() as mcp:
        assert (await rpc(mcp, "resources/list"))["result"]["resources"] == []
        assert (await rpc(mcp, "prompts/list"))["result"]["prompts"] == []
        answer = (await call(mcp, "read_guide", {}))["result"]
        assert answer["isError"] is True
        assert "404" in answer["content"][0]["text"]
        assert CODE in answer["content"][0]["text"]


def test_prompt_name_replaces_slashes() -> None:
    assert prompt_name("runs/launch") == "runs.launch"
    assert prompt_name("connect") == "connect"


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_open(self, path: str) -> str:
        self.calls.append(path)
        return "text"


@pytest.mark.parametrize("hostile", ["../api/v1/projects", "Connect", "a//b", "", "a?b", "%2e"])
async def test_a_hostile_page_id_is_refused_before_any_call(hostile: str) -> None:
    recorder = Recorder()
    tool = next(t for t in build_tools(cast(InProcessApi, recorder)) if t.__name__ == "read_guide")

    with pytest.raises(ToolFailure, match="not a page id"):
        await tool(id=hostile)

    assert recorder.calls == []


async def test_read_guide_calls_the_index_or_the_page() -> None:
    recorder = Recorder()
    tool = next(t for t in build_tools(cast(InProcessApi, recorder)) if t.__name__ == "read_guide")

    await tool()
    await tool(id="runs/launch")

    assert recorder.calls == ["/llms.txt", "/guide/runs/launch.md"]


def open_app(seen: dict[str, Any]) -> FastAPI:
    app = FastAPI()

    @app.get("/llms.txt")
    async def llms() -> Response:
        return Response("index", media_type="text/plain")

    @app.get(API_PREFIX + "/llms.txt")
    async def prefixed() -> Response:
        seen["prefixed"] = True
        return Response("wrong", media_type="text/plain")

    return app


async def test_get_open_has_no_prefix_sends_the_bearer_and_returns_text() -> None:
    seen: dict[str, Any] = {}
    api = InProcessApi(open_app(seen), lambda: "tok")

    assert await api.get_open("/llms.txt") == "index"
    assert "prefixed" not in seen


async def test_get_open_raises_the_refusal_with_its_status() -> None:
    api = InProcessApi(open_app({}), lambda: "tok")

    with pytest.raises(ApiRefusal) as raised:
        await api.get_open("/nowhere.md")

    assert raised.value.status == 404  # noqa: PLR2004


def test_the_instructions_point_at_the_guide() -> None:
    assert "Read the guide: read_guide with no id lists every page." in INSTRUCTIONS


@pytest.mark.parametrize(
    "index",
    [
        {"pages": "not a list"},
        ["not", "a", "dict"],
        {
            "pages": [
                "not a dict",
                {"id": 7, "kind": "procedure"},
                {"id": "../api/v1/projects", "kind": "procedure"},
                {"id": "a//b", "kind": "page"},
                {"id": "Connect", "kind": "procedure"},
            ]
        },
    ],
)
def test_an_index_entry_that_is_not_a_page_id_becomes_no_resource_or_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, index: Any
) -> None:
    (tmp_path / "guide-index.json").write_text(json.dumps(index))
    monkeypatch.setattr(guide, "GUIDE_DIR", tmp_path)
    recorder = Recorder()

    assert guide_entries(cast(InProcessApi, recorder)) == ([], [])


async def test_each_resource_reads_its_own_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages_ = [{"id": "a", "kind": "procedure"}, {"id": "b/c", "kind": "page"}]
    (tmp_path / "guide-index.json").write_text(json.dumps({"pages": pages_}))
    monkeypatch.setattr(guide, "GUIDE_DIR", tmp_path)
    recorder = Recorder()

    resources, prompts = guide_entries(cast(InProcessApi, recorder))
    for resource in resources:
        await resource.read()
    await prompts[0].render()

    assert [r.uri for r in resources] == ["guide://a", "guide://b/c"]
    assert [p.name for p in prompts] == ["a"]
    assert recorder.calls == ["/guide/a.md", "/guide/b/c.md", "/guide/a.md"]


def test_an_index_nested_too_deep_to_parse_becomes_no_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "guide-index.json").write_text("[" * 100_000)
    monkeypatch.setattr(guide, "GUIDE_DIR", tmp_path)

    assert guide_entries(cast(InProcessApi, Recorder())) == ([], [])
