"""What a Run recorded about each repository it touched and each commit the orchestrator made.

Side records (AGENTS.md "Data capture"): no status, route, retry or park reads them. Only
`head_pushed` and `head_local_at_end` are ever updated; nothing is deleted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

MadeBy = Literal["wip", "prepare", "git.commit", "git.merge", "session", "operator_edit"]
MADE_BY: tuple[str, ...] = ("wip", "prepare", "git.commit", "git.merge", "session", "operator_edit")
ROOT_PATH = "."


class RunRepositoryRecord(BaseModel):
    """One repository of a Run: the Run's own (`path` `.`) or a submodule member.

    `branch` and `base_tip` are `None` when unknown: a Run without a `branch` input, or a base
    tip `ls_remote` could not read. An empty string is read as unknown, built or loaded.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    path: str
    remote_url: str
    base_branch: str
    branch: str | None = None
    base_tip: str | None = None
    head_pushed: str | None = None
    head_local_at_end: str | None = None

    @field_validator("branch", "base_tip", mode="before")
    @classmethod
    def _empty_is_unknown(cls, value: object) -> object:
        return None if value == "" else value


class RunCommit(BaseModel):
    """One commit the orchestrator made in a Run's tree."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    path: str
    sha: str
    made_by: MadeBy
    at: datetime
