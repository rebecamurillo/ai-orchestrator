"""What a Run recorded about each repository it touched and each commit the orchestrator made.

Side records (AGENTS.md "Data capture"): no status, route, retry or park reads them. Only
`head_pushed` and `head_local_at_end` are ever updated; nothing is deleted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

MadeBy = Literal["wip", "prepare", "git.commit", "git.merge", "session", "operator_edit"]
MADE_BY: tuple[str, ...] = ("wip", "prepare", "git.commit", "git.merge", "session", "operator_edit")
ROOT_PATH = "."


class RunRepositoryRecord(BaseModel):
    """One repository of a Run: the Run's own (`path` `.`) or a submodule member."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    path: str
    remote_url: str
    base_branch: str
    branch: str
    base_tip: str
    head_pushed: str | None = None
    head_local_at_end: str | None = None


class RunCommit(BaseModel):
    """One commit the orchestrator made in a Run's tree."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    path: str
    sha: str
    made_by: MadeBy
    at: datetime
