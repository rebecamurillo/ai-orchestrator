"""`infrastructure/db/run_finished.py`: `on_finished` wired to a session of its own.

The rule itself is `tests/unit/application/test_run_finished.py`'s; what is asserted here,
the way `test_run_environment_reader.py` does for its own sibling module, is the wiring:
which adapter reads which session, and that the session is closed on every path — proven
over a recording session rather than a database, since the SQL each adapter builds is
`tests/unit/test_run_repository_adapter.py`'s own subject.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import DEFAULT_TEST_GLOBS, CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import CloneResult, RemoteRef
from orchestrator.infrastructure.db import run_finished as module
from orchestrator.infrastructure.db.run_finished import run_finished_hook
from tests.unit.fakes.git import FakeGit

NOW = datetime(2026, 9, 6, tzinfo=UTC)
BMAD_VERSION = "6.11.0"
WORK_DIR = Path("/work")
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
MANIFEST = "installation:\n  version: 6.11.0\n  installDate: 2026-08-24\nmodules: []\n"


class RecordingSession:
    """A session that records only that it was closed and committed — no SQL runs here."""

    def __init__(self) -> None:
        self.closed = 0
        self.committed = 0

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed += 1


class _Answering:
    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.updated: list[object] = []

    def get(self, _id: UUID) -> object:
        return self.answer

    def update(self, value: object) -> None:
        self.updated.append(value)


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


def a_repository(project_id: UUID) -> Repository:
    return Repository(
        id=new_id(),
        project_id=project_id,
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


def a_run(project_id: UUID, repository_id: UUID, **overrides: object) -> Run:
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


def reachable_git() -> FakeGit:
    return FakeGit(
        ls_remote=[RemoteRef(ref="HEAD", sha=SHA), RemoteRef(ref="refs/heads/main", sha=SHA)],
        clone_base=[CloneResult(seconds=1.0, bytes=4096)],
        read_file=[MANIFEST],
    )


def wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    run: Run | None,
    project: Project | None,
    repository: Repository | None,
) -> _Answering:
    monkeypatch.setattr(module, "SQLAlchemyRunRepository", lambda _s: _Answering(run))
    monkeypatch.setattr(module, "SQLAlchemyProjectRepository", lambda _s: _Answering(project))
    repositories = _Answering(repository)
    monkeypatch.setattr(module, "SQLAlchemyRepositoryRepository", lambda _s: repositories)
    return repositories


def test_a_finished_repo_init_run_writes_back_through_the_wired_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(project.id, repository.id)
    repositories = wire(monkeypatch, run=run, project=project, repository=repository)
    session = RecordingSession()

    run_finished_hook(lambda: session, reachable_git(), WORK_DIR, BMAD_VERSION, run.id)

    assert len(repositories.updated) == 1
    assert repositories.updated[0].clone_check.bmad_version == BMAD_VERSION
    assert session.committed == 1
    assert session.closed == 1


def test_the_session_is_closed_even_when_there_is_nothing_to_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch, run=None, project=None, repository=None)
    session = RecordingSession()

    run_finished_hook(lambda: session, reachable_git(), WORK_DIR, BMAD_VERSION, new_id())

    assert session.committed == 0
    assert session.closed == 1


def test_the_session_is_closed_when_theres_no_git_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(project.id, repository.id)
    wire(monkeypatch, run=run, project=project, repository=repository)
    session = RecordingSession()

    run_finished_hook(lambda: session, None, WORK_DIR, BMAD_VERSION, run.id)

    assert session.committed == 0
    assert session.closed == 1
