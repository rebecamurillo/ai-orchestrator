"""`validate_spec_folder` of `/mcp` (epic 2 story 3, 2026-11-12, AD-35)."""

from __future__ import annotations

import json

from orchestrator.infrastructure.mcp import build_tools
from orchestrator.infrastructure.mcp.client import InProcessApi
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.test_mcp_workflow_tools import BodyRecorder, tool

DUPLICATES = '- {id: "3", title: A, description: d}\n- {id: "3", title: B, description: d}\n'


async def test_the_tool_makes_one_post_with_the_body_and_the_bearer() -> None:
    recorder = BodyRecorder()
    tools = build_tools(InProcessApi(recorder, lambda: "tok"))
    files = {"e1/stories.yaml": "x"}

    await tool(tools, "validate_spec_folder")(files=files)

    assert recorder.calls == [("POST", "/api/v1/spec-folders/validate", "")]
    assert recorder.authorization == ["Bearer tok"]
    assert json.loads(recorder.bodies[0]) == {"files": files}


async def test_through_the_application_a_duplicate_id_is_a_finding(
    env: dict[str, str],
) -> None:
    app = create_app(Settings())
    tools = build_tools(InProcessApi(app, lambda: env["ORCHESTRATOR_TOKEN"]))

    answer = await tool(tools, "validate_spec_folder")(
        files={"e1/stories.yaml": DUPLICATES, "e1/SPEC.md": "x"}
    )

    assert [f["code"] for f in answer["findings"]] == ["spec-duplicate-entry-id"]
