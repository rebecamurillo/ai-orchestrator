#!/usr/bin/env python3
"""Stub stdio MCP server for the story-6 experiment (which methods a CLI asks of a server).

Reads newline-delimited JSON-RPC from stdin, appends every message's `method` to the `--log`
file, and answers a minimal set of methods. Standard library only, Python 3.9 syntax.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Any

METHOD_NOT_FOUND = -32601
PARSE_ERROR = -32700

Handler = Callable[[dict[str, Any]], dict[str, Any]]


def _initialize(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": params.get("protocolVersion"),
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "serverInfo": {"name": "stub", "version": "0"},
    }


def _tools_list(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "noop",
                "description": "does nothing",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]
    }


def _resources_list(_: dict[str, Any]) -> dict[str, Any]:
    return {"resources": [{"uri": "guide://stub", "name": "stub", "mimeType": "text/markdown"}]}


def _resources_read(_: dict[str, Any]) -> dict[str, Any]:
    return {"contents": [{"uri": "guide://stub", "mimeType": "text/markdown", "text": "stub"}]}


def _prompts_list(_: dict[str, Any]) -> dict[str, Any]:
    return {"prompts": [{"name": "stub", "description": "stub prompt"}]}


def _prompts_get(_: dict[str, Any]) -> dict[str, Any]:
    return {"messages": [{"role": "user", "content": {"type": "text", "text": "stub"}}]}


def _ping(_: dict[str, Any]) -> dict[str, Any]:
    return {}


HANDLERS: dict[str, Handler] = {
    "initialize": _initialize,
    "tools/list": _tools_list,
    "resources/list": _resources_list,
    "resources/read": _resources_read,
    "prompts/list": _prompts_list,
    "prompts/get": _prompts_get,
    "ping": _ping,
}


def _write(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _error(id_: Any, code: int, text: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": text}}


def _log(path: str, method: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(method + "\n")
        handle.flush()


def _handle(line: str, log_path: str) -> None:
    try:
        message = json.loads(line)
    except ValueError:
        _write(_error(None, PARSE_ERROR, "parse error"))
        return
    if not isinstance(message, dict):
        _write(_error(None, PARSE_ERROR, "parse error"))
        return
    method = message.get("method")
    if isinstance(method, str):
        _log(log_path, method)
    if "id" not in message:
        return
    handler = HANDLERS.get(method) if isinstance(method, str) else None
    if handler is None:
        _write(_error(message["id"], METHOD_NOT_FOUND, "method not found"))
        return
    params = message.get("params")
    _write(
        {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": handler(params if isinstance(params, dict) else {}),
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True)
    args = parser.parse_args(argv)
    for line in sys.stdin:
        if line.strip():
            _handle(line, args.log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
