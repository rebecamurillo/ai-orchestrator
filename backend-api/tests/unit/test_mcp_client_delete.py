"""`InProcessApi.delete` sends one authorised DELETE under `/api/v1` (story 3 of epic 6)."""

from __future__ import annotations

from orchestrator.infrastructure.mcp.client import InProcessApi
from tests.unit.test_mcp_endpoint import Recorder


async def test_one_delete_with_the_bearer_reads_a_body_as_json() -> None:
    recorder = Recorder()

    answer = await InProcessApi(recorder, lambda: "tok").delete("/projects/x/package")

    assert recorder.calls == [("DELETE", "/api/v1/projects/x/package", "")]
    assert recorder.authorization == ["Bearer tok"]
    assert answer == {}


async def test_an_empty_204_body_reads_as_an_empty_string() -> None:
    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    assert await InProcessApi(app, lambda: "tok").delete("/x") == ""
