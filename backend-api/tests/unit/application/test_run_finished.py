"""`on_finished` (SPEC CAP-10, FR-30): the walker's completion hook.

Reuses the exact `Git` scripting `test_clone_check_use_cases.py` gives a reachable
repository, because `on_finished` runs the same pure check `run_clone_check` runs — this
suite proves *when* that happens, not what a check itself decides.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.use_cases.run_finished import RunFinishedPorts, on_finished
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import (
    DEFAULT_TEST_GLOBS,
    CloneCheck,
    Repository,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import CloneResult, RemoteRef
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 9, 6, tzinfo=UTC)
BMAD_VERSION = "6.11.0"
WORK_DIR = Path("/work")
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
MANIFEST = "installation:\n  version: 6.11.0\n  installDate: 2026-08-24\nmodules: []\n"


def reachable_git() -> FakeGit:
    return FakeGit(
        ls_remote=[RemoteRef(ref="HEAD", sha=SHA), RemoteRef(ref="refs/heads/main", sha=SHA)],
        clone_base=[CloneResult(seconds=1.0, bytes=4096)],
        read_file=[MANIFEST],
    )


def a_project() -> Project:
    return Project(
        id=new_id(),
        slug="acme",
        name="Acme",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def a_repository(project_id: object) -> Repository:
    return Repository(
        id=new_id(),
        project_id=project_id,  # type: ignore[arg-type]
        slug="widgets",
        url="https://github.com/acme/widgets.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=DEFAULT_TEST_GLOBS,
        package_manager="uv",
        clone_check=CloneCheck.pending(),
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(project_id: object, repository_id: object, **overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": project_id,
        "repository_id": repository_id,
        "template_name": "repo-init",
        "template_version": 1,
        "status": "done",
        "budget_usd": 0,
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Harness:
    def __init__(self, *, git: FakeGit | None) -> None:
        self.project = a_project()
        self.repository = a_repository(self.project.id)
        self.projects = FakeProjectRepository([self.project])
        self.repositories = FakeRepositoryRepository([self.repository])
        self.runs = FakeRunRepository()
        self.uow = FakeUnitOfWork()
        self.uow.__enter__()
        self.ports = RunFinishedPorts(
            runs=self.runs,
            repositories=self.repositories,
            projects=self.projects,
            git=git,
            uow=self.uow,
            clock=FakeClock(NOW),
            work_dir=WORK_DIR,
            bmad_version=BMAD_VERSION,
        )

    def add(self, run: Run) -> Run:
        self.runs.add(run)
        return run


def test_a_finished_repo_init_run_re_runs_its_repositorys_clone_check() -> None:
    harness = Harness(git=reachable_git())
    run = harness.add(a_run(harness.project.id, harness.repository.id))

    checked = on_finished(harness.ports, run.id)

    assert checked is not None
    assert checked.clone_check.bmad_version == BMAD_VERSION
    assert harness.repositories.get(harness.repository.id) == checked
    assert harness.uow.committed is True


def test_a_run_that_is_not_repo_init_is_a_no_op() -> None:
    harness = Harness(git=reachable_git())
    run = harness.add(a_run(harness.project.id, harness.repository.id, template_name="epic"))

    result = on_finished(harness.ports, run.id)

    assert result is None
    assert harness.repository.clone_check.status == "pending"


def test_a_repo_init_run_that_is_not_done_is_a_no_op() -> None:
    harness = Harness(git=reachable_git())
    run = harness.add(a_run(harness.project.id, harness.repository.id, status="failed"))

    result = on_finished(harness.ports, run.id)

    assert result is None


def test_an_unknown_run_is_a_no_op() -> None:
    harness = Harness(git=reachable_git())

    result = on_finished(harness.ports, new_id())

    assert result is None


def test_a_process_with_no_git_adapter_wired_is_a_no_op() -> None:
    harness = Harness(git=None)
    run = harness.add(a_run(harness.project.id, harness.repository.id))

    result = on_finished(harness.ports, run.id)

    assert result is None


def test_a_repository_the_run_pointed_at_that_is_gone_is_a_no_op() -> None:
    harness = Harness(git=reachable_git())
    run = harness.add(a_run(harness.project.id, new_id()))

    result = on_finished(harness.ports, run.id)

    assert result is None


def test_a_project_the_repository_pointed_at_that_is_gone_is_a_no_op() -> None:
    harness = Harness(git=reachable_git())
    orphan_repository = a_repository(new_id())
    harness.repositories = FakeRepositoryRepository([orphan_repository])
    harness.ports = RunFinishedPorts(
        runs=harness.runs,
        repositories=harness.repositories,
        projects=harness.projects,
        git=harness.ports.git,
        uow=harness.uow,
        clock=harness.ports.clock,
        work_dir=WORK_DIR,
        bmad_version=BMAD_VERSION,
    )
    run = harness.add(a_run(harness.project.id, orphan_repository.id))

    result = on_finished(harness.ports, run.id)

    assert result is None
