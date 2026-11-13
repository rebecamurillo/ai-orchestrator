"""Port for analyses and their artefacts. Rows are written once: no update, no delete
(AGENTS.md "Data capture")."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact


@runtime_checkable
class AnalysisRepository(Protocol):
    def add(self, analysis: Analysis) -> None: ...

    def list_for_calculation(self, calculation_id: UUID) -> list[Analysis]: ...

    def add_artifact(self, artifact: AnalysisArtifact) -> None: ...

    def artifact(self, analysis_id: UUID, tool: str) -> AnalysisArtifact | None: ...
