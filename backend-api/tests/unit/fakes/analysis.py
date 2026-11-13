"""In-memory `AnalysisRepository` (AD-18): no update, no delete, like the port."""

from __future__ import annotations

from uuid import UUID

from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact


class FakeAnalysisRepository:
    def __init__(self) -> None:
        self.rows: list[Analysis] = []
        self.artifacts: list[AnalysisArtifact] = []

    def add(self, analysis: Analysis) -> None:
        self.rows.append(analysis)

    def get(self, analysis_id: UUID) -> Analysis | None:
        return next((a for a in self.rows if a.id == analysis_id), None)

    def list_for_run(self, run_id: UUID) -> list[Analysis]:
        return sorted(
            (a for a in self.rows if a.run_id == run_id),
            key=lambda a: (a.repository_path, a.created_at),
        )

    def list_for_calculation(self, calculation_id: UUID) -> list[Analysis]:
        return [a for a in self.rows if a.calculation_id == calculation_id]

    def add_artifact(self, artifact: AnalysisArtifact) -> None:
        self.artifacts.append(artifact)

    def artifact(self, analysis_id: UUID, tool: str) -> AnalysisArtifact | None:
        return next(
            (a for a in self.artifacts if a.analysis_id == analysis_id and a.tool == tool), None
        )
