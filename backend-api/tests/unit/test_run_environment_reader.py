"""`infrastructure/db/environment.py`: the Run's facts, read once, on a session of its own.

The three reads are recorded rather than real — that the four adapters build the SQL they
claim is `tests/unit/test_run_repository_adapter.py`'s, and that the schema matches is the
e2e suite's. What is asserted here is what this module decides: which columns become which
fields, that a Run whose Project or Repository is gone answers `None` rather than raising
inside a durable step, and that the session is closed on every path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Worktree
from orchestrator.infrastructure.db import environment as module
from orchestrator.infrastructure.db.environment import read_run_environment

NOW = datetime(2026, 9, 6, tzinfo=UTC)
BMAD_VERSION = "6.11.0"
SPEC_FOLDER = "_bmad-output/planning-artifacts/mvp/epics/epic-04-runs"
WORKTREE = Worktree(
    branch="feat/x",
    path="/work/acme/widgets/wt/feat/x",
    created_branch=True,
    pushed=False,
)
COMPARE = "https://github.com/acme/widgets/compare/main...feat/x"


class RecordingSession:
    """A session that records only that it was closed — nothing here executes SQL."""

    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def a_project() -> Project:
    return Project(
        id=new_id(),
        name="Acme",
        slug="acme",
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
        install_command="uv sync",
        quality_gate_command="make check",
        unit_test_command="make test",
        test_globs=("tests/**",),
        package_manager="uv",
        clone_check=CloneCheck.pending(),
        created_at=NOW,
        updated_at=NOW,
    )


def a_run(project: Project, repository: Repository, **over: Any) -> Run:
    fields: dict[str, Any] = {
        "id": new_id(),
        "project_id": project.id,
        "repository_id": repository.id,
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10.00"),
        "created_at": NOW,
    }
    fields.update(over)
    return Run(**fields)


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


def wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    run: Run | None,
    project: Project | None,
    repository: Repository | None,
) -> None:
    """Replace the three adapters with ones answering exactly what a scenario names."""
    monkeypatch.setattr(module, "SQLAlchemyRunRepository", lambda _s: _Answering(run))
    monkeypatch.setattr(module, "SQLAlchemyProjectRepository", lambda _s: _Answering(project))
    monkeypatch.setattr(module, "SQLAlchemyRepositoryRepository", lambda _s: _Answering(repository))


class _Answering:
    def __init__(self, answer: object) -> None:
        self.answer = answer

    def get(self, _id: UUID) -> object:
        return self.answer


def test_every_field_a_git_executor_reads_comes_off_the_three_rows(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(
        project,
        repository,
        inputs={"spec_folder": SPEC_FOLDER},
        worktrees=(WORKTREE,),
        compare_urls=(COMPARE,),
        accepted_paths=("AGENTS.md",),
    )
    wire(monkeypatch, run=run, project=project, repository=repository)

    env = read_run_environment(lambda: session, BMAD_VERSION, run.id)

    assert env is not None
    assert env.run_id == run.id
    assert env.project_slug == "acme"
    assert env.repository_slug == "widgets"
    assert env.repository_url == repository.url
    assert env.default_branch == "main"
    assert env.bmad_version == BMAD_VERSION
    assert env.spec_folder == SPEC_FOLDER
    assert env.worktrees == (WORKTREE,)
    assert env.compare_urls == (COMPARE,)
    assert env.accepted_paths == ("AGENTS.md",)
    assert session.closed == 1


def test_a_run_that_declares_no_spec_folder_has_none(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    """`repo-init@1` declares none, and `git.commit` reads that as "stage everything"."""
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(project, repository, inputs={"base_branch": "main"})
    wire(monkeypatch, run=run, project=project, repository=repository)

    env = read_run_environment(lambda: session, BMAD_VERSION, run.id)

    assert env is not None
    assert env.spec_folder is None


def test_a_run_that_is_not_there_answers_none_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    wire(monkeypatch, run=None, project=None, repository=None)

    assert read_run_environment(lambda: session, BMAD_VERSION, new_id()) is None
    assert session.closed == 1


@pytest.mark.parametrize("missing", ["project", "repository"])
def test_a_run_whose_entities_were_deleted_answers_none(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession, missing: str
) -> None:
    project = a_project()
    repository = a_repository(project.id)
    run = a_run(project, repository)
    wire(
        monkeypatch,
        run=run,
        project=None if missing == "project" else project,
        repository=None if missing == "repository" else repository,
    )

    assert read_run_environment(lambda: session, BMAD_VERSION, run.id) is None


def test_the_session_is_closed_even_when_a_read_raises(
    monkeypatch: pytest.MonkeyPatch, session: RecordingSession
) -> None:
    class Raising:
        def __init__(self, _s: object) -> None: ...

        def get(self, _id: UUID) -> object:
            raise RuntimeError("the row was gone")

    monkeypatch.setattr(module, "SQLAlchemyRunRepository", Raising)

    with pytest.raises(RuntimeError, match="the row was gone"):
        read_run_environment(lambda: session, BMAD_VERSION, new_id())
    assert session.closed == 1
