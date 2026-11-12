"""The stub MCP server of the story-6 experiment, driven through a subprocess pipe."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any

from tests.unit.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "mcp_stub_server.py"
METHOD_NOT_FOUND = -32601
PARSE_ERROR = -32700
SECOND_ID = 2
EIGHTH_ID = 8


class Session:
    def __init__(self, proc: subprocess.Popen[str]) -> None:
        self.proc = proc

    def send(self, message: dict[str, Any]) -> None:
        stdin: IO[str] = self.proc.stdin  # type: ignore[assignment]
        stdin.write(json.dumps(message) + "\n")
        stdin.flush()

    def read(self) -> dict[str, Any]:
        stdout: IO[str] = self.proc.stdout  # type: ignore[assignment]
        return json.loads(stdout.readline())  # type: ignore[no-any-return]

    def call(self, id_: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.send({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})
        return self.read()


@contextmanager
def stub(log: Path) -> Iterator[Session]:
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--log", str(log)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        yield Session(proc)
        proc.communicate(timeout=10)
        assert proc.returncode == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def test_initialize_then_resources_list_are_answered_and_logged(tmp_path: Path) -> None:
    log = tmp_path / "log"
    with stub(log) as s:
        init = s.call(1, "initialize", {"protocolVersion": "2025-06-18"})
        listed = s.call(SECOND_ID, "resources/list")
    assert init["id"] == 1
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert set(init["result"]["capabilities"]) == {"tools", "resources", "prompts"}
    assert init["result"]["serverInfo"]["name"] == "stub"
    assert listed["id"] == SECOND_ID
    assert [r["uri"] for r in listed["result"]["resources"]] == ["guide://stub"]
    assert log.read_text().splitlines() == ["initialize", "resources/list"]


def test_notification_gets_no_answer_and_unknown_method_is_refused(tmp_path: Path) -> None:
    log = tmp_path / "log"
    with stub(log) as s:
        s.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert s.call(7, "ping") == {"jsonrpc": "2.0", "id": 7, "result": {}}
        refused = s.call(EIGHTH_ID, "tools/call", {"name": "noop"})
    assert refused["id"] == EIGHTH_ID
    assert refused["error"]["code"] == METHOD_NOT_FOUND
    assert log.read_text().splitlines() == ["notifications/initialized", "ping", "tools/call"]


def test_unparsable_line_is_a_parse_error_and_is_not_logged(tmp_path: Path) -> None:
    log = tmp_path / "log"
    with stub(log) as s:
        stdin: IO[str] = s.proc.stdin  # type: ignore[assignment]
        stdin.write("\n{not json\n")
        stdin.flush()
        answer = s.read()
    assert answer["id"] is None
    assert answer["error"]["code"] == PARSE_ERROR
    assert not log.exists() or log.read_text() == ""


def test_remaining_methods_answer_minimal_results(tmp_path: Path) -> None:
    with stub(tmp_path / "log") as s:
        tools = s.call(1, "tools/list")["result"]["tools"]
        prompts = s.call(2, "prompts/list")["result"]["prompts"]
        read = s.call(3, "resources/read", {"uri": "guide://stub"})["result"]["contents"]
        got = s.call(4, "prompts/get", {"name": "stub"})["result"]["messages"]
    assert [t["name"] for t in tools] == ["noop"]
    assert [p["name"] for p in prompts] == ["stub"]
    assert read[0]["uri"] == "guide://stub"
    assert got[0]["role"] == "user"


def test_source_parses_as_python_39() -> None:
    ast.parse(SCRIPT.read_text(), feature_version=(3, 9))
