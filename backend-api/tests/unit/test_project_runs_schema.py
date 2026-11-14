"""`ProjectRunOut` carries the Run's label (story 3), and lives in `schemas/project_runs.py`."""

from __future__ import annotations

from orchestrator.api.schemas import project_runs, projects
from orchestrator.application.use_cases.project_runs import ProjectRunSummary
from tests.unit.test_run_label_router import a_run


def test_the_row_carries_label_and_operator_flag() -> None:
    run = a_run(label="snake round 2", label_set_by_operator=True)

    out = project_runs.ProjectRunOut.of(
        ProjectRunSummary(run=run, token="RUN", current_step_label="build", reason="")
    )

    assert (out.label, out.label_set_by_operator) == ("snake round 2", True)


def test_projects_re_exports_the_same_class() -> None:
    assert projects.ProjectRunOut is project_runs.ProjectRunOut
