"""The findings opengrep stored for one analysis (epic 6 story 4)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from orchestrator.application.use_cases.analysis_findings import FindingRow


class FindingOut(BaseModel):
    kind: Literal["security", "bug"]
    rule: str
    path: str
    line: int | None
    severity: Literal["high", "medium", "low"]
    cwe: list[str]
    state: Literal["new", "unchanged", "absent"]


class FindingsOut(BaseModel):
    analysis_id: UUID
    items: list[FindingOut]

    @classmethod
    def of(cls, analysis_id: UUID, rows: list[FindingRow]) -> FindingsOut:
        return cls.model_validate({"analysis_id": analysis_id, "items": [asdict(r) for r in rows]})
