"""The comparison of selected Runs and its export rows (epic 4 story 1; ARCHITECTURE §6.1, §6.4).

Every figure is a projection of stored `metric_value` rows or stored Run totals; blind is
applied here once, so the payload and both files are free of what it hides.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from orchestrator.application.metrics.blind import HIDDEN, blind_label, blind_value
from orchestrator.application.metrics.compare_views import (
    CompareCell,
    CompareMetric,
    CompareRunHeader,
    Comparison,
    ExportResult,
    FamilyCellView,
    FamilyView,
    SameWork,
    SameWorkRun,
    StoriesDone,
)
from orchestrator.application.metrics.export_rows import (
    ExportSource,
    catalogue_for,
    to_export_row,
)
from orchestrator.application.metrics.families import (
    FamilyResult,
    InStory,
    family_applies,
    family_results,
    orchestrate_in_story,
)
from orchestrator.application.metrics.subscription import run_subscription
from orchestrator.domain.entities.metric_results import ResultVersion, StoredMetricValue
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Invalid, NotFound
from orchestrator.domain.ports.catalogue import Catalogue, CatalogueEntry
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.facts import FactSetRepository
from orchestrator.domain.ports.metric_results import ResultVersionRepository
from orchestrator.domain.ports.repositories import (
    ProjectRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.run_records import RunRepositoryRecords

NOT_RUN = "not run"
STORIES_DONE = "process.stories_done"
COST_GATEWAY = "cost.gateway"
COST_HARNESS = "cost.harness"
CENT = Decimal("0.01")
SHORT_ID = 8


@dataclass(frozen=True)
class MetricsComparePorts:
    projects: ProjectRepository
    runs: RunRepository
    steps: StepRunRepository
    versions: ResultVersionRepository
    fact_sets: FactSetRepository
    run_records: RunRepositoryRecords
    catalogue: Catalogue
    clock: Clock


@dataclass(frozen=True)
class CompareQuery:
    run_ids: tuple[UUID, ...]
    versions: Mapping[UUID, int]
    blind: bool


@dataclass(frozen=True)
class _Column:
    run: Run
    label: str
    version: ResultVersion | None
    available: list[int]
    values: list[StoredMetricValue]


def parse_versions(text: str) -> dict[UUID, int]:
    """`"{run}:{n},{run}:{n}"`; a token that is not that raises `Invalid`."""
    found: dict[UUID, int] = {}
    for token in filter(None, text.split(",")):
        run, _, number = token.partition(":")
        try:
            found[UUID(run)] = int(number)
        except ValueError as error:
            raise Invalid(f"v: {token!r} is not run:version") from error
    return found


def parse_runs(text: str) -> tuple[UUID, ...]:
    try:
        return tuple(UUID(token) for token in filter(None, text.split(",")))
    except ValueError as error:
        raise Invalid("runs: every item is a Run id") from error


def _load(ports: MetricsComparePorts, query: CompareQuery) -> tuple[str, UUID, list[_Column]]:
    ids = list(dict.fromkeys(query.run_ids))
    if len(ids) < 2:  # noqa: PLR2004 - a comparison needs two Runs
        raise Invalid("a comparison needs at least two distinct Runs")
    runs = []
    for run_id in ids:
        run = ports.runs.get(run_id)
        if run is None:
            raise NotFound(f"no run {run_id}")
        runs.append(run)
    if len({run.project_id for run in runs}) > 1:
        raise Invalid("runs of more than one project")
    stray = set(query.versions) - set(ids)
    if stray:
        raise Invalid(f"v names a Run that is not selected: {sorted(stray)[0]}")
    project = ports.projects.get(runs[0].project_id)
    columns = [_column(ports, query, n, run) for n, run in enumerate(runs, start=1)]
    return (project.name if project else ""), runs[0].project_id, columns


def _column(ports: MetricsComparePorts, query: CompareQuery, n: int, run: Run) -> _Column:
    available = [version.n for version in ports.versions.list_for_run(run.id)]
    wanted = query.versions.get(run.id)
    if wanted is not None and wanted not in available:
        raise NotFound(f"run {run.id} has no version {wanted}")
    version = ports.versions.get(run.id, wanted) if wanted else ports.versions.latest(run.id)
    values = [] if version is None else ports.versions.values(version.id)
    if query.blind:
        values = [blind_value(value) for value in values]
    label = run.label or blind_label(n)
    return _Column(run, blind_label(n) if query.blind else label, version, available, values)


def _entry(ports: MetricsComparePorts) -> dict[str, CatalogueEntry]:
    return {entry.id: entry for entry in ports.catalogue.entries()}


def _stories(values: list[StoredMetricValue]) -> StoriesDone | None:
    by_source = {
        v.source: v.value_num
        for v in values
        if v.metric_id == STORIES_DONE and v.scope_type == "run" and v.value_num is not None
    }
    if "done" not in by_source or "planned" not in by_source:
        return None
    return StoriesDone(int(by_source["done"] or 0), int(by_source["planned"] or 0))


def _models_by_role(column: _Column, blind: bool) -> dict[str, list[str]]:
    models: dict[str, set[str]] = {}
    for value in column.values:
        if value.scope_type == "attempt" and value.role and value.model:
            models.setdefault(value.role, set()).add(HIDDEN if blind else value.model)
    return {role: sorted(found) for role, found in sorted(models.items())}


def _header(
    ports: MetricsComparePorts,
    column: _Column,
    flags: Mapping[UUID, list[bool | None]],
    blind: bool,
) -> CompareRunHeader:
    run = column.run
    harness = run.inputs.get("harness")
    base = run.inputs.get("base_branch")
    return CompareRunHeader(
        run_id=run.id,
        short_id=run.id.hex[:SHORT_ID],
        label=column.label,
        label_set_by_operator=run.label_set_by_operator,
        template_name=HIDDEN if blind else run.template_name,
        template_version=HIDDEN if blind else str(run.template_version),
        harness=harness if isinstance(harness, str) else None,
        models_by_role=_models_by_role(column, blind),
        base_branch=base if isinstance(base, str) else None,
        status=run.status,
        stories_done=_stories(column.values),
        selected_version=None if column.version is None else column.version.n,
        versions_available=column.available,
        subscription=run_subscription(flags.get(run.id, [])),
    )


def _same_work(ports: MetricsComparePorts, columns: list[_Column]) -> SameWork:
    runs: dict[UUID, SameWorkRun] = {}
    for column in columns:
        run = column.run
        folder = run.inputs.get("initiative_folder") or run.inputs.get("spec_folder")
        stories = _stories(column.values)
        runs[run.id] = SameWorkRun(
            base_commits={r.path: r.base_tip for r in ports.run_records.list_for_run(run.id)},
            initiative_folder=folder if isinstance(folder, str) else None,
            stories_planned=None if stories is None else stories.planned,
        )
    items = list(runs.values())
    differs = any(item != items[0] for item in items[1:])
    return SameWork(runs, differs)


def _cell(value: StoredMetricValue) -> CompareCell:
    figure = value.value_num
    return CompareCell(
        method_id=value.method_id,
        scope_type=value.scope_type,
        scope_key=value.scope_key,
        scope_label=value.scope_label,
        role=value.role,
        model=value.model,
        repository=value.repository,
        attempt_n=value.attempt_n,
        source=value.source,
        value_num=None if figure is None else format(figure, "f"),
        unit=value.unit,
        missing=value.missing,
        partial_n=value.partial_n,
        partial_m=value.partial_m,
        carried_from=value.carried_from,
    )


def _run_figure(values: list[StoredMetricValue], metric_id: str) -> Decimal | None:
    for value in values:
        if (
            value.metric_id == metric_id
            and value.scope_type == "run"
            and value.value_num is not None
        ):
            return value.value_num
    return None


def _delta_words(harness: Decimal, gateway: Decimal) -> str:
    delta = (harness - gateway).quantize(CENT)
    if delta == 0:
        return "±$0.00 vs gateway"
    sign = "+" if delta > 0 else "-"
    return f"{sign}${abs(delta):.2f} vs gateway"


def _harness_delta(columns: list[_Column]) -> dict[UUID, str]:
    deltas: dict[UUID, str] = {}
    for column in columns:
        harness = _run_figure(column.values, COST_HARNESS)
        gateway = _run_figure(column.values, COST_GATEWAY)
        if harness is not None and gateway is not None:
            deltas[column.run.id] = _delta_words(harness, gateway)
    return deltas


def _family_views(results: list[FamilyResult]) -> list[FamilyView]:
    return [
        FamilyView(
            family=result.family,
            source=result.source,
            step_structure_differs=result.step_structure_differs,
            cells={
                run_id: FamilyCellView(
                    None if cell.value_num is None else format(cell.value_num, "f"),
                    cell.missing,
                    list(cell.roles),
                )
                for run_id, cell in result.cells.items()
            },
        )
        for result in results
    ]


def _metric(
    entry: CatalogueEntry, columns: list[_Column], modes: Mapping[UUID, InStory]
) -> CompareMetric | None:
    by_run = {c.run.id: [v for v in c.values if v.metric_id == entry.id] for c in columns}
    if not any(by_run.values()):
        return None
    methods = {run_id: sorted({v.method_id for v in values}) for run_id, values in by_run.items()}
    present = [ids for ids in methods.values() if ids]
    families = _family_views(family_results(by_run, modes)) if family_applies(entry) else []
    return CompareMetric(
        metric_id=entry.id,
        methods_differ=any(ids != present[0] for ids in present[1:]),
        methods=methods,
        cells={run_id: [_cell(v) for v in values] for run_id, values in by_run.items()},
        harness_delta=_harness_delta(columns) if entry.id == COST_HARNESS else {},
        families=families,
    )


def compare_runs(ports: MetricsComparePorts, query: CompareQuery) -> Comparison:
    project_name, project_id, columns = _load(ports, query)
    flags = ports.fact_sets.subscriptions([c.run.id for c in columns])
    modes = {c.run.id: orchestrate_in_story(ports.steps.list_for_run(c.run.id)) for c in columns}
    metrics = [_metric(entry, columns, modes) for entry in ports.catalogue.entries()]
    return Comparison(
        project_id=project_id,
        project_name=project_name,
        runs=[_header(ports, c, flags, query.blind) for c in columns],
        same_work=_same_work(ports, columns),
        metrics=[m for m in metrics if m is not None],
        diff_size={c.run.id: NOT_RUN for c in columns},
    )


def export_rows(ports: MetricsComparePorts, query: CompareQuery) -> ExportResult:
    project_name, _, columns = _load(ports, query)
    catalogue = _entry(ports)
    order = {metric_id: n for n, metric_id in enumerate(catalogue)}
    rows = [
        to_export_row(
            ExportSource(column.run.id, column.label, column.version, query.blind),
            value,
            catalogue.get(value.metric_id),
        )
        for column in columns
        if column.version is not None
        for value in sorted(column.values, key=lambda v: order.get(v.metric_id, len(order)))
    ]
    flags = ports.fact_sets.subscriptions([c.run.id for c in columns])
    headers = [_header(ports, c, flags, query.blind) for c in columns]
    return ExportResult(project_name, headers, rows, catalogue_for(rows, catalogue))
