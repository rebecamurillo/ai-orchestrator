"""SQLAlchemy adapter for analyses: insert and read only. `body` is zlib-compressed here."""

from __future__ import annotations

import zlib
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.infrastructure.db.models.analysis import AnalysisArtifactRow, AnalysisRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def _analysis(row: AnalysisRow) -> Analysis:
    return Analysis(
        id=row.id,
        run_id=row.run_id,
        calculation_id=row.calculation_id,
        repository_path=row.repository_path,
        base=row.base,
        head=row.head,
        toolset=tuple(row.toolset),
        toolset_fingerprint=row.toolset_fingerprint,
        declaration_hash=row.declaration_hash,
        status=row.status,  # type: ignore[arg-type]
        output=row.output,
        created_at=row.created_at,
    )


class SQLAlchemyAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, analysis: Analysis) -> None:
        self._session.add(
            AnalysisRow(
                id=analysis.id,
                run_id=analysis.run_id,
                calculation_id=analysis.calculation_id,
                repository_path=analysis.repository_path,
                base=analysis.base,
                head=analysis.head,
                toolset=list(analysis.toolset),
                toolset_fingerprint=analysis.toolset_fingerprint,
                declaration_hash=analysis.declaration_hash,
                status=analysis.status,
                output=analysis.output,
                created_at=analysis.created_at,
            )
        )
        self._session.flush()

    def list_for_calculation(self, calculation_id: UUID) -> list[Analysis]:
        rows = self._session.scalars(
            select(AnalysisRow)
            .where(AnalysisRow.calculation_id == calculation_id)
            .order_by(AnalysisRow.repository_path)
        ).all()
        return [_analysis(row) for row in rows]

    def add_artifact(self, artifact: AnalysisArtifact) -> None:
        self._session.add(
            AnalysisArtifactRow(
                id=artifact.id,
                analysis_id=artifact.analysis_id,
                tool=artifact.tool,
                media_type=artifact.media_type,
                body=zlib.compress(artifact.body),
            )
        )
        self._session.flush()

    def artifact(self, analysis_id: UUID, tool: str) -> AnalysisArtifact | None:
        row = self._session.scalars(
            select(AnalysisArtifactRow).where(
                AnalysisArtifactRow.analysis_id == analysis_id, AnalysisArtifactRow.tool == tool
            )
        ).first()
        if row is None:
            return None
        return AnalysisArtifact(
            id=row.id,
            analysis_id=row.analysis_id,
            tool=row.tool,
            media_type=row.media_type,
            body=zlib.decompress(row.body),
        )
