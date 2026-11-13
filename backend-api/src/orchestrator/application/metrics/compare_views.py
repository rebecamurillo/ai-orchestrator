"""The shapes a comparison and an export are answered in (epic 4 story 1): plain data, every
figure already a decimal string, so the API maps them without computing anything."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from orchestrator.application.metrics.export_rows import ExportRow
from orchestrator.domain.ports.catalogue import CatalogueEntry


@dataclass(frozen=True)
class StoriesDone:
    done: int
    planned: int


@dataclass(frozen=True)
class CompareRunHeader:
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
    stories_done: StoriesDone | None
    selected_version: int | None
    versions_available: list[int]
    subscription: bool | None


@dataclass(frozen=True)
class SameWorkRun:
    base_commits: dict[str, str | None]
    initiative_folder: str | None
    stories_planned: int | None


@dataclass(frozen=True)
class SameWork:
    runs: dict[UUID, SameWorkRun]
    differs: bool


@dataclass(frozen=True)
class CompareCell:
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


@dataclass(frozen=True)
class FamilyCellView:
    value_num: str | None
    missing: str | None
    roles: list[str]


@dataclass(frozen=True)
class FamilyView:
    family: str
    source: str | None
    step_structure_differs: bool
    cells: dict[UUID, FamilyCellView]


@dataclass(frozen=True)
class ToolVersion:
    tool: str
    version: str


@dataclass(frozen=True)
class CompareMetric:
    metric_id: str
    methods_differ: bool
    methods: dict[UUID, list[str]]
    cells: dict[UUID, list[CompareCell]]
    harness_delta: dict[UUID, str]
    families: list[FamilyView]
    tool_versions_differ: bool = False
    toolsets: dict[UUID, list[ToolVersion]] = field(default_factory=dict)


@dataclass(frozen=True)
class Comparison:
    project_id: UUID
    project_name: str
    runs: list[CompareRunHeader]
    same_work: SameWork
    metrics: list[CompareMetric]
    diff_size: dict[UUID, str]


@dataclass(frozen=True)
class ExportResult:
    project_name: str
    runs: list[CompareRunHeader]
    rows: list[ExportRow]
    catalogue: list[CatalogueEntry]
