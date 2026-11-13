"""`set_run_label`: set or restore a Run's label at any status (story 3; SPEC CAP-3).

Not a status writer (AD-8): it never reads or writes `status`. The unit of work is entered by
the provider before this runs, as for every other use case.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.rules.run_label import clean_label, default_label
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.repositories import (
    ProjectRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class RunLabelPorts:
    runs: RunRepository
    steps: StepRunRepository
    projects: ProjectRepository
    uow: UnitOfWork


def set_run_label(
    ports: RunLabelPorts, run_id: UUID, label: str | None
) -> tuple[Run, list[StepRun]]:
    """A string sets the label (the operator's); `None` restores the computed default."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    if label is None:
        project = ports.projects.get(run.project_id)
        text = default_label(
            project.name if project else "", run.inputs, run.template_name, run.created_at
        )
        by_operator = False
    else:
        text, by_operator = clean_label(label), True
    ports.runs.set_label(run_id, text, by_operator)
    ports.uow.commit()
    updated = ports.runs.get(run_id) or run
    return updated, list(ports.steps.list_for_run(run_id))
