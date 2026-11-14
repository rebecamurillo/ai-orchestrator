"""One export row per stored metric value: the CSV and JSON files are projections of these."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from datetime import UTC
from uuid import UUID

from orchestrator.application.metrics.blind import HIDDEN
from orchestrator.application.metrics.values import na
from orchestrator.domain.entities.metric_results import ResultVersion, StoredMetricValue
from orchestrator.domain.ports.catalogue import CatalogueEntry


@dataclass(frozen=True)
class ExportRow:
    run_id: str
    run_label: str
    result_version: str
    metric_id: str
    method_id: str
    scope_type: str
    scope_key: str
    scope_label: str
    role: str
    model: str
    repository: str
    attempt_n: str
    source: str
    value_num: str
    unit: str
    missing: str
    carried_from: str
    component_of: str
    additive: str
    calculated_at: str
    entry_point: str
    project_id: str
    template_name: str
    template_version: str
    harness: str
    origin_model: str
    origin_repository: str
    branch: str
    commit: str
    base_commit: str


EXPORT_COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(ExportRow))


def _text(value: object | None) -> str:
    return "" if value is None else str(value)


def _origin(value: str | None, reason: str | None) -> str:
    return value if value is not None else na(_text(reason))


@dataclass(frozen=True)
class ExportSource:
    """The Run column a row is read from."""

    run_id: UUID
    label: str
    version: ResultVersion
    blind: bool


def to_export_row(
    source: ExportSource, value: StoredMetricValue, entry: CatalogueEntry | None
) -> ExportRow:
    run_id, label, version, blind = source.run_id, source.label, source.version, source.blind
    origin = value.origin
    figure = value.value_num
    return ExportRow(
        run_id=str(run_id),
        run_label=label,
        result_version=str(version.n),
        metric_id=value.metric_id,
        method_id=value.method_id,
        scope_type=value.scope_type,
        scope_key=value.scope_key,
        scope_label=_text(value.scope_label),
        role=_text(value.role),
        model=_text(value.model),
        repository=_text(value.repository),
        attempt_n=_text(value.attempt_n),
        source=_text(value.source),
        value_num="" if figure is None else format(figure, "f"),
        unit=value.unit,
        missing=_text(value.missing),
        carried_from=_text(value.carried_from),
        component_of="" if entry is None else _text(entry.component_of),
        additive="" if entry is None else str(entry.additive).lower(),
        calculated_at=version.calculated_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        entry_point="+".join(version.entry_point),
        project_id=str(origin.project_id),
        template_name=origin.template_name,
        template_version=HIDDEN if blind else str(origin.template_version),
        harness=_origin(origin.harness, origin.harness_na),
        origin_model=_origin(origin.origin_model, origin.origin_model_na),
        origin_repository=_origin(origin.origin_repository, origin.origin_repository_na),
        branch=_origin(origin.branch, origin.branch_na),
        commit=_origin(origin.commit, origin.commit_na),
        base_commit=_origin(origin.base_commit, origin.base_commit_na),
    )


def catalogue_for(
    rows: Iterable[ExportRow], catalogue: Mapping[str, CatalogueEntry]
) -> list[CatalogueEntry]:
    """Each catalogue entry of a metric in the rows, once, in catalogue order."""
    used = {row.metric_id for row in rows}
    return [entry for entry in catalogue.values() if entry.id in used]
