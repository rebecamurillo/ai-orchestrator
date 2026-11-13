"""The `Catalogue` port: every metric described once, with its numbered methods.

An entry is the definition a hint, a stored value and an export all refer to; a method is one
numbered way of computing it. The closed sets below are named here once so the validator and
the API schema cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

LEVELS = ("H", "A")
SCOPES = (
    "run",
    "epic",
    "story",
    "step",
    "attempt",
    "role",
    "model",
    "repository",
    "project",
    "park",
    "gate",
    "tool",
    "conversation",
)
ADDITIVE_VALUES = (True, False, "within_scope_type")
ENTRY_FIELDS = (
    "id",
    "label",
    "group",
    "level",
    "scopes",
    "unit",
    "source",
    "component_of",
    "additive",
    "missing_words",
    "limits",
    "fingerprint_group",
    "methods",
)
#: `component_of` and `limits` may be left out of a file; every other field is required.
OPTIONAL_ENTRY_FIELDS = ("component_of", "limits")
METHOD_FIELDS = ("n", "description", "parameters")


@dataclass(frozen=True)
class CatalogueMethod:
    n: int
    description: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class CatalogueEntry:
    id: str
    label: str
    group: str
    level: str
    scopes: tuple[str, ...]
    unit: str
    source: str
    component_of: str | None
    additive: bool | str
    missing_words: tuple[str, ...]
    limits: str | None
    fingerprint_group: bool
    methods: tuple[CatalogueMethod, ...]


@runtime_checkable
class Catalogue(Protocol):
    """A read-only view of the validated catalogue."""

    def entries(self) -> tuple[CatalogueEntry, ...]:
        """Every entry, in file order."""
        ...
