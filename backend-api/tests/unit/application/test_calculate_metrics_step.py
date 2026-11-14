"""A calculation with step-produced metrics: values, `methods` and output (epic 6 story 3)."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.analysis.signals import (
    SUMMARY_TOOL,
    RepositorySignals,
    signals_to_json,
)
from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.ids import new_id
from tests.unit.application.metrics_fixed_run import RUN_ID
from tests.unit.application.test_calculate_metrics_job import Job, a_job, state_of
from tests.unit.fakes.analysis import FakeAnalysisRepository

ID = "step.bench-v1.heldout_tests"
EIGHTEEN, TWO = 18, 2


def with_summary(job: Job, signals: RepositorySignals) -> None:
    repository = FakeAnalysisRepository()
    analysis = Analysis(
        id=new_id(),
        run_id=RUN_ID,
        repository_path=signals.path,
        status="ok",
        toolset_fingerprint="fp",
        created_at=job.ports.clock.now(),
    )
    repository.add(analysis)
    repository.add_artifact(
        AnalysisArtifact(
            id=new_id(),
            analysis_id=analysis.id,
            tool=SUMMARY_TOOL,
            media_type="application/json",
            body=signals_to_json(signals),
        )
    )
    job.ports = replace(job.ports, analyses=repository)


def test_declared_values_are_stored_under_their_own_method_and_listed_in_methods() -> None:  # AC3
    job = a_job()
    counts = (
        Count(ID, "passed", EIGHTEEN, None),
        Count(ID, "failed", TWO, None),
        Count(ID, "errored", 0, None),
        Count(ID, "skipped", 0, None),
    )
    with_summary(job, RepositorySignals(".", "ok", "", counts))

    calculation_id = job.calculate()

    [version] = job.versions.list_for_run(RUN_ID)
    mine = {v.source: v for v in job.versions.values(version.id) if v.metric_id == ID}
    assert {s: v.value_num for s, v in mine.items()} == {
        "passed": EIGHTEEN,
        "failed": TWO,
        "errored": 0,
        "skipped": 0,
    }
    assert {v.method_id for v in mine.values()} == {f"{ID}@1"}
    assert version.methods == tuple(sorted({*REGISTRY, f"{ID}@1"}))
    assert (
        state_of(job, calculation_id).output == f"v1: {len(job.versions.values(version.id))} values"
    )


def test_an_undeclared_file_is_named_in_the_output_and_stores_no_value() -> None:  # AC6
    job = a_job()
    with_summary(
        job, RepositorySignals(".", "ok", "", (), not_catalogued=("a.xml", "out/other.xml"))
    )

    calculation_id = job.calculate()

    [version] = job.versions.list_for_run(RUN_ID)
    stored = job.versions.values(version.id)
    assert state_of(job, calculation_id).output == (
        f"v1: {len(stored)} values\nnot catalogued: a.xml\nnot catalogued: out/other.xml"
    )
    assert not any(v.metric_id.startswith("step.") for v in stored)
    assert version.methods == tuple(sorted(REGISTRY))
