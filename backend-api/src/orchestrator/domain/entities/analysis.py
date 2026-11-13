"""What one calculation read of one repository, and the artefacts its tools produced."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

AnalysisStatus = Literal["ok", "partial", "failed"]


class Analysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    run_id: UUID
    calculation_id: UUID
    repository_path: str
    base: str | None = None
    head: str | None = None
    toolset: tuple[dict[str, Any], ...] = ()
    toolset_fingerprint: str = ""
    declaration_hash: str | None = None
    status: AnalysisStatus
    output: str = ""
    created_at: datetime


class AnalysisArtifact(BaseModel):
    """`body` is the uncompressed bytes; compression is the adapter's."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    analysis_id: UUID
    tool: str
    media_type: str
    body: bytes
