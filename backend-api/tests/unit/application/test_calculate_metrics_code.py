"""Part C inside the calculation job: pending analyses at v1, a fresh analysis when manual
(epic 5 story 4, AC4, AC5)."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from uuid import UUID

from orchestrator.application.analysis.signals import (
    SUMMARY_TOOL,
    RepositorySignals,
    signals_to_json,
)
from orchestrator.application.analysis.tier1a import Count
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.ids import new_id
from tests.unit.application.metrics_fixed_run import RUN_ID
from tests.unit.application.test_calculate_metrics_job import Job, a_job, state_of
from tests.unit.fakes.analysis import FakeAnalysisRepository

LINES = "code.lines_added"
SEVEN = 7
THREE = 3


def stored(  # noqa: PLR0913 — one keyword per fixture a case varies
    repository: FakeAnalysisRepository,
    job: Job,
    *,
    path: str = ".",
    fingerprint: str = "fp",
    calculation: UUID | None = None,
    lines: int = SEVEN,
) -> Analysis:
    analysis = Analysis(
        id=new_id(),
        run_id=RUN_ID,
        calculation_id=calculation,
        repository_path=path,
        status="ok",
        toolset_fingerprint=fingerprint,
        created_at=job.ports.clock.now(),
    )
    repository.add(analysis)
    signals = RepositorySignals(path, "ok", "", (Count(LINES, "production", lines, None),))
    repository.add_artifact(
        AnalysisArtifact(
            id=new_id(),
            analysis_id=analysis.id,
            tool=SUMMARY_TOOL,
            media_type="application/json",
            body=signals_to_json(signals),
        )
    )
    return analysis


def code_ids(job: Job, version_id: UUID) -> set[str]:
    return {v.metric_id for v in job.versions.values(version_id) if v.metric_id.startswith("code.")}


def with_analyses(job: Job, run_analysis=None) -> FakeAnalysisRepository:  # type: ignore[no-untyped-def]
    repository = FakeAnalysisRepository()
    job.ports = replace(job.ports, analyses=repository, analysis=run_analysis)
    return repository


def test_v1_uses_the_pending_analyses_and_adds_the_workflow_step() -> None:  # AC4
    job = a_job()
    repository = with_analyses(job)
    pending = stored(repository, job, fingerprint="fp1", lines=SEVEN)

    job.calculate()

    [version] = job.versions.list_for_run(RUN_ID)
    assert version.entry_point == ("at_attempt_end", "workflow_step")
    assert version.analysis_ids == (pending.id,)
    assert version.toolset_fingerprint == hashlib.sha256(b"fp1").hexdigest()
    assert LINES in code_ids(job, version.id)
    added = next(
        v.value_num
        for v in job.versions.values(version.id)
        if v.metric_id == LINES and v.scope_type == "run"
    )
    assert added == SEVEN


def test_v1_never_analyses_and_ignores_analyses_a_calculation_owns() -> None:
    job = a_job()
    called: list[object] = []
    repository = with_analyses(job, lambda *args: called.append(args) or [])
    calculation = job.queue(n=2)
    stored(repository, job, calculation=calculation)

    job.calculate()

    [version] = job.versions.list_for_run(RUN_ID)
    assert called == []
    assert version.analysis_ids == ()


def test_v1_without_a_pending_analysis_keeps_its_entry_point_and_has_no_fingerprint() -> None:
    job = a_job()
    with_analyses(job)

    job.calculate()

    [version] = job.versions.list_for_run(RUN_ID)
    assert version.entry_point == ("at_attempt_end",)
    assert version.analysis_ids == ()
    assert version.toolset_fingerprint is None


def test_a_job_without_the_analysis_ports_calculates_as_before() -> None:
    job = a_job()

    job.calculate()

    [version] = job.versions.list_for_run(RUN_ID)
    assert version.entry_point == ("at_attempt_end",)
    assert version.toolset_fingerprint is None


def test_a_manual_calculation_analyses_afresh_under_its_own_id() -> None:  # AC5
    job = a_job()
    repository = with_analyses(job)
    asked: list[tuple[UUID, UUID]] = []

    def analyse(run_id: UUID, calculation_id: UUID) -> list[Analysis]:
        asked.append((run_id, calculation_id))
        return [
            stored(repository, job, path="b", fingerprint="b", calculation=calculation_id),
            stored(repository, job, path="a", fingerprint="a", calculation=calculation_id),
            stored(repository, job, path="c", fingerprint="a", calculation=calculation_id),
        ]

    job.ports = replace(job.ports, analysis=analyse)
    stale = stored(repository, job, fingerprint="stale")

    calculation_id = job.calculate(2)

    [version] = job.versions.list_for_run(RUN_ID)
    assert asked == [(RUN_ID, calculation_id)]
    assert version.entry_point == ("manual",)
    assert stale.id not in version.analysis_ids
    assert len(version.analysis_ids) == THREE
    assert version.toolset_fingerprint == hashlib.sha256(b"a\nb").hexdigest()
    assert LINES in code_ids(job, version.id)
    assert state_of(job, calculation_id).entry_point == ("manual",)


def test_a_manual_calculation_without_the_analysis_port_reads_the_pending_ones() -> None:
    job = a_job()
    repository = with_analyses(job)
    pending = stored(repository, job)

    job.calculate(2)

    [version] = job.versions.list_for_run(RUN_ID)
    assert version.entry_point == ("manual", "workflow_step")
    assert version.analysis_ids == (pending.id,)
