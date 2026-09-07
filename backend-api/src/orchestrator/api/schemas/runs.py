"""The HTTP shape of `POST /runs` and `GET /runs/{id}` (SPEC CAP-4, FR-6, FR-8).

`RunIn` is pre-flight's own request (`api/schemas/preflight.py::PreflightIn`) with the
fields *Start run* needs that a live probe does not: every targeting field becomes
required — a Run cannot be created from a Template, a Project or a Repository the request
never named — and `budget_usd` gains the brief's own `> 0` rule. `RunSummaryOut` is the
"minimal" read model the brief asks for; the full one is 4.12's.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.errors import ProblemError
from orchestrator.api.schemas.common import MAX_VERSION, MoneyStr, UtcTimestamp
from orchestrator.application.rules.signals import run_admitted_signals
from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.create_run import CreateRunRequest, CreateRunResult
from orchestrator.domain.entities.run import Run
from orchestrator.domain.statuses import RunStatus, SignalKind

#: Same bound as `api/schemas/preflight.py::TemplateVersion` — Postgres `integer`'s range.
TemplateVersionField = Annotated[int, Field(gt=0, le=MAX_VERSION)]

#: The brief's own rule: a Run cannot be started with no budget at all.
BudgetUsd = Annotated[MoneyStr, Field(gt=0)]


def plan_error_problems(error: PlanError) -> list[ProblemError]:
    """One `PlanError` as `errors[]`: `template`, `version`, `line`, `item` (as `path`),
    `reason` — the shape `api/schemas/templates.py::as_problem_errors` gives a validation
    failure, extended with `path` because a plan error names an entry, not only a line."""
    return [
        ProblemError(
            template=error.template,
            version=str(error.version) if error.version is not None else None,
            line=error.line,
            path=error.item,
            reason=error.reason,
        )
    ]


class RunIn(BaseModel):
    """`POST /runs`'s body: what *Start run* submits once every field is filled in."""

    template_name: str
    template_version: TemplateVersionField
    project_id: UUID
    repository_id: UUID
    base_branch: str
    budget_usd: BudgetUsd
    inputs: dict[str, Any] = Field(default_factory=dict)
    harness: str | None = None
    model: str | None = None
    manual_estimate_h: Decimal | None = None
    re_review_done: bool = False

    def as_request(self) -> CreateRunRequest:
        return CreateRunRequest(
            template_name=self.template_name,
            template_version=self.template_version,
            project_id=self.project_id,
            repository_id=self.repository_id,
            base_branch=self.base_branch,
            budget_usd=self.budget_usd,
            inputs=self.inputs,
            harness=self.harness,
            model=self.model,
            manual_estimate_h=self.manual_estimate_h,
            re_review_done=self.re_review_done,
        )


class RunSummaryOut(BaseModel):
    """The minimal Run read model (4.12 replaces this with the full one)."""

    id: UUID
    status: RunStatus
    template: str
    version: int
    project: UUID
    repository: UUID
    #: The branch this Run works on, as bound at creation — `run.inputs["base_branch"]`.
    branch: str
    budget_usd: MoneyStr
    spend_usd: MoneyStr
    plan_ref: str | None
    created_at: UtcTimestamp
    #: What the Operator can send this Run right now (SPEC CAP-9, PRD §4.6). `[cancel]`
    #: while it runs, the parked stop's own list while it waits on one, `[]` once it is
    #: terminal — `application/rules/signals.py::run_admitted_signals`.
    admitted_signals: tuple[SignalKind, ...]

    @classmethod
    def of(cls, run: Run, *, park_row_kind: str | None = None) -> RunSummaryOut:
        return cls(
            id=run.id,
            status=run.status,
            template=run.template_name,
            version=run.template_version,
            project=run.project_id,
            repository=run.repository_id,
            branch=str(run.inputs.get("base_branch", "")),
            budget_usd=run.budget_usd,
            spend_usd=run.spend_usd,
            plan_ref=run.plan_ref,
            created_at=run.created_at,
            admitted_signals=run_admitted_signals(run, park_row_kind),
        )


class CreateRunOut(BaseModel):
    """`POST /runs`'s 201 body: the Run, and where it stands in the queue."""

    run: RunSummaryOut
    starts_now: bool
    waiting: str

    @classmethod
    def of(cls, result: CreateRunResult) -> CreateRunOut:
        return cls(
            run=RunSummaryOut.of(result.run),
            starts_now=result.starts_now,
            waiting=result.waiting,
        )
