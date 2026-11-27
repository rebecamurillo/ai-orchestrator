"""An initiative: facts about one piece of work and the Runs it produced (AD-36).

There is no status field. The status is computed from the Runs and the advances.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from orchestrator.domain.entities.project_package import (
    GateWords,
    ShownAs,
    StepDecl,
    TemplateTypeName,
)


class FrozenWorkflow(BaseModel):
    """One workflow of the sequence as it stood when the initiative was created."""

    model_config = ConfigDict(frozen=True)

    workflow: str
    template: str
    version: int
    type: TemplateTypeName
    shown_as: ShownAs
    steps: tuple[StepDecl, ...]


class FrozenSequence(BaseModel):
    """The package's sequence, frozen at creation."""

    model_config = ConfigDict(frozen=True)

    package: str
    sha: str
    workflows: tuple[FrozenWorkflow, ...]
    gate: GateWords
    status_map: Mapping[str, str]


class InitiativeKey(BaseModel):
    """The idempotency key of one initiative step's Run."""

    model_config = ConfigDict(frozen=True)

    initiative_id: UUID
    round: int
    position: int


class Initiative(BaseModel):
    """One initiative."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    project_id: UUID
    repository_id: UUID
    slug: str
    name: str
    first_message: str
    sequence: FrozenSequence
    round: int = 1
    cancelled_at: datetime | None = None
    branch_cleanup_error: str | None = None
    pr_merged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None
    last_opened_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.cancelled_at is None and self.pr_merged_at is None
