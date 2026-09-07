"""`run_clone_check_job` (SPEC CAP-11, FR-4): the daily re-check of every Repository.

The four-line check itself is `application/use_cases/clone_check.py`'s own, proven in
`tests/unit/test_clone_check_use_cases.py`; what this module proves is the job's own
question — every Project, every Repository under it — and that a failure is stored without
raising, which is what leaves a new Run blocked at pre-flight rather than this job.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.jobs.clone_check import run_clone_check_job
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import (
    DEFAULT_PACKAGE_MANAGER,
    DEFAULT_TEST_GLOBS,
    CloneCheck,
    Repository,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import CloneResult, GitError, RemoteRef
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

AT = datetime(2026, 9, 7, tzinfo=UTC)
WORK_DIR = Path("/work")
BMAD_VERSION = "6.11.0"
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
MANIFEST = "installation:\n  version: 6.11.0\n"


def a_project(slug: str = "my-project") -> Project:
    return Project(
        id=new_id(),
        slug=slug,
        name=slug,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=AT,
        updated_at=AT,
    )


def a_repository(project_id: object, slug: str = "my-repo") -> Repository:
    return Repository(  # type: ignore[call-arg]
        id=new_id(),
        project_id=project_id,
        slug=slug,
        url=f"https://github.com/org/{slug}.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=DEFAULT_TEST_GLOBS,
        package_manager=DEFAULT_PACKAGE_MANAGER,
        clone_check=CloneCheck.pending(),
        created_at=AT,
        updated_at=AT,
    )


def reachable() -> FakeGit:
    return FakeGit(
        ls_remote=[RemoteRef(ref="HEAD", sha=SHA), RemoteRef(ref="refs/heads/main", sha=SHA)],
        clone_base=[CloneResult(seconds=1.0, bytes=4096)],
        read_file=[MANIFEST],
    )


def a_ports(
    git: FakeGit, projects: FakeProjectRepository, repositories: FakeRepositoryRepository
) -> ProjectPorts:
    uow = FakeUnitOfWork()
    uow.__enter__()
    return ProjectPorts(
        uow=uow,
        projects=projects,
        repositories=repositories,
        crypto=None,  # type: ignore[arg-type] — the job never encrypts anything
        clock=FakeClock(AT),
        git=git,
    )


def test_every_repository_of_every_project_is_checked() -> None:
    projects = FakeProjectRepository()
    repositories = FakeRepositoryRepository()
    first, second = a_project("first"), a_project("second")
    projects.add(first)
    projects.add(second)
    repo_one = a_repository(first.id, "repo-one")
    repo_two = a_repository(second.id, "repo-two")
    repositories.add(repo_one)
    repositories.add(repo_two)
    ports = a_ports(reachable(), projects, repositories)

    run_clone_check_job(ports, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)

    assert repositories.get(repo_one.id).clone_check.status == "ok"  # type: ignore[union-attr]
    assert repositories.get(repo_two.id).clone_check.status == "ok"  # type: ignore[union-attr]


def test_a_repository_whose_origin_is_unreachable_is_stored_failed_and_blocks_no_run() -> None:
    """FR-4's own AC: `clone_check.status` becomes `failed`, and the job writes no Run at all."""
    projects = FakeProjectRepository()
    repositories = FakeRepositoryRepository()
    project = a_project()
    projects.add(project)
    repository = a_repository(project.id)
    repositories.add(repository)
    unreachable = GitError(command="git ls-remote", exit_code=128, output="fatal: not found")
    git = FakeGit(ls_remote=[unreachable])
    ports = a_ports(git, projects, repositories)

    run_clone_check_job(ports, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)

    stored = repositories.get(repository.id)
    assert stored is not None
    assert stored.clone_check.status == "failed"


def test_a_project_with_no_repositories_is_skipped_without_error() -> None:
    projects = FakeProjectRepository()
    projects.add(a_project())
    ports = a_ports(reachable(), projects, FakeRepositoryRepository())

    run_clone_check_job(ports, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)
