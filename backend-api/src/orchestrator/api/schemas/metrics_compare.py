"""Payloads of the comparison, spend and export endpoints (AD-3): the contract is these models.

Every figure is a decimal string; `subscription` is `true`, `false` or `null` when unknown.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.metrics import CatalogueEntryOut
from orchestrator.application.metrics.compare_views import Comparison, ExportResult
from orchestrator.application.use_cases.metrics_spend import MetricsRun, ProjectSpend


class CancelledSpendOut(BaseModel):
    gateway: str
    harness: str
    runs: int


class ProjectSpendOut(BaseModel):
    project_id: UUID
    project_name: str
    gateway: str
    harness: str
    runs: int
    cancelled: CancelledSpendOut
    gateway_reported: bool
    harness_reported: bool
    subscription: bool | None

    @classmethod
    def of(cls, spend: ProjectSpend) -> ProjectSpendOut:
        return cls.model_validate(asdict(spend))


class MetricsRunOut(BaseModel):
    id: UUID
    label: str
    label_set_by_operator: bool
    status: str
    template_name: str
    template_version: int
    harness: str | None
    base_branch: str | None
    branch: str | None
    wall_clock_seconds: int | None
    gateway: str
    harness_spend: str
    latest_version: int | None
    subscription: bool | None
    selectable: bool

    @classmethod
    def of(cls, run: MetricsRun) -> MetricsRunOut:
        return cls.model_validate(asdict(run))


class StoriesDoneOut(BaseModel):
    done: int
    planned: int


class CompareRunHeaderOut(BaseModel):
    run_id: UUID
    short_id: str
    label: str
    label_set_by_operator: bool
    template_name: str
    template_version: str
    harness: str | None
    models_by_role: dict[str, list[str]]
    base_branch: str | None
    status: str
    stories_done: StoriesDoneOut | None
    selected_version: int | None
    versions_available: list[int]
    subscription: bool | None


class SameWorkRunOut(BaseModel):
    base_commits: dict[str, str | None]
    initiative_folder: str | None
    stories_planned: int | None


class SameWorkOut(BaseModel):
    runs: dict[UUID, SameWorkRunOut]
    differs: bool


class CompareCellOut(BaseModel):
    method_id: str
    scope_type: str
    scope_key: str
    scope_label: str | None
    role: str | None
    model: str | None
    repository: str | None
    attempt_n: int | None
    source: str | None
    value_num: str | None
    unit: str
    missing: str | None
    partial_n: int | None
    partial_m: int | None
    carried_from: int | None


class FamilyCellOut(BaseModel):
    value_num: str | None
    missing: str | None
    roles: list[str]


class FamilyOut(BaseModel):
    family: str
    source: str | None
    step_structure_differs: bool
    cells: dict[UUID, FamilyCellOut]


class ToolVersionOut(BaseModel):
    tool: str
    version: str


class CompareMetricOut(BaseModel):
    metric_id: str
    methods_differ: bool
    methods: dict[UUID, list[str]]
    cells: dict[UUID, list[CompareCellOut]]
    harness_delta: dict[UUID, str]
    families: list[FamilyOut]
    tool_versions_differ: bool = False
    toolsets: dict[UUID, list[ToolVersionOut]] = {}


class CompareOut(BaseModel):
    project_id: UUID
    project_name: str
    runs: list[CompareRunHeaderOut]
    same_work: SameWorkOut
    metrics: list[CompareMetricOut]
    diff_size: dict[UUID, str]

    @classmethod
    def of(cls, comparison: Comparison) -> CompareOut:
        return cls.model_validate(asdict(comparison))


class ExportRowOut(BaseModel):
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


class CompareExportOut(BaseModel):
    runs: list[CompareRunHeaderOut]
    rows: list[ExportRowOut]
    catalogue: list[CatalogueEntryOut]

    @classmethod
    def of(cls, result: ExportResult) -> CompareExportOut:
        return cls(
            runs=[CompareRunHeaderOut.model_validate(asdict(r)) for r in result.runs],
            rows=[ExportRowOut.model_validate(asdict(r)) for r in result.rows],
            catalogue=[CatalogueEntryOut.from_entry(e) for e in result.catalogue],
        )


__all__ = [
    "CompareExportOut",
    "CompareOut",
    "ExportRowOut",
    "MetricsRunOut",
    "ProjectSpendOut",
]
