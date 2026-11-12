"""The workflow tools of `/mcp` (epic 2 story 2, 2026-11-12, AD-34)."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from orchestrator.api.providers import template_ports
from orchestrator.application import findings
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.infrastructure.mcp import build_tools
from orchestrator.infrastructure.mcp.client import ApiRefusal, InProcessApi
from orchestrator.infrastructure.mcp.facade import ToolFailure
from orchestrator.infrastructure.mcp.tools import Tool
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.template_folders import FakeTemplateFolders, file, ready
from tests.unit.fakes.templates import FakeTemplateVersionRepository
from tests.unit.test_mcp_endpoint import Recorder
from tests.unit.test_templates_in_folder import BODY, SMOKE

THREE_MISTAKES = """\
name: fixture
version: 1
bogus: 1
steps:
  - id: a
    uses: git.sync
    gate: deterministic
  - id: a
    uses: git.sync
    gate: deterministic
  - uses: git.sync
    gate: deterministic
"""
THREE = 3
BREAKERS = ["a/b", "a?b", "a#b", "a%b", "a..b"]


class BodyRecorder(Recorder):
    """The shared recorder, plus the JSON body of each request."""

    def __init__(self) -> None:
        super().__init__()
        self.bodies: list[bytes] = []

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        message = await receive()
        self.bodies.append(message.get("body", b""))
        await super().__call__(scope, receive, send)


def tool(tools: list[Tool], name: str) -> Tool:
    return next(t for t in tools if t.__name__ == name)


def over_app(env: dict[str, str], folders: FakeTemplateFolders | None) -> tuple[Any, list[Tool]]:
    app = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
    repo = FakeTemplateVersionRepository()
    uow, clock = FakeUnitOfWork(), FakeClock()
    uow.__enter__()
    app.dependency_overrides[template_ports] = lambda: TemplatePorts(
        uow=uow, templates=repo, clock=clock, folders=folders
    )
    return repo, build_tools(InProcessApi(app, lambda: env["ORCHESTRATOR_TOKEN"]))


async def test_validate_template_answers_each_mistake_with_a_line_and_a_resolvable_guide(
    env: dict[str, str],
) -> None:
    _, tools = over_app(env, None)

    answer = await tool(tools, "validate_template")("fixture", THREE_MISTAKES)

    assert len(answer["errors"]) == THREE
    for item in answer["errors"]:
        assert isinstance(item["line"], int)
        assert findings.entry(item["code"]).code == item["code"]
        assert item["guide"] == findings.guide_id(item["code"])


async def test_save_template_of_a_folder_held_name_is_refused_with_the_code(
    env: dict[str, str],
) -> None:
    repo, tools = over_app(env, FakeTemplateFolders(folder=ready(file(SMOKE, "x"))))

    with pytest.raises(ApiRefusal, match="409") as refused:
        await tool(tools, "save_template")(SMOKE, BODY.format(n=SMOKE, v=1))

    assert "refusal-template-in-folder" in str(refused.value)
    assert repo.list_versions(SMOKE) == []


async def test_the_three_tools_make_one_call_each_with_the_flag_on_the_save() -> None:
    recorder = BodyRecorder()
    tools = build_tools(InProcessApi(recorder, lambda: "tok"))

    await tool(tools, "validate_template")("wf", "y: 1")
    await tool(tools, "save_template")("wf", "y: 1")
    await tool(tools, "reload_templates")()

    assert [c[:2] for c in recorder.calls] == [
        ("POST", "/api/v1/templates/wf/validate"),
        ("POST", "/api/v1/templates/wf/versions"),
        ("POST", "/api/v1/templates/reload"),
    ]
    assert json.loads(recorder.bodies[1]) == {"yaml": "y: 1", "refuse_if_in_folder": True}
    assert json.loads(recorder.bodies[0]) == {"yaml": "y: 1"}
    assert recorder.authorization == ["Bearer tok"] * 3


@pytest.mark.parametrize("name", ["validate_template", "save_template"])
@pytest.mark.parametrize("breaker", BREAKERS)
async def test_a_name_that_breaks_the_path_is_refused_before_any_call(
    name: str, breaker: str
) -> None:
    recorder = BodyRecorder()
    tools = build_tools(InProcessApi(recorder, lambda: "tok"))

    with pytest.raises(ToolFailure, match="name"):
        await tool(tools, name)(breaker, "y: 1")

    assert recorder.calls == []


def test_the_tools_state_the_rules_an_agent_needs() -> None:
    tools = build_tools(cast(InProcessApi, object()))
    for name in ("validate_template", "save_template"):
        assert "errors/{code}" in (tool(tools, name).__doc__ or "")
    assert "reload_templates" in (tool(tools, "save_template").__doc__ or "")
