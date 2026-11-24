"""A Project's installed package: the declaration read from its hub, and the record of it.

Shape only. The rules that decide whether a `package.yaml` may be installed live in
`application/packages/declaration.py` (AD-39).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

StepKind = Literal["conversation", "automatic"]
TemplateTypeName = Literal["interactive", "auto"]
ShownAs = Literal["workflow", "step"]


class StepDecl(BaseModel):
    """One step of a workflow that the initiative page shows: a conversation or the gate."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: StepKind
    skill: str | None
    persona: str | None
    file: str | None
    writes: tuple[str, ...]


class SequenceEntry(BaseModel):
    """One workflow of the package's sequence, as install resolved it."""

    model_config = ConfigDict(frozen=True)

    workflow: str
    template: str
    version: int | None
    type: TemplateTypeName
    shown_as: ShownAs
    steps: tuple[StepDecl, ...]


class GateWords(BaseModel):
    """The words a spec gate answers with, and the key that names an owner."""

    model_config = ConfigDict(frozen=True)

    pass_words: tuple[str, ...]
    fail_words: tuple[str, ...]
    owners_key: str


class PackageDeclaration(BaseModel):
    """What a validated `package.yaml` declares."""

    model_config = ConfigDict(frozen=True)

    name: str
    sequence: tuple[SequenceEntry, ...]
    gate: GateWords
    status_map: Mapping[str, str]


class ProjectPackage(BaseModel):
    """The one package a Project has installed, at the commit install read."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID
    repository_id: UUID
    path: str
    ref: str
    sha: str
    name: str
    declaration: PackageDeclaration
    installed_at: datetime
