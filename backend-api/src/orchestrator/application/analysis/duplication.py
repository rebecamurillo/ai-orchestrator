"""Reading a jscpd run through its SARIF: clone fragments at paths relative to the scan root.

jscpd's JSON `name` depends on the scanned set (a bare basename for a flat one), so a path is
taken only from the SARIF: each result is one clone, its fragments in `locations` and
`relatedLocations`, each `file://` URI resolved against `originalUriBaseIds` and made relative
to the scan root (Operator ruling 2026-11-13).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote

FILE_SCHEME = "file://"


@dataclass(frozen=True)
class Fragment:
    path: str
    start: int
    end: int


def _bases(run: Mapping[str, Any]) -> dict[str, str]:
    bases = run.get("originalUriBaseIds") or {}
    return {
        key: value["uri"]
        for key, value in bases.items()
        if isinstance(value, dict) and isinstance(value.get("uri"), str)
    }


def _file_uri(location: Mapping[str, Any], bases: Mapping[str, str]) -> str | None:
    """The location's absolute `file://` URI, or `None` when it does not resolve to one."""
    uri = location.get("uri")
    if not isinstance(uri, str):
        return None
    base_id = location.get("uriBaseId")
    full = bases.get(base_id, "") + uri if isinstance(base_id, str) else uri
    return full if full.startswith(FILE_SCHEME) else None


def _relative(full: str, root: str) -> str | None:
    """The path of a `file://` URI below `root`, or `None` when it lies elsewhere."""
    path = unquote(full[len(FILE_SCHEME) :])
    prefix = f"{root.rstrip('/')}/"
    return path[len(prefix) :] if path.startswith(prefix) and path != prefix else None


def clone_fragments(sarif_text: str, root: str) -> list[list[Fragment]]:
    """One list of fragments per clone; a fragment outside `root` is left out."""
    clones: list[list[Fragment]] = []
    for run in json.loads(sarif_text)["runs"]:
        bases = _bases(run)
        for result in run.get("results", []):
            fragments: list[Fragment] = []
            for entry in [*result.get("locations", []), *result.get("relatedLocations", [])]:
                physical = entry["physicalLocation"]
                full = _file_uri(physical["artifactLocation"], bases)
                path = _relative(full, root) if full is not None else None
                if path is not None:
                    region = physical["region"]
                    fragments.append(
                        Fragment(path, int(region["startLine"]), int(region["endLine"]))
                    )
            clones.append(fragments)
    return clones


def duplication_added(sarif_text: str, added: Mapping[str, frozenset[int]], root: str) -> int:
    """Distinct added `(path, line)` inside any clone fragment, fragment ends included."""
    counted: set[tuple[str, int]] = set()
    for fragments in clone_fragments(sarif_text, root):
        for fragment in fragments:
            counted.update(
                (fragment.path, line)
                for line in added.get(fragment.path, ())
                if fragment.start <= line <= fragment.end
            )
    return len(counted)


def _rewrite(value: Any, bases: Mapping[str, str], root: str) -> None:
    if isinstance(value, list):
        for item in value:
            _rewrite(item, bases, root)
        return
    if not isinstance(value, dict):
        return
    if isinstance(value.get("uri"), str):
        full = _file_uri(value, bases)
        if full is not None:
            relative = _relative(full, root)
            value["uri"] = relative if relative is not None else PurePosixPath(full).name
            value.pop("uriBaseId", None)
    for item in value.values():
        _rewrite(item, bases, root)


def relative_sarif(text: str, root: str) -> str:
    """The SARIF with every `file://` location relative to `root` and no base URI left.

    A location outside `root` keeps only its file name: no scratch path is stored.
    """
    document = json.loads(text)
    for run in document["runs"]:
        bases = _bases(run)
        run.pop("originalUriBaseIds", None)
        _rewrite(run, bases, root)
    return json.dumps(document, ensure_ascii=False)
