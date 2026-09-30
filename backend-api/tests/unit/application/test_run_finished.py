"""`on_finished` (SPEC CAP-10, FR-30): the walker's completion hook.

Reuses the exact `Git` scripting `test_clone_check_use_cases.py` gives a reachable
repository, because `on_finished` runs the same pure check `run_clone_check` runs — this
suite proves *when* that happens, not what a check itself decides.

*When* is read off the Run's own rows, not off its Template's name (Operator decision
2026-09-30: no template name hardcoded in product code): a Run holding a `bmad.install` row
installed the method, so the Repository's stored method version is stale. The plans below
are `(path, kind)` pairs this suite owns, not a shipped Template's.
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
from tests.unit.application.writer_fixtures import build_rows
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 9, 6, tzinfo=UTC)
BMAD_VERSION = "6.11.0"
WORK_DIR = Path("/work")
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
MANIFEST = "installation:\n  version: 6.11.0\n  installDate: 2026-08-24\nmodules: []\n"

#: A plan that installs the method — the shape this hook exists for.
INSTALLING_PLAN: tuple[tuple[str, str], ...] = (
    ("checkout", "git.worktree"),
    ("install", "bmad.install"),
    ("commit", "git.commit"),
)
#: A plan that does not: no `bmad.install` row anywhere in it.
NON_INSTALLING_PLAN: tuple[tuple[str, str], ...] = (
    ("checkout", "git.worktree"),
    ("stories[0].build", "agent"),
    ("stories[0].commit-guard", "git.commit"),
)


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
    def __init__(self, *, git: FakeGit | None, steps: bool = True) -> None:
        self.project = a_project()
        self.repository = a_repository(self.project.id)
        self.projects = FakeProjectRepository([self.project])
        self.repositories = FakeRepositoryRepository([self.repository])
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.uow = FakeUnitOfWork()
        self.uow.__enter__()
        self.ports = RunFinishedPorts(
            runs=self.runs,
            steps=self.steps if steps else None,
            repositories=self.repositories,
            projects=self.projects,
            git=git,
            uow=self.uow,
            clock=FakeClock(NOW),
            work_dir=WORK_DIR,
            bmad_version=BMAD_VERSION,
        )

    def add(self, run: Run, plan: tuple[tuple[str, str], ...] = INSTALLING_PLAN) -> Run:
        self.runs.add(run)
        self.steps.add_many(build_rows(run.id, plan))
        return run


def test_a_finished_installing_run_re_runs_its_repositorys_clone_check() -> None:
    harness = Harness(git=reachable_git())
    run = harness.add(a_run(harness.project.id, harness.repository.id))

    checked = on_finished(harness.ports, run.id)

    assert checked is not None
    assert checked.clone_check.bmad_version == BMAD_VERSION
    assert harness.repositories.get(harness.repository.id) == checked
    assert harness.uow.committed is True


def test_a_run_whose_plan_installs_no_method_is_a_no_op() -> None:
    """Whatever its Template is called: no `bmad.install` row, nothing to re-check."""
    harness = Harness(git=reachable_git())
    run = harness.add(
        a_run(harness.project.id, harness.repository.id, template_name="epic"),
        plan=NON_INSTALLING_PLAN,
    )

    result = on_finished(harness.ports, run.id)

    assert result is None
    assert harness.repository.clone_check.status == "pending"


def test_a_run_of_any_other_template_that_installs_the_method_is_not_a_no_op() -> None:
    """The point of the change: a Template of any name whose plan installs the method leaves
    the same stale manifest reading behind, so it gets the same re-check."""
    harness = Harness(git=reachable_git())
    run = harness.add(a_run(harness.project.id, harness.repository.id, template_name="house-init"))

    checked = on_finished(harness.ports, run.id)

    assert checked is not None
    assert checked.clone_check.bmad_version == BMAD_VERSION


def test_a_process_with_no_step_run_adapter_wired_is_a_no_op() -> None:
    harness = Harness(git=reachable_git(), steps=False)
    run = a_run(harness.project.id, harness.repository.id)
    harness.runs.add(run)

    assert on_finished(harness.ports, run.id) is None


def test_an_installing_run_that_is_not_done_is_a_no_op() -> None:
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
        steps=harness.steps,
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
