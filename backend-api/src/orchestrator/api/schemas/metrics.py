"""Payloads of the metrics catalogue endpoint (AD-3): the contract is these models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from orchestrator.domain.ports.catalogue import CatalogueEntry, CatalogueMethod


class CatalogueMethodOut(BaseModel):
    n: int
    description: str
    parameters: dict[str, Any]

    @classmethod
    def from_method(cls, method: CatalogueMethod) -> CatalogueMethodOut:
        return cls(n=method.n, description=method.description, parameters=dict(method.parameters))


class CatalogueEntryOut(BaseModel):
    id: str
    label: str
    group: str
    level: Literal["H", "A"]
    scopes: list[str]
    unit: str
    source: str
    component_of: str | None
    additive: bool | Literal["within_scope_type"]
    missing_words: list[str]
    limits: str | None
    fingerprint_group: bool
    methods: list[CatalogueMethodOut]

    @classmethod
    def from_entry(cls, entry: CatalogueEntry) -> CatalogueEntryOut:
        return cls(
            id=entry.id,
            label=entry.label,
            group=entry.group,
            level=entry.level,  # type: ignore[arg-type]
            scopes=list(entry.scopes),
            unit=entry.unit,
            source=entry.source,
            component_of=entry.component_of,
            additive=entry.additive,  # type: ignore[arg-type]
            missing_words=list(entry.missing_words),
            limits=entry.limits,
            fingerprint_group=entry.fingerprint_group,
            methods=[CatalogueMethodOut.from_method(m) for m in entry.methods],
        )
