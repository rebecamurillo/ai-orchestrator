"""`/projects/{id}/package` payloads (SPEC CAP-3, AD-39)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.api.schemas.common import StorableText, UtcTimestamp
from orchestrator.domain.entities.project_package import (
    GateWords,
    ProjectPackage,
    SequenceEntry,
    StepDecl,
)
from orchestrator.domain.entities.repository import Repository


class PackageIn(BaseModel):
    """Where the package is: a folder of the Project's hub repository, at a branch."""

    model_config = ConfigDict(extra="forbid")

    repository_id: UUID
    path: StorableText
    ref: Annotated[StorableText, Field(min_length=1)]


class StepDeclOut(BaseModel):
    id: str
    kind: Literal["conversation", "automatic"]
    skill: str | None
    persona: str | None
    file: str | None
    writes: list[str]

    @classmethod
    def of(cls, step: StepDecl) -> StepDeclOut:
        return cls(
            id=step.id,
            kind=step.kind,
            skill=step.skill,
            persona=step.persona,
            file=step.file,
            writes=list(step.writes),
        )


class SequenceEntryOut(BaseModel):
    workflow: str
    template: str
    version: int | None
    type: Literal["interactive", "auto"]
    shown_as: Literal["workflow", "step"]
    steps: list[StepDeclOut]

    @classmethod
    def of(cls, entry: SequenceEntry) -> SequenceEntryOut:
        return cls(
            workflow=entry.workflow,
            template=entry.template,
            version=entry.version,
            type=entry.type,
            shown_as=entry.shown_as,
            steps=[StepDeclOut.of(step) for step in entry.steps],
        )


class GateOut(BaseModel):
    """The gate words; `pass` is a Python keyword, so the field is aliased."""

    model_config = ConfigDict(populate_by_name=True)

    pass_: list[str] = Field(alias="pass")
    fail: list[str]
    owners_key: str

    @classmethod
    def of(cls, gate: GateWords) -> GateOut:
        return cls(
            pass_=list(gate.pass_words), fail=list(gate.fail_words), owners_key=gate.owners_key
        )


class PackageRepositoryOut(BaseModel):
    """The hub the package was read from."""

    id: UUID
    slug: str
    default_branch: str
    initiative_folder: str

    @classmethod
    def of(cls, repository: Repository) -> PackageRepositoryOut:
        return cls(
            id=repository.id,
            slug=repository.slug,
            default_branch=repository.default_branch,
            initiative_folder=repository.initiative_folder,
        )


class PackageOut(BaseModel):
    id: UUID
    project_id: UUID
    repository_id: UUID
    path: str
    ref: str
    sha: str
    name: str
    installed_at: UtcTimestamp
    repository: PackageRepositoryOut
    sequence: list[SequenceEntryOut]
    gate: GateOut
    status_map: dict[str, str]

    @classmethod
    def of(cls, package: ProjectPackage, repository: Repository) -> PackageOut:
        declaration = package.declaration
        return cls(
            id=package.id,
            project_id=package.project_id,
            repository_id=package.repository_id,
            path=package.path,
            ref=package.ref,
            sha=package.sha,
            name=package.name,
            installed_at=package.installed_at,
            repository=PackageRepositoryOut.of(repository),
            sequence=[SequenceEntryOut.of(entry) for entry in declaration.sequence],
            gate=GateOut.of(declaration.gate),
            status_map=dict(declaration.status_map),
        )
