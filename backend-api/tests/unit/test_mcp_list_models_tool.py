"""`list_models` of `/mcp` (epic 2 story 4, 2026-11-12, AD-34)."""

from __future__ import annotations

import pytest

from orchestrator.api.providers_harness_models import ModelSources, model_sources
from orchestrator.infrastructure.mcp import build_tools
from orchestrator.infrastructure.mcp.client import InProcessApi
from orchestrator.infrastructure.mcp.facade import ToolFailure
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.gateway import FakeGatewayModels
from tests.unit.test_mcp_workflow_tools import BodyRecorder, tool


async def test_the_tool_makes_one_get_with_the_bearer() -> None:
    recorder = BodyRecorder()
    tools = build_tools(InProcessApi(recorder, lambda: "tok"))

    await tool(tools, "list_models")(harness="claude")

    assert recorder.calls == [("GET", "/api/v1/harnesses/claude/models", "")]
    assert recorder.authorization == ["Bearer tok"]


@pytest.mark.parametrize("name", ["../instance/hold", "Claude"])
async def test_a_bad_name_is_refused_before_any_call(name: str) -> None:
    recorder = BodyRecorder()
    tools = build_tools(InProcessApi(recorder, lambda: "tok"))

    with pytest.raises(ToolFailure):
        await tool(tools, "list_models")(harness=name)

    assert recorder.calls == []


async def test_through_the_application_the_answer_is_the_fakes_list(env: dict[str, str]) -> None:
    app = create_app(Settings())
    fake = FakeGatewayModels(("claude-sonnet", "gpt-5"))
    app.dependency_overrides[model_sources] = lambda: ModelSources(fake, (), frozenset({"claude"}))
    tools = build_tools(InProcessApi(app, lambda: env["ORCHESTRATOR_TOKEN"]))

    answer = await tool(tools, "list_models")(harness="claude")

    assert answer["source"] == "litellm"
    assert answer["models"] == ["claude-sonnet", "gpt-5"]
