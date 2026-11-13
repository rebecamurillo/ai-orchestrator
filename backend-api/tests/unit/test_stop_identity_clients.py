"""AD-24 at the first-party clients and the edges: body validation, storage, MCP.

The watcher test left with the watcher (epic 3 story 3, 2026-11-12, AD-33).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.signals import SignalIn
from orchestrator.infrastructure.db.models.run import RunRow
from orchestrator.infrastructure.db.repositories import runs as runs_module
from orchestrator.infrastructure.mcp.tools import build_tools
from tests.unit.application.writer_fixtures import build_run

STOP = 4
RUN = "01a06887-79ab-759b-97a0-71c32ad939c2"


@pytest.mark.parametrize("value", [True, "3", 2.5, -1])
def test_a_signal_body_refuses_anything_but_a_whole_stop_number(value: object) -> None:
    with pytest.raises(ValidationError):
        SignalIn(kind="answer", stop=value)  # type: ignore[arg-type]


def test_a_stored_number_reads_back() -> None:
    run = build_run("needs_you", park_seq=STOP)

    row = RunRow(**runs_module.row_values(run))

    assert row.park_seq == STOP
    assert runs_module.to_entity(row).park_seq == STOP


class RecordingApi:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []

    async def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.posts.append((path, body))
        return {}


def send_signal(api: RecordingApi) -> Any:
    return {tool.__name__: tool for tool in build_tools(api)}["send_signal"]  # type: ignore[arg-type]


async def test_the_mcp_tool_forwards_the_stop() -> None:
    api = RecordingApi()

    await send_signal(api)(RUN, "answer", {"text": "go"}, stop=STOP)

    assert api.posts == [
        (f"/runs/{RUN}/signals", {"kind": "answer", "payload": {"text": "go"}, "stop": STOP})
    ]


async def test_the_mcp_tool_sends_no_stop_when_it_was_given_none() -> None:
    api = RecordingApi()

    await send_signal(api)(RUN, "cancel")

    assert api.posts == [(f"/runs/{RUN}/signals", {"kind": "cancel", "payload": {}})]


def test_the_mcp_tool_states_the_rule() -> None:
    assert "park_seq" in (send_signal(RecordingApi()).__doc__ or "")
