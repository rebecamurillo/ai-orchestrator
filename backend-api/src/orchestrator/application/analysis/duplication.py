"""Reading a jscpd run: the added lines inside clones, and the SARIF made path-free."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any


def common_dir(paths: Sequence[str]) -> str:
    """The deepest folder holding every path, as jscpd names its files relative to it."""
    parents = [PurePosixPath(path).parent.parts for path in paths]
    shared: list[str] = []
    for level in zip(*parents, strict=False):
        if len(set(level)) != 1:
            break
        shared.append(level[0])
    return "/".join(shared)


def duplication_added(report_json: str, added: Mapping[str, frozenset[int]], folder: str) -> int:
    """Distinct added `(path, line)` inside any clone fragment, fragment ends included.

    `folder` is the common folder of the scanned files: jscpd names a fragment relative to it.
    """
    counted: set[tuple[str, int]] = set()
    for clone in json.loads(report_json).get("duplicates", []):
        for side in ("firstFile", "secondFile"):
            fragment = clone[side]
            path = f"{folder}/{fragment['name']}" if folder else fragment["name"]
            counted.update(
                (path, line)
                for line in added.get(path, ())
                if fragment["start"] <= line <= fragment["end"]
            )
    return len(counted)


def _rewrite(value: Any, prefixes: Sequence[str]) -> Any:
    if isinstance(value, str):
        for prefix in prefixes:
            if value.startswith(prefix):
                return value[len(prefix) :] or "./"
        return value
    if isinstance(value, list):
        return [_rewrite(item, prefixes) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite(item, prefixes) for key, item in value.items()}
    return value


def relative_sarif(text: str) -> str:
    """The SARIF with every `file://` URI made relative to its scan root.

    The base URI jscpd records is the absolute scan folder; stored as it is it would put a
    scratch path in the result.
    """
    document = json.loads(text)
    for run in document.get("runs", []):
        bases = run.get("originalUriBaseIds", {})
        prefixes = [
            base["uri"]
            for base in bases.values()
            if isinstance(base.get("uri"), str) and base["uri"].startswith("file://")
        ]
        run.update(_rewrite(run, prefixes))
    return json.dumps(document, ensure_ascii=False)
