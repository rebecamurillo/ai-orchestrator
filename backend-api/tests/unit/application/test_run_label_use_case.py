"""`set_run_label` sets or restores a label at any status (story 3; AC4, AC5, AC6)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.use_cases.run_label import RunLabelPorts, set_run_label
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Invalid, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

AT = datetime(2026, 11, 10, 10, 23, 41, tzinfo=UTC)
PROJECT_ID = UUID(int=7)


def a_project(name: str) -> Project:
    return Project(
        id=PROJECT_ID,
        slug="familio",
        name=name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=AT,
        updated_at=AT,
    )


def a_run(**over: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": UUID(int=8),
        "template_name": "bench",
        "template_version": 1,
        "status": "cancelled",
        "budget_usd": Decimal("1"),
        "inputs": {"initiative_folder": "initiatives/snake"},
        "created_at": AT,
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def ports_for(
    run: Run, project: Project | None
) -> tuple[RunLabelPorts, FakeRunRepository, FakeUnitOfWork]:
    runs, uow = FakeRunRepository([run]), FakeUnitOfWork()
    uow.__enter__()  # the provider opens it before the use case runs
    projects = FakeProjectRepository([project] if project else [])
    return (
        RunLabelPorts(runs=runs, steps=FakeStepRunRepository(), projects=projects, uow=uow),
        runs,
        uow,
    )


def test_a_cancelled_run_takes_the_operators_label_and_keeps_its_status() -> None:
    run = a_run()
    ports, runs, uow = ports_for(run, a_project("familio"))

    updated, rows = set_run_label(ports, run.id, "  snake round 2 · story session ")

    assert (updated.label, updated.label_set_by_operator) == ("snake round 2 · story session", True)
    assert updated.status == "cancelled"
    assert rows == []
    assert ("set_label", run.id) in runs.calls
    assert uow.committed


def test_null_restores_the_default_with_the_projects_current_name() -> None:
    run = a_run(label="mine", label_set_by_operator=True)
    ports, _, _ = ports_for(run, a_project("renamed"))

    updated, _ = set_run_label(ports, run.id, None)

    assert updated.label == "renamed snake bench 2026-11-10 10:23"
    assert updated.label_set_by_operator is False


def test_a_missing_project_leaves_the_project_word_out() -> None:
    run = a_run()
    ports, _, _ = ports_for(run, None)

    updated, _ = set_run_label(ports, run.id, None)

    assert updated.label == "snake bench 2026-11-10 10:23"


@pytest.mark.parametrize("label", ["x" * 121, "", "   "])
def test_a_label_out_of_bounds_changes_nothing(label: str) -> None:
    run = a_run(label="kept")
    ports, runs, uow = ports_for(run, a_project("familio"))

    with pytest.raises(Invalid):
        set_run_label(ports, run.id, label)

    assert ("set_label", run.id) not in runs.calls
    assert not uow.committed
    assert runs.runs[run.id].label == "kept"


def test_an_unknown_run_is_not_found() -> None:
    ports, _, uow = ports_for(a_run(), a_project("familio"))

    with pytest.raises(NotFound):
        set_run_label(ports, new_id(), "x")

    assert not uow.committed
