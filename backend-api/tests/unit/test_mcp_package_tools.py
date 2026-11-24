"""`set_run_defaults` over `/mcp` (story 1 of epic 6): one `PUT`, a UUID-checked path."""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.mcp import build_tools
from orchestrator.infrastructure.mcp.client import InProcessApi
from orchestrator.infrastructure.mcp.facade import ToolFailure
from orchestrator.infrastructure.mcp.package_tools import package_tools
from tests.unit.test_mcp_endpoint import Recorder

ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


def tools(recorder: Recorder) -> dict[str, object]:
    return {tool.__name__: tool for tool in package_tools(InProcessApi(recorder, lambda: "tok"))}


async def test_set_run_defaults_makes_one_put_to_the_route() -> None:
    recorder = Recorder()

    await tools(recorder)["set_run_defaults"](project_id=ID, body={"default_model": None})  # type: ignore[operator]

    assert recorder.calls == [("PUT", f"/api/v1/projects/{ID}/run-defaults", "")]
    assert recorder.authorization == ["Bearer tok"]


@pytest.mark.parametrize("hostile", ["not-a-uuid", "../instance/hold?x=", ""])
async def test_a_non_uuid_project_id_is_refused_before_any_call(hostile: str) -> None:
    recorder = Recorder()

    with pytest.raises(ToolFailure):
        await tools(recorder)["set_run_defaults"](project_id=hostile, body={})  # type: ignore[operator]

    assert recorder.calls == []


def test_the_docstring_states_the_replace_together_and_never_invent_rules() -> None:
    doc = (tools(Recorder())["set_run_defaults"].__doc__ or "").lower()

    for phrase in ("replaced together", "omitted key is refused", "null", "never invent"):
        assert phrase in doc, phrase


async def test_set_initiative_folder_makes_one_put_to_the_route() -> None:
    recorder = Recorder()

    await tools(recorder)["set_initiative_folder"](  # type: ignore[operator]
        repository_id=ID, body={"initiative_folder": "specs"}
    )

    assert recorder.calls == [("PUT", f"/api/v1/repositories/{ID}/initiative-folder", "")]
    assert recorder.authorization == ["Bearer tok"]


@pytest.mark.parametrize("hostile", ["not-a-uuid", "../instance/hold?x=", ""])
async def test_a_non_uuid_repository_id_is_refused_before_any_call(hostile: str) -> None:
    recorder = Recorder()

    with pytest.raises(ToolFailure):
        await tools(recorder)["set_initiative_folder"](repository_id=hostile, body={})  # type: ignore[operator]

    assert recorder.calls == []


def test_the_initiative_folder_docstring_names_the_folder_rule() -> None:
    doc = " ".join((tools(Recorder())["set_initiative_folder"].__doc__ or "").lower().split())

    for phrase in ("every initiative", "initiative_folder", "lie under it", "omitted"):
        assert phrase in doc, phrase


def test_the_tools_list_in_order() -> None:
    names = [tool.__name__ for tool in package_tools(InProcessApi(object(), lambda: "t"))]

    assert names == ["set_run_defaults", "set_initiative_folder"]


def test_set_initiative_folder_follows_set_run_defaults_in_the_tool_order() -> None:
    names = [tool.__name__ for tool in build_tools(InProcessApi(object(), lambda: "t"))]

    assert names[names.index("set_run_defaults") + 1] == "set_initiative_folder"


def test_the_tool_follows_init_repository_in_the_tool_order() -> None:
    names = [tool.__name__ for tool in build_tools(InProcessApi(object(), lambda: "t"))]

    assert names[names.index("init_repository") + 1] == "set_run_defaults"
