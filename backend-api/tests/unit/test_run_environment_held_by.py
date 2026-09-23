"""`infrastructure/db/environment._held_by_label` (story 5-1, AD-14).

Verifies that `read_run_environment` correctly populates `env.held_by_label` when
another non-terminal Run shares the same (repository_id, partition_branch), and
that `held_by_label` is None in every other case.

The monkeypatching approach follows `test_run_environment_reader.py`: the three
SQLAlchemy adapters are replaced with in-process fakes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db import environment as module
from orchestrator.infrastructure.db.environment import read_run_environment

NOW = datetime(2026, 9, 18, tzinfo=UTC)
BMAD_VERSION = "6.11.0"


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


def a_run(project: Project, repository: Repository, **over: object) -> Run:
    fields: dict[str, object] = {
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
    return Run(**fields)  # type: ignore[arg-type]


class _RecordingSession:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class _RunRepo:
    """Minimal duck-typed fake with `get` and `list_by_repository_non_terminal`."""

    def __init__(self, run: Run | None, non_terminal: list[Run]) -> None:
        self._run = run
        self._non_terminal = non_terminal

    def get(self, _id: UUID) -> Run | None:
        return self._run

    def list_by_repository_non_terminal(self, repository_id: UUID) -> list[Run]:
        return [r for r in self._non_terminal if r.repository_id == repository_id]


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    run: Run | None,
    non_terminal: list[Run],
    project: Project | None,
    repository: Repository | None,
) -> None:
    """Patch all three adapters; SQLAlchemyRunRepository supports both `get` and list."""

    class _ProjectRepo:
        def get(self, _id: UUID) -> Project | None:
            return project

    class _RepoRepo:
        def get(self, _id: UUID) -> Repository | None:
            return repository

    monkeypatch.setattr(module, "SQLAlchemyRunRepository", lambda _s: _RunRepo(run, non_terminal))
    monkeypatch.setattr(module, "SQLAlchemyProjectRepository", lambda _s: _ProjectRepo())
    monkeypatch.setattr(module, "SQLAlchemyRepositoryRepository", lambda _s: _RepoRepo())


# ── held_by_label is set when another run holds the same partition ─────────────


def test_held_by_label_is_set_when_another_run_shares_partition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another non-terminal, enqueued Run with the same (repository_id, partition_branch)
    → label set.

    # Revised: a saved Run holds no branch (multi-repo initiative S2, spine AD-14
    # amendment, 2026-09-23). `engine_ref` set on `holder` so it is in the engine, which
    # is exactly the case that still holds; the saved case is the new test below.
    """
    project = a_project()
    repository = a_repository(project.id)
    target = a_run(project, repository, partition_branch="feat/s")
    holder = a_run(
        project,
        repository,
        template_name="epic",
        status="running",
        partition_branch="feat/s",
        engine_ref={"ref": 1},
    )
    session = _RecordingSession()

    _wire(
        monkeypatch,
        run=target,
        non_terminal=[target, holder],
        project=project,
        repository=repository,
    )

    env = read_run_environment(lambda: session, BMAD_VERSION, target.id)

    assert env is not None
    assert env.held_by_label == "epic · feat/s"


# ── held_by_label is None when the only sharer is a saved Run ─────────────────


def test_held_by_label_is_none_when_the_only_sharer_is_a_saved_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A saved Run (`engine_ref` empty) sharing the partition has materialised no worktree
    and is not the holder.

    # Revised: a saved Run holds no branch (multi-repo initiative S2, spine AD-14
    # amendment, 2026-09-23).
    """
    project = a_project()
    repository = a_repository(project.id)
    target = a_run(project, repository, partition_branch="feat/s")
    saved = a_run(
        project,
        repository,
        template_name="epic",
        status="queued",
        partition_branch="feat/s",
        engine_ref={},
    )
    session = _RecordingSession()

    _wire(
        monkeypatch,
        run=target,
        non_terminal=[target, saved],
        project=project,
        repository=repository,
    )

    env = read_run_environment(lambda: session, BMAD_VERSION, target.id)

    assert env is not None
    assert env.held_by_label is None


# ── held_by_label is None when no other run holds the partition ────────────────


def test_held_by_label_is_none_when_no_holder_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No other run on the same (repository_id, partition_branch) → held_by_label is None."""
    project = a_project()
    repository = a_repository(project.id)
    target = a_run(project, repository, partition_branch="feat/s")
    session = _RecordingSession()

    _wire(
        monkeypatch,
        run=target,
        non_terminal=[target],
        project=project,
        repository=repository,
    )

    env = read_run_environment(lambda: session, BMAD_VERSION, target.id)

    assert env is not None
    assert env.held_by_label is None


# ── held_by_label is None when the run has no partition_branch ────────────────


def test_held_by_label_is_none_when_run_has_no_partition_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Old run with partition_branch=None is non-competing; held_by_label is None."""
    project = a_project()
    repository = a_repository(project.id)
    target = a_run(project, repository)  # partition_branch defaults to None
    other = a_run(project, repository, partition_branch="feat/s")
    session = _RecordingSession()

    _wire(
        monkeypatch,
        run=target,
        non_terminal=[target, other],
        project=project,
        repository=repository,
    )

    env = read_run_environment(lambda: session, BMAD_VERSION, target.id)

    assert env is not None
    assert env.held_by_label is None


# ── held_by_label is None when holder is on a different partition branch ──────


def test_held_by_label_is_none_when_other_run_has_different_partition_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Different partition branches on the same repository do not trigger held_by_label."""
    project = a_project()
    repository = a_repository(project.id)
    target = a_run(project, repository, partition_branch="feat/s1")
    other = a_run(project, repository, partition_branch="feat/s2")
    session = _RecordingSession()

    _wire(
        monkeypatch,
        run=target,
        non_terminal=[target, other],
        project=project,
        repository=repository,
    )

    env = read_run_environment(lambda: session, BMAD_VERSION, target.id)

    assert env is not None
    assert env.held_by_label is None
