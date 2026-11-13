"""One row of a Project's Run list (SPEC CAP-10, CAP-3), split from `schemas/projects.py`."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.schemas.common import UtcTimestamp, drop_default
from orchestrator.application.use_cases.project_runs import ProjectRunSummary


class ProjectRunOut(BaseModel):
    """One row of a Project's **RUNS ON THIS PROJECT** list (SPEC CAP-10, UX-DR12): the record
    row's own fields, plus what a Repository row's control reads about the Run it started."""

    id: UUID
    #: The UI status token `StatusToken.astro` renders (`QUE RUN BLK CHK DON ERR CAN`).
    token: str
    #: `"{name}@{version}"` — the Template name and the pinned version it ran.
    template: str
    #: Whether this is the Repository's own *Initialise repository* Run (`INIT_TEMPLATE`,
    #: AD-20) — a fact, so no screen tests a Template's name for it.
    is_init: bool
    branch: str
    repository_id: UUID
    #: The row the Operator would point at right now, or the last one this Run touched.
    current_step_label: str
    #: The sentence a `failed` or `cancelled` Run's row states beside its token; `""` for
    #: every Run whose reason a signal or an error row has not already given a home.
    reason: str
    #: `run.compare_urls`, whole — an initialisation Run carries at most one, and the
    #: Repository row's own control is what reads it (UX-DR12's `link`).
    compare_urls: list[str]
    created_at: UtcTimestamp
    label: str = Field(default="", json_schema_extra=drop_default)
    label_set_by_operator: bool = Field(default=False, json_schema_extra=drop_default)

    @classmethod
    def of(cls, summary: ProjectRunSummary) -> ProjectRunOut:
        run = summary.run
        return cls(
            id=run.id,
            token=summary.token,
            template=f"{run.template_name}@{run.template_version}",
            is_init=summary.is_init,
            branch=str(run.inputs.get("base_branch", "")),
            repository_id=run.repository_id,
            current_step_label=summary.current_step_label,
            reason=summary.reason,
            compare_urls=list(run.compare_urls),
            created_at=run.created_at,
            label=run.label,
            label_set_by_operator=run.label_set_by_operator,
        )
