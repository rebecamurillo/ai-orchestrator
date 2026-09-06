"""The HTTP shape of `POST /runs/preflight` (SPEC CAP-3, FR-8)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.schemas.common import MAX_VERSION
from orchestrator.application.preflight.model import (
    Line,
    LineStatus,
    PreflightRequest,
    PreflightResult,
)
from orchestrator.application.templates.plan_model import PlanError
from orchestrator.domain.statuses import Gate, StepStatus
from orchestrator.domain.values import PlannedRow

#: Postgres `integer`'s upper bound (`api/schemas/common.py::MAX_VERSION`) — a version above
#: it would otherwise reach `TemplateVersionRepository.get` and the database as an
#: out-of-range value, a 500 rather than the 422 an unresolvable version means (schemathesis
#: gate).
TemplateVersion = Annotated[int, Field(gt=0, le=MAX_VERSION)]


class PreflightIn(BaseModel):
    """The pre-flight request. Every field but `re_review_done` is optional — a missing one
    makes its dependent lines `skip` rather than a 422 (the brief's own rule)."""

    template_name: str | None = None
    template_version: TemplateVersion | None = None
    project_id: UUID | None = None
    repository_id: UUID | None = None
    base_branch: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    harness: str | None = None
    model: str | None = None
    budget_usd: Decimal | None = None
    re_review_done: bool = False

    def as_request(self) -> PreflightRequest:
        return PreflightRequest(
            template_name=self.template_name,
            template_version=self.template_version,
            project_id=self.project_id,
            repository_id=self.repository_id,
            base_branch=self.base_branch,
            inputs=self.inputs,
            harness=self.harness,
            model=self.model,
            budget_usd=self.budget_usd,
            re_review_done=self.re_review_done,
        )


class LineOut(BaseModel):
    """One check line: `{check, status, text, fix?}`."""

    check: str
    status: LineStatus
    text: str
    fix: str | None = None

    @classmethod
    def of(cls, line: Line) -> LineOut:
        return cls(check=line.check, status=line.status, text=line.text, fix=line.fix)


class PlannedRowOut(BaseModel):
    """One row of *What will run* — the same shape `create_run` (4.4) will persist."""

    seq: int
    path: str
    label: str
    kind: str
    gate: Gate
    status: StepStatus
    reason: str | None
    with_resolved: dict[str, Any]
    frame: str | None
    story_id: str | None

    @classmethod
    def of(cls, row: PlannedRow) -> PlannedRowOut:
        return cls(
            seq=row.seq,
            path=row.path,
            label=row.label,
            kind=row.kind,
            gate=row.gate,
            status=row.status,
            reason=row.reason,
            with_resolved=row.with_resolved,
            frame=row.frame,
            story_id=row.story_id,
        )


class PlanErrorOut(BaseModel):
    """Why *What will run* could not be built."""

    reason: str
    template: str | None
    version: int | None
    line: int | None
    item: str | None

    @classmethod
    def of(cls, error: PlanError) -> PlanErrorOut:
        return cls(
            reason=error.reason,
            template=error.template,
            version=error.version,
            line=error.line,
            item=error.item,
        )


class PreflightOut(BaseModel):
    """`POST /runs/preflight`'s response."""

    lines: list[LineOut]
    start_allowed: bool
    queue_note: str
    rows: list[PlannedRowOut] | None
    plan_error: PlanErrorOut | None

    @classmethod
    def of(cls, result: PreflightResult) -> PreflightOut:
        return cls(
            lines=[LineOut.of(line) for line in result.lines],
            start_allowed=result.start_allowed,
            queue_note=result.queue_note,
            rows=[PlannedRowOut.of(row) for row in result.rows]
            if result.rows is not None
            else None,
            plan_error=PlanErrorOut.of(result.plan_error)
            if result.plan_error is not None
            else None,
        )
