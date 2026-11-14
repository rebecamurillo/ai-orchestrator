"""Validate the metric catalogue: pure, every error collected, each naming file and id.

The files arrive as `(file name, yaml text)` pairs; reading them is the infrastructure's job.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import yaml

from orchestrator.domain.ports.catalogue import (
    ENTRY_FIELDS,
    LEVELS,
    METHOD_FIELDS,
    OPTIONAL_ENTRY_FIELDS,
    SCOPES,
    CatalogueEntry,
    CatalogueMethod,
)

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
TEXT_FIELDS = ("label", "unit", "source")
UNKNOWN_ID = "?"


@dataclass(frozen=True)
class CatalogueError:
    file: str
    metric_id: str
    reason: str


class CatalogueInvalid(RuntimeError):
    """Raised with every error found, so one start-up shows the whole list."""

    def __init__(self, errors: tuple[CatalogueError, ...]) -> None:
        self.errors = errors
        super().__init__("\n".join(f"{e.file}: {e.metric_id}: {e.reason}" for e in errors))


def _blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def _check_method(index: int, method: object) -> list[str]:
    where = f"method {index}"
    if not isinstance(method, Mapping):
        return [f"{where} must be a mapping"]
    found = [f"{where}: unknown field {name}" for name in method if name not in METHOD_FIELDS]
    found += [
        f"{where}: missing field {name}" for name in ("n", "description") if name not in method
    ]
    if "description" in method and _blank(method["description"]):
        found.append(f"{where}: description must be non-blank text")
    if "parameters" in method and not isinstance(method["parameters"], Mapping):
        found.append(f"{where}: parameters must be a mapping")
    return found


def _check_numbers(methods: Sequence[object]) -> list[str]:
    numbers = [m["n"] for m in methods if isinstance(m, Mapping) and "n" in m]
    ints = [n for n in numbers if isinstance(n, int) and not isinstance(n, bool) and n >= 1]
    if len(ints) != len(numbers):
        return ["method n must be an integer of at least 1"]
    if any(a >= b for a, b in pairwise(ints)):
        return ["method n must be strictly ascending"]
    return []


def _check_methods(methods: object) -> list[str]:
    if not isinstance(methods, list) or not methods:
        return ["methods must be a non-empty list"]
    found: list[str] = []
    for index, method in enumerate(methods, start=1):
        found += _check_method(index, method)
    return found + _check_numbers(methods)


def _check_shape(entry: Mapping[str, Any]) -> list[str]:
    found = [f"unknown field {name}" for name in entry if name not in ENTRY_FIELDS]
    required = (f for f in ENTRY_FIELDS if f not in OPTIONAL_ENTRY_FIELDS)
    found += [f"missing field {name}" for name in required if name not in entry]
    return found


def _check_values(entry: Mapping[str, Any]) -> list[str]:
    found = [f"{f} must be non-blank text" for f in TEXT_FIELDS if f in entry and _blank(entry[f])]
    if "level" in entry and entry["level"] not in LEVELS:
        found.append(f"level must be one of {', '.join(LEVELS)}")
    if "scopes" in entry:
        scopes = entry["scopes"]
        if not isinstance(scopes, list):
            found.append("scopes must be a list")
        else:
            found += [f"unknown scope {s}" for s in scopes if s not in SCOPES]
    if "additive" in entry and not (
        isinstance(entry["additive"], bool) or entry["additive"] == "within_scope_type"
    ):
        found.append("additive must be true, false or within_scope_type")
    words = entry.get("missing_words", [])
    if not isinstance(words, list) or any(not isinstance(w, str) for w in words):
        found.append("missing_words must be a list of strings")
    if "fingerprint_group" in entry and not isinstance(entry["fingerprint_group"], bool):
        found.append("fingerprint_group must be true or false")
    if entry.get("limits") is not None and not isinstance(entry["limits"], str):
        found.append("limits must be text or null")
    return found


def _check_id(entry: Mapping[str, Any]) -> list[str]:
    metric_id = entry.get("id")
    if not isinstance(metric_id, str) or not ID_PATTERN.match(metric_id):
        return [f"malformed id {metric_id!r}: expected group.name in lower case"]
    if entry.get("group") != metric_id.split(".")[0]:
        return [f"group must equal the id's prefix {metric_id.split('.')[0]}"]
    return []


def check_entry_fields(entry: Mapping[str, Any]) -> list[str]:
    """Every offence of an entry's fields, its id and group aside."""
    return _check_shape(entry) + _check_values(entry) + _check_methods(entry.get("methods"))


def _check_entry(entry: Mapping[str, Any]) -> list[str]:
    return _check_id(entry) + check_entry_fields(entry)


def build_entry(entry: Mapping[str, Any]) -> CatalogueEntry:
    return CatalogueEntry(
        id=entry["id"],
        label=entry["label"],
        group=entry["group"],
        level=entry["level"],
        scopes=tuple(entry["scopes"]),
        unit=entry["unit"],
        source=entry["source"],
        component_of=entry.get("component_of"),
        additive=entry["additive"],
        missing_words=tuple(entry["missing_words"]),
        limits=entry.get("limits"),
        fingerprint_group=entry["fingerprint_group"],
        methods=tuple(
            CatalogueMethod(
                n=m["n"], description=m["description"], parameters=m.get("parameters", {})
            )
            for m in entry["methods"]
        ),
    )


def _parse(file: str, text: str) -> tuple[list[Mapping[str, Any]], list[CatalogueError]]:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return [], [CatalogueError(file, UNKNOWN_ID, f"invalid yaml: {error}")]
    if not isinstance(loaded, list):
        return [], [CatalogueError(file, UNKNOWN_ID, "a catalogue file must be a list of entries")]
    entries: list[Mapping[str, Any]] = []
    errors: list[CatalogueError] = []
    for item in loaded:
        if isinstance(item, Mapping):
            entries.append(item)
        else:
            errors.append(CatalogueError(file, UNKNOWN_ID, "an entry must be a mapping"))
    return entries, errors


def _cross_checks(seen: list[tuple[str, Mapping[str, Any]]]) -> list[CatalogueError]:
    files_by_id: dict[str, list[str]] = {}
    for file, entry in seen:
        files_by_id.setdefault(str(entry.get("id")), []).append(file)
    errors = [
        CatalogueError(files[0], metric_id, f"duplicate id, defined in {', '.join(files)}")
        for metric_id, files in files_by_id.items()
        if len(files) > 1
    ]
    for file, entry in seen:
        target = entry.get("component_of")
        if target is not None and str(target) not in files_by_id:
            errors.append(CatalogueError(file, str(entry.get("id")), f"unknown id {target}"))
    return errors


def validate_catalogue(files: Sequence[tuple[str, str]]) -> tuple[CatalogueEntry, ...]:
    """The entries of every file in order, or `CatalogueInvalid` carrying every error."""
    if not files:
        raise CatalogueInvalid((CatalogueError("", UNKNOWN_ID, "no catalogue files"),))
    errors: list[CatalogueError] = []
    seen: list[tuple[str, Mapping[str, Any]]] = []
    for file, text in files:
        entries, parse_errors = _parse(file, text)
        errors += parse_errors
        for entry in entries:
            seen.append((file, entry))
            errors += [CatalogueError(file, str(entry.get("id")), r) for r in _check_entry(entry)]
    errors += _cross_checks(seen)
    if errors:
        raise CatalogueInvalid(tuple(errors))
    return tuple(build_entry(entry) for _, entry in seen)
