"""`reload_folder` (SPEC CAP-5, D3): one snapshot, one commit, nothing touched but templates."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.template_reload import (
    FOLDER_MISSING,
    FOLDER_OFF,
    reload_folder,
)
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.template_folders import OperatorFolder
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)
from tests.unit.fakes.template_folders import FakeTemplateFolders, file, ready
from tests.unit.fakes.templates import FakeTemplateVersionRepository

AT = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
STEP = "steps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
SECOND = 2


def bench(note: str = "a") -> str:
    return f"name: bench\nversion: 1\ndescription: {note}\n{STEP}"


def ports(
    templates: FakeTemplateVersionRepository | None,
    folders: FakeTemplateFolders | None,
    uow: FakeUnitOfWork,
) -> TemplatePorts:
    return TemplatePorts(
        uow=uow,
        templates=templates or FakeTemplateVersionRepository(),
        clock=FakeClock(AT),
        folders=folders,
    )


def test_a_ready_folder_is_stored_and_committed_from_one_snapshot() -> None:
    folders = FakeTemplateFolders(folder=ready(file("bench", bench()), path="/mine"))
    templates = FakeTemplateVersionRepository()

    with FakeUnitOfWork() as uow:
        result = reload_folder(ports(templates, folders, uow))

    assert uow.committed
    assert result.folder == "/mine"
    assert [(e.name, e.version, e.overrides_shipped) for e in result.outcome.stored] == [
        ("bench", 1, False)
    ]
    assert folders.operator_calls == 1


def test_a_second_reload_with_nothing_changed_stores_nothing() -> None:
    folders = FakeTemplateFolders(folder=ready(file("bench", bench())))
    templates = FakeTemplateVersionRepository()
    with FakeUnitOfWork() as uow:
        reload_folder(ports(templates, folders, uow))
    with FakeUnitOfWork() as uow:
        again = reload_folder(ports(templates, folders, uow))

    assert again.outcome.stored == ()
    assert [e.name for e in again.outcome.unchanged] == ["bench"]


def test_an_edited_file_stores_the_next_version_and_the_runs_pin_stays() -> None:
    templates = FakeTemplateVersionRepository()
    folders = FakeTemplateFolders(folder=ready(file("bench", bench("one"))))
    with FakeUnitOfWork() as uow:
        reload_folder(ports(templates, folders, uow))
    first = templates.get("bench", 1)
    run = Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="bench",
        template_version=1,
        pinned_versions=(TemplateRef(name="bench", version=1),),
        status="running",  # type: ignore[arg-type]
        budget_usd=Decimal("1"),
        created_at=AT,
    )
    runs = FakeRunRepository([run])

    folders.folder = ready(file("bench", bench("two")))
    with FakeUnitOfWork() as uow:
        result = reload_folder(ports(templates, folders, uow))

    assert [(e.name, e.version) for e in result.outcome.stored] == [("bench", SECOND)]
    assert runs.get(run.id) == run
    assert run.pinned_versions == (TemplateRef(name="bench", version=1),)
    assert templates.get("bench", 1) == first


def test_the_run_rows_attempts_and_engine_are_untouched() -> None:
    run_id = new_id()
    run = Run(
        id=run_id,
        project_id=new_id(),
        repository_id=new_id(),
        template_name="bench",
        template_version=1,
        status="running",  # type: ignore[arg-type]
        budget_usd=None,
        created_at=AT,
    )
    step = StepRun(
        id=new_id(),
        run_id=run_id,
        seq=1,
        path="sync",
        label="sync",
        kind="git.sync",
        gate="deterministic",  # type: ignore[arg-type]
        status="running",  # type: ignore[arg-type]
    )
    attempt = Attempt(id=new_id(), run_id=run_id, step_run_id=step.id, n=1, status="running")  # type: ignore[arg-type]
    runs, steps, attempts = (
        FakeRunRepository([run]),
        FakeStepRunRepository([step]),
        FakeAttemptRepository([attempt]),
    )
    engine = FakeWorkflowEngine()
    before = (dict(runs.runs), steps.list_for_run(run_id), attempts.list_for_row(step.id))
    run_calls = list(runs.calls)
    folders = FakeTemplateFolders(folder=ready(file("bench", bench())))

    with FakeUnitOfWork() as uow:
        result = reload_folder(ports(None, folders, uow))

    assert result.outcome.stored
    assert (dict(runs.runs), steps.list_for_run(run_id), attempts.list_for_row(step.id)) == before
    assert runs.calls == run_calls
    assert engine.calls == []


@pytest.mark.parametrize(
    ("folder", "message"),
    [
        (OperatorFolder(path="", state="off"), FOLDER_OFF),
        (OperatorFolder(path="/nope", state="missing"), FOLDER_MISSING + "/nope"),
    ],
)
def test_an_off_or_missing_folder_is_a_conflict_after_one_snapshot(
    folder: OperatorFolder, message: str
) -> None:
    folders = FakeTemplateFolders(folder=folder)

    with FakeUnitOfWork() as uow, pytest.raises(Conflict) as raised:
        reload_folder(ports(None, folders, uow))

    assert str(raised.value) == message
    assert folders.operator_calls == 1
    assert not uow.committed


def test_a_ready_folder_reads_its_snapshot_once() -> None:
    folders = FakeTemplateFolders(folder=ready())

    with FakeUnitOfWork() as uow:
        reload_folder(ports(None, folders, uow))

    assert folders.operator_calls == 1


def test_no_folder_port_is_the_off_conflict() -> None:
    with FakeUnitOfWork() as uow, pytest.raises(Conflict) as raised:
        reload_folder(ports(None, None, uow))

    assert str(raised.value) == FOLDER_OFF
    assert FOLDER_OFF == "template folder not configured"


def test_the_only_parameter_is_the_ports() -> None:
    parameters = list(inspect.signature(reload_folder).parameters.values())

    assert [p.name for p in parameters] == ["ports"]
    assert parameters[0].annotation in (TemplatePorts, "TemplatePorts")


class Racing(FakeTemplateVersionRepository):
    def add_version(self, version: TemplateVersion, *, description: str | None) -> None:
        raise Conflict("template version bench@2 taken by a concurrent save; nothing stored")


def test_a_concurrent_save_propagates_and_rolls_back() -> None:
    folders = FakeTemplateFolders(folder=ready(file("bench", bench())))
    uow = FakeUnitOfWork()

    with pytest.raises(Conflict, match=r"bench@2"), uow:
        reload_folder(ports(Racing(), folders, uow))

    assert not uow.committed
    assert uow.rolled_back
