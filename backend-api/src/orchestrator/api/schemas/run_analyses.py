"""The analyses behind a Run's shown result version (epic 5 story 5)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.metrics_compare import ToolVersionOut
from orchestrator.application.use_cases.run_analyses import RunAnalyses


class AnalysisOut(BaseModel):
    analysis_id: UUID
    repository_path: str
    status: str
    reason: str
    base: str | None
    head: str | None
    base_branch: str | None
    languages: list[str] | None
    commits_outside_run: int | None
    tools: list[ToolVersionOut]
    vulnerability_db_date: date | None
    lookup_date: date | None
    declaration_hash: str | None
    sarif_tools: list[str]


class RunAnalysesOut(BaseModel):
    run_id: UUID
    version: int | None
    items: list[AnalysisOut]

    @classmethod
    def of(cls, analyses: RunAnalyses) -> RunAnalysesOut:
        return cls.model_validate(asdict(analyses))
