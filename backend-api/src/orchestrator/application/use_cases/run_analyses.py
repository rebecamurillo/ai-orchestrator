"""The analyses behind a Run's shown result version, for the METRICS tab (epic 5 story 5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from orchestrator.application.analysis.dependencies import OSV_SCANNER
from orchestrator.application.analysis.findings import OPENGREP
from orchestrator.application.analysis.secrets import GITLEAKS
from orchestrator.application.analysis.signals import SUMMARY_TOOL, signals_from_json
from orchestrator.application.analysis.tier1b import JSCPD
from orchestrator.application.analysis.toolset import DECLARATION_HASH, RULE_PACK_HASH
from orchestrator.application.metrics.compare_views import ToolVersion
from orchestrator.application.templates.step_metrics import declared_step_metrics
from orchestrator.application.use_cases.analysis_sarif import SARIF_MEDIA_TYPE
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.entities.run_records import ROOT_PATH
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.analysis import AnalysisRepository
from orchestrator.domain.ports.catalogue import CatalogueEntry
from orchestrator.domain.ports.metric_results import ResultVersionRepository
from orchestrator.domain.ports.repositories import RunRepository
from orchestrator.domain.ports.run_records import RunRepositoryRecords
from orchestrator.domain.ports.templates import TemplateVersionRepository

SARIF_TOOLS = (GITLEAKS, OSV_SCANNER, JSCPD, OPENGREP)


@dataclass(frozen=True)
class RunAnalysesPorts:
    runs: RunRepository
    versions: ResultVersionRepository
    analyses: AnalysisRepository
    run_records: RunRepositoryRecords
    templates: TemplateVersionRepository | None = None


@dataclass(frozen=True)
class AnalysisView:
    analysis_id: UUID
    repository_path: str
    status: str
    reason: str
    base: str | None
    head: str | None
    base_branch: str | None
    languages: list[str] | None
    commits_outside_run: int | None
    tools: list[ToolVersion]
    vulnerability_db_date: date | None
    lookup_date: date | None
    declaration_hash: str | None
    sarif_tools: list[str]
    rule_pack_hash: str | None


@dataclass(frozen=True)
class RunAnalyses:
    run_id: UUID
    version: int | None
    items: list[AnalysisView]
    step_entries: tuple[CatalogueEntry, ...] = ()


def _date(value: object) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _reason(analysis: Analysis) -> str:
    lines = analysis.output.splitlines() if analysis.status != "ok" else []
    return lines[0] if lines else ""


def _view(ports: RunAnalysesPorts, analysis: Analysis) -> AnalysisView:
    summary = ports.analyses.artifact(analysis.id, SUMMARY_TOOL)
    signals = None if summary is None else signals_from_json(summary.body)
    record = ports.run_records.get(analysis.run_id, analysis.repository_path)
    dates: dict[str, object] = {}
    for entry in analysis.toolset:
        if "tool" not in entry:
            dates = dict(entry)
    sarif = [
        tool
        for tool in SARIF_TOOLS
        if (found := ports.analyses.artifact(analysis.id, tool)) is not None
        and found.media_type == SARIF_MEDIA_TYPE
    ]
    commits = None if signals is None else signals.commits_not_made_by_run
    return AnalysisView(
        analysis_id=analysis.id,
        repository_path=analysis.repository_path,
        status=analysis.status,
        reason=_reason(analysis),
        base=analysis.base,
        head=analysis.head,
        base_branch=None if record is None else record.base_branch,
        languages=None if signals is None or signals.languages is None else list(signals.languages),
        commits_outside_run=None if commits is None else len(commits),
        tools=[
            ToolVersion(str(entry["tool"]), str(entry["version"]))
            for entry in analysis.toolset
            if "tool" in entry
        ],
        vulnerability_db_date=_date(dates.get("vulnerability_db_date")),
        lookup_date=_date(dates.get("lookup_date")),
        declaration_hash=_text(dates.get(DECLARATION_HASH)) or analysis.declaration_hash,
        sarif_tools=sarif,
        rule_pack_hash=next(
            (_text(e.get(RULE_PACK_HASH)) for e in analysis.toolset if e.get("tool") == OPENGREP),
            None,
        ),
    )


def _step_entries(ports: RunAnalysesPorts, run_id: UUID) -> tuple[CatalogueEntry, ...]:
    if ports.templates is None:
        return ()
    return tuple(m.entry for m in declared_step_metrics(ports.runs, ports.templates, run_id))


def run_analyses(ports: RunAnalysesPorts, run_id: UUID, v: int | None) -> RunAnalyses:
    """The newest version's analyses, or version `v`'s; `.` first, then by path."""
    if ports.runs.get(run_id) is None:
        raise NotFound(f"no run {run_id}")
    if v is None:
        version = ports.versions.latest(run_id)
    else:
        version = ports.versions.get(run_id, v)
        if version is None:
            raise NotFound(f"run {run_id} has no version {v}")
    entries = _step_entries(ports, run_id)
    if version is None:
        return RunAnalyses(run_id, None, [], entries)
    found = [a for i in version.analysis_ids if (a := ports.analyses.get(i)) is not None]
    found.sort(key=lambda a: (a.repository_path != ROOT_PATH, a.repository_path))
    return RunAnalyses(run_id, version.n, [_view(ports, a) for a in found], entries)
