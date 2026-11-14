"""Lock files and manifests read as `package name → versions` (ARCHITECTURE §7.2).

A file that cannot be read yields no packages and a one-line problem; the caller decides what
that means for the signal.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import yaml

LOCK_ECOSYSTEM = {
    "package-lock.json": "npm",
    "pnpm-lock.yaml": "npm",
    "uv.lock": "pypi",
    "poetry.lock": "pypi",
}
MANIFEST_ECOSYSTEM = {"package.json": "npm", "pyproject.toml": "pypi"}
NPM_TABLES = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
NODE_MODULES = "node_modules/"
UNINSTALLED_SOURCES = ("editable", "virtual")
REQUIREMENT_END = re.compile(r"[ <>=!~;\[(@]")
_SEPARATORS = re.compile(r"[-_.]+")


@dataclass(frozen=True)
class ParsedDeps:
    packages: Mapping[str, frozenset[str]]
    problem: str | None = None


def normalise_pypi(name: str) -> str:
    """PEP 503."""
    return _SEPARATORS.sub("-", name).lower()


def _collect(pairs: list[tuple[str, str]]) -> dict[str, frozenset[str]]:
    found: dict[str, set[str]] = {}
    for name, version in pairs:
        found.setdefault(name, set()).add(version)
    return {name: frozenset(versions) for name, versions in found.items()}


def _unreadable(name: str) -> ParsedDeps:
    return ParsedDeps({}, f"{name}: not parseable")


def _npm_v1(dependencies: Any) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not isinstance(dependencies, dict):
        return pairs
    for name, entry in dependencies.items():
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("version"), str):
            pairs.append((name, entry["version"]))
        pairs += _npm_v1(entry.get("dependencies", {}))
    return pairs


def _package_lock(name: str, text: str) -> ParsedDeps:
    try:
        document = json.loads(text)
    except ValueError:
        return _unreadable(name)
    if not isinstance(document, dict):
        return _unreadable(name)
    if "packages" not in document:
        return ParsedDeps(_collect(_npm_v1(document.get("dependencies", {}))))
    if not isinstance(document["packages"], dict):
        return _unreadable(name)
    pairs = [
        (key.rsplit(NODE_MODULES, 1)[-1], entry["version"])
        for key, entry in document["packages"].items()
        if key and isinstance(entry, dict) and isinstance(entry.get("version"), str)
    ]
    return ParsedDeps(_collect(pairs))


def _pnpm_key(key: str, *, v5: bool) -> tuple[str, str]:
    bare = key.lstrip("/").split("(")[0]
    if v5:
        package, _, version = bare.rpartition("/")
        return package, version.split("_")[0]
    # The version may be a tarball or git URL holding `@` (and a credential): split at the
    # first `@` after a scope's leading one, never the last.
    at = bare.find("@", 1)
    return (bare, "") if at < 0 else (bare[:at], bare[at + 1 :])


def _pnpm_lock(name: str, text: str) -> ParsedDeps:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return _unreadable(name)
    if not isinstance(document, dict):
        return _unreadable(name)
    v5 = str(document.get("lockfileVersion", "")).startswith("5")
    keys = document.get("packages") or {}
    if not isinstance(keys, dict):
        return _unreadable(name)
    return ParsedDeps(_collect([_pnpm_key(str(key), v5=v5) for key in keys]))


def _toml_lock(name: str, text: str) -> ParsedDeps:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return _unreadable(name)
    entries = document.get("package", [])
    if not isinstance(entries, list):
        return _unreadable(name)
    pairs = [
        (normalise_pypi(entry["name"]), entry["version"])
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and isinstance(entry.get("version"), str)
        and not (
            isinstance(entry.get("source"), dict)
            and any(key in entry["source"] for key in UNINSTALLED_SOURCES)
        )
    ]
    return ParsedDeps(_collect(pairs))


def _guarded(parser: Callable[[str, str], ParsedDeps], name: str, text: str) -> ParsedDeps:
    """A file nested deeper than the parsers recurse is unparseable, not a crash."""
    try:
        return parser(name, text)
    except RecursionError:
        return _unreadable(name)


_LOCK_PARSERS: dict[str, Callable[[str, str], ParsedDeps]] = {
    "package-lock.json": _package_lock,
    "pnpm-lock.yaml": _pnpm_lock,
    "uv.lock": _toml_lock,
    "poetry.lock": _toml_lock,
}


def parse_lock(name: str, text: str | None) -> ParsedDeps:
    """`name` is the file's basename; no text or an unknown name holds no packages."""
    parser = _LOCK_PARSERS.get(name)
    if text is None or parser is None:
        return ParsedDeps({})
    return _guarded(parser, name, text)


def _package_json(name: str, text: str) -> ParsedDeps:
    try:
        document = json.loads(text)
    except ValueError:
        return _unreadable(name)
    if not isinstance(document, dict):
        return _unreadable(name)
    pairs = [
        (package, spec)
        for table in NPM_TABLES
        if isinstance(document.get(table), dict)
        for package, spec in document[table].items()
        if isinstance(spec, str)
    ]
    return ParsedDeps(_collect(pairs))


def _requirement(entry: object) -> tuple[str, str] | None:
    if not isinstance(entry, str):
        return None
    ended = REQUIREMENT_END.search(entry)
    package = entry if ended is None else entry[: ended.start()]
    if not package:
        return None
    return normalise_pypi(package), "" if ended is None else entry[ended.start() :].strip()


def _pyproject(name: str, text: str) -> ParsedDeps:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return _unreadable(name)
    project = document.get("project")
    if not isinstance(project, dict):
        return ParsedDeps({})
    optional = project.get("optional-dependencies")
    lists: list[object] = [project.get("dependencies")]
    lists += list(optional.values()) if isinstance(optional, dict) else []
    requirements = (
        _requirement(entry) for entries in lists if isinstance(entries, list) for entry in entries
    )
    return ParsedDeps(_collect([pair for pair in requirements if pair is not None]))


_MANIFEST_PARSERS: dict[str, Callable[[str, str], ParsedDeps]] = {
    "package.json": _package_json,
    "pyproject.toml": _pyproject,
}


def parse_manifest(name: str, text: str | None) -> ParsedDeps:
    """Name → the specifier strings, not resolved versions."""
    parser = _MANIFEST_PARSERS.get(name)
    if text is None or parser is None:
        return ParsedDeps({})
    return _guarded(parser, name, text)
