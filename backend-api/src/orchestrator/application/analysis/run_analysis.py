"""Analyse every repository a Run worked on, and read the stored analyses back (SPEC CAP-4).

Pure over ports. No unit of work is open while a tool runs: one scope reads the Run's records,
and one scope per repository stores that repository's analysis and its summary.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.inputs import (
    RepositoryInputs,
    attempt_ranges,
    prepare_analysis,
)
from orchestrator.application.analysis.signals import (
    SUMMARY_TOOL,
    RepositorySignals,
    collect_signals,
    signals_from_json,
    signals_to_json,
    store_signals,
)
from orchestrator.application.analysis.tier2 import Tier2Ports
from orchestrator.application.templates.step_metric_model import StepMetric
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.ports.analysis import AnalysisRepository
from orchestrator.domain.ports.analysis_tools import AnalysisTools
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.package_lookup import PackageLookup
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.domain.ports.repositories import AttemptRepository, StepRunRepository
from orchestrator.domain.ports.run_records import RunCommitRepository, RunRepositoryRecords
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.ports.workspace import Workspace

SUMMARY_MEDIA_TYPE = "application/json"
NO_SUMMARY = "no summary stored for this analysis"


def _no_project_env(run_id: UUID) -> Mapping[str, str]:
    return {}


def _no_step_metrics(run_id: UUID) -> Sequence[StepMetric]:
    return ()


@dataclass(frozen=True)
class AnalysisDeps:
    git: Git
    tools: AnalysisTools
    lookup: PackageLookup
    lookups: bool
    scratch_root: Workspace
    work_dir: Path
    clock: Clock
    new_id: Callable[[], UUID]
    runner: ProcessRunner | None = None
    command_timeout_min: float = 20
    project_env: Callable[[UUID], Mapping[str, str]] = _no_project_env
    step_metrics: Callable[[UUID], Sequence[StepMetric]] = _no_step_metrics


@dataclass(frozen=True)
class AnalysisScope:
    steps: StepRunRepository
    attempts: AttemptRepository
    run_records: RunRepositoryRecords
    run_commits: RunCommitRepository
    analyses: AnalysisRepository
    uow: UnitOfWork


AnalysisWrites = Callable[[], AbstractContextManager[AnalysisScope]]


def _first_line(error: Exception) -> str:
    lines = str(error).splitlines()
    return f"{type(error).__name__}: {lines[0] if lines else ''}"


def _collect(
    deps: AnalysisDeps,
    prepared: RepositoryInputs,
    env: Mapping[str, str],
    declared: Sequence[StepMetric],
) -> tuple[Analysis, RepositorySignals]:
    """One repository's failure is that analysis's `failed`, never another's."""
    ports = None if deps.runner is None else Tier2Ports(deps.runner, deps.command_timeout_min, env)
    try:
        return collect_signals(
            prepared,
            git=deps.git,
            scratch_root=deps.scratch_root,
            tools=deps.tools,
            lookup=deps.lookup,
            lookups=deps.lookups,
            now=deps.clock.now(),
            new_id=deps.new_id,
            tier2=ports,
            step_metrics=declared,
        )
    except Exception as error:
        output = _first_line(error)
        failed = prepared.analysis.model_copy(update={"status": "failed", "output": output})
        path = failed.repository_path
        return failed, RepositorySignals(path, "failed", output, ())


def _store(
    deps: AnalysisDeps,
    writes: AnalysisWrites,
    analysis: Analysis,
    signals: RepositorySignals,
) -> None:
    with writes() as scope:
        store_signals(scope.analyses, analysis, signals)
        scope.analyses.add_artifact(
            AnalysisArtifact(
                id=deps.new_id(),
                analysis_id=analysis.id,
                tool=SUMMARY_TOOL,
                media_type=SUMMARY_MEDIA_TYPE,
                body=signals_to_json(signals),
            )
        )
        scope.uow.commit()


def analyse_run(
    deps: AnalysisDeps, writes: AnalysisWrites, run_id: UUID, calculation_id: UUID | None
) -> tuple[Analysis, ...]:
    """Analyse each `run_repository` of the Run; `calculation_id` is `None` while pending."""
    env = deps.project_env(run_id)
    declared = deps.step_metrics(run_id)
    with writes() as scope:
        records = scope.run_records.list_for_run(run_id)
        commits = scope.run_commits.list_for_run(run_id)
        pairs = [
            (attempt, row)
            for row in scope.steps.list_for_run(run_id)
            for attempt in scope.attempts.list_for_row(row.id)
        ]
    ranges = attempt_ranges(pairs, [record.path for record in records])
    stored: list[Analysis] = []
    with prepare_analysis(
        run_id=run_id,
        calculation_id=calculation_id,
        records=records,
        commits=commits,
        ranges=ranges,
        git=deps.git,
        scratch_root=deps.scratch_root,
        work_dir=deps.work_dir,
        new_id=deps.new_id,
        clock=deps.clock,
    ) as prepared:
        for item in prepared:
            analysis, signals = _collect(deps, item, env, declared)
            _store(deps, writes, analysis, signals)
            stored.append(analysis)
    return tuple(stored)


def pending_analyses(analyses: Sequence[Analysis], run_id: UUID) -> list[Analysis]:
    """The newest analysis per repository among the Run's that no calculation owns."""
    newest: dict[str, Analysis] = {}
    for analysis in analyses:
        if analysis.run_id != run_id or analysis.calculation_id is not None:
            continue
        held = newest.get(analysis.repository_path)
        if held is None or analysis.created_at >= held.created_at:
            newest[analysis.repository_path] = analysis
    return sorted(newest.values(), key=lambda a: a.repository_path)


def load_code(
    repository: AnalysisRepository, found: Sequence[Analysis]
) -> tuple[RepositorySignals, ...]:
    """Each analysis's signals as its `summary` artefact kept them."""
    loaded: list[RepositorySignals] = []
    for analysis in found:
        artifact = repository.artifact(analysis.id, SUMMARY_TOOL)
        if artifact is None:
            loaded.append(RepositorySignals(analysis.repository_path, "failed", NO_SUMMARY, ()))
        else:
            loaded.append(signals_from_json(artifact.body))
    return tuple(loaded)
