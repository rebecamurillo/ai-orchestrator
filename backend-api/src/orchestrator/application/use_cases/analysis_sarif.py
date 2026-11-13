"""Read one stored SARIF report of an analysis (SPEC CAP-4)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.analysis import AnalysisRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork

SARIF_MEDIA_TYPE = "application/sarif+json"


@dataclass(frozen=True)
class AnalysisReadPorts:
    analyses: AnalysisRepository
    uow: UnitOfWork


def read_sarif(
    analyses: AnalysisRepository, uow: UnitOfWork, run_id: UUID, analysis_id: UUID, tool: str
) -> bytes:
    """The SARIF the tool wrote for the analysis; `summary` and unknown tools are not served."""
    with uow:
        analysis = analyses.get(analysis_id)
        if analysis is None or analysis.run_id != run_id:
            raise NotFound(f"run {run_id} has no analysis {analysis_id}")
        artifact = analyses.artifact(analysis_id, tool)
        if artifact is None or artifact.media_type != SARIF_MEDIA_TYPE:
            raise NotFound(f"analysis {analysis_id} has no SARIF report from {tool}")
        return artifact.body
