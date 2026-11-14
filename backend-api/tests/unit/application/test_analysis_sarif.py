"""`read_sarif`: the stored SARIF of one analysis, or `NotFound` (epic 5 story 4, AC6)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from orchestrator.application.use_cases.analysis_sarif import read_sarif
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.errors import NotFound
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.db import FakeUnitOfWork

RUN = UUID(int=1)
ANALYSIS = UUID(int=2)
SARIF = b'{"version": "2.1.0"}'


def repository() -> FakeAnalysisRepository:
    fake = FakeAnalysisRepository()
    fake.add(
        Analysis(
            id=ANALYSIS,
            run_id=RUN,
            repository_path=".",
            status="ok",
            created_at=datetime(2026, 11, 13, tzinfo=UTC),
        )
    )
    fake.add_artifact(
        AnalysisArtifact(
            id=UUID(int=3),
            analysis_id=ANALYSIS,
            tool="gitleaks",
            media_type="application/sarif+json",
            body=SARIF,
        )
    )
    fake.add_artifact(
        AnalysisArtifact(
            id=UUID(int=4),
            analysis_id=ANALYSIS,
            tool="summary",
            media_type="application/json",
            body=b"{}",
        )
    )
    return fake


def test_the_stored_sarif_comes_back_whole() -> None:
    assert read_sarif(repository(), FakeUnitOfWork(), RUN, ANALYSIS, "gitleaks") == SARIF


@pytest.mark.parametrize(
    ("run", "analysis", "tool"),
    [
        (UUID(int=9), ANALYSIS, "gitleaks"),
        (RUN, UUID(int=9), "gitleaks"),
        (RUN, ANALYSIS, "osv-scanner"),
        (RUN, ANALYSIS, "summary"),
    ],
    ids=["other run", "no analysis", "no artifact", "not sarif"],
)
def test_anything_else_is_not_found(run: UUID, analysis: UUID, tool: str) -> None:
    with pytest.raises(NotFound):
        read_sarif(repository(), FakeUnitOfWork(), run, analysis, tool)
