"""`run_worktree_gc` (SPEC CAP-11, FR-9, AD-14): free a terminal Run's worktrees and logs.

`Git.remove_worktree` and `Workspace.remove` are both idempotent (module docstring); what
this suite proves is the *decision* — which Run is due, and only once — over the shared
fakes, never a real filesystem or a real git command.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from orchestrator.application.jobs.worktree_gc import WorktreeGcPorts, run_worktree_gc
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Worktree
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

NOW = datetime(2026, 9, 7, tzinfo=UTC)
WORK_DIR = "/work"
RETENTION_DAYS = 7
PROJECT = new_id()
REPOSITORY = new_id()
BASE = Path("/work/p/r/base")


def a_worktree(path: str = "/work/p/r/wt/feat-x", branch: str = "feat/x") -> Worktree:
    return Worktree(branch=branch, path=path, created_branch=True, pushed=True)


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT,
        "repository_id": REPOSITORY,
        "template_name": "epic",
        "template_version": 1,
        "status": "done",
        "budget_usd": 0,
        "inputs": {},
        "worktrees": (a_worktree(),),
        "created_at": NOW - timedelta(days=30),
        "ended_at": NOW - timedelta(days=8),
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def an_environment(run_id: UUID) -> RunEnvironment:
    return RunEnvironment(
        run_id=run_id,
        project_slug="p",
        repository_slug="r",
        repository_url="https://github.com/org/r.git",
        default_branch="main",
        install_command="",
        bmad_version="6.11.0",
        spec_folder=None,
    )


def _read_environment(known: dict[UUID, RunEnvironment], run_id: UUID) -> RunEnvironment | None:
    return known.get(run_id)


def a_ports(
    runs: FakeRunRepository,
    git: FakeGit,
    logs: FakeWorkspace,
    *,
    known: dict[UUID, RunEnvironment] | None = None,
    retention_days: int = RETENTION_DAYS,
) -> WorktreeGcPorts:
    environments = known or {}
    uow = FakeUnitOfWork()
    uow.__enter__()
    return WorktreeGcPorts(
        uow=uow,
        runs=runs,
        git=git,
        logs=logs,
        clock=FakeClock(NOW),
        read_environment=lambda run_id: _read_environment(environments, run_id),
        work_dir=WORK_DIR,
        retention_days=retention_days,
    )


def a_logs_workspace(**files: str) -> FakeWorkspace:
    return FakeWorkspace(root="/work/logs", files=files)


def test_only_the_older_run_is_swept() -> None:
    old = a_run(
        ended_at=NOW - timedelta(days=8),
        worktrees=(a_worktree("/work/p/r/wt/old", "old"),),
    )
    recent = a_run(
        ended_at=NOW - timedelta(days=1),
        worktrees=(a_worktree("/work/p/r/wt/recent", "recent"),),
    )
    runs = FakeRunRepository([old, recent])
    git = FakeGit()
    logs = a_logs_workspace(**{f"{old.id}/001-1.log": "x", f"{recent.id}/001-1.log": "y"})
    known = {old.id: an_environment(old.id), recent.id: an_environment(recent.id)}
    ports = a_ports(runs, git, logs, known=known)

    swept = run_worktree_gc(ports)

    assert swept == [old.id]
    assert ("remove_worktree", (BASE, Path(old.worktrees[0].path))) in git.calls
    removed_paths = [call[1][1] for call in git.calls if call[0] == "remove_worktree"]
    assert Path(recent.worktrees[0].path) not in removed_paths
    assert logs.exists(f"{recent.id}/001-1.log")
    assert not logs.exists(f"{old.id}/001-1.log")
    assert runs.runs[old.id].worktrees_removed is True
    assert runs.runs[recent.id].worktrees_removed is False


def test_a_non_terminal_run_is_never_swept() -> None:
    run = a_run(status="running", ended_at=None)
    runs = FakeRunRepository([run])
    ports = a_ports(runs, FakeGit(), a_logs_workspace(), known={run.id: an_environment(run.id)})

    swept = run_worktree_gc(ports)

    assert swept == []
    assert runs.runs[run.id].worktrees_removed is False


def test_a_run_already_swept_is_not_swept_again() -> None:
    """Idempotent (FR-9): a second fire of the same cron finds nothing left to do."""
    run = a_run(worktrees_removed=True)
    runs = FakeRunRepository([run])
    git = FakeGit()
    ports = a_ports(runs, git, a_logs_workspace(), known={run.id: an_environment(run.id)})

    swept = run_worktree_gc(ports)

    assert swept == []
    assert not any(call[0] == "remove_worktree" for call in git.calls)


def test_a_run_ended_within_the_retention_window_is_left_alone() -> None:
    run = a_run(ended_at=NOW - timedelta(days=3))
    runs = FakeRunRepository([run])
    ports = a_ports(runs, FakeGit(), a_logs_workspace(), known={run.id: an_environment(run.id)})

    swept = run_worktree_gc(ports)

    assert swept == []


def test_a_run_whose_environment_is_gone_still_has_its_logs_removed_and_is_marked_swept() -> None:
    """A deleted Project/Repository underneath a Run: no base to remove a worktree from, but
    the log directory and the record still get the same treatment (module docstring)."""
    run = a_run()
    runs = FakeRunRepository([run])
    git = FakeGit()
    logs = a_logs_workspace(**{f"{run.id}/001-1.log": "x"})
    ports = a_ports(runs, git, logs, known={})

    swept = run_worktree_gc(ports)

    assert swept == [run.id]
    assert not any(call[0] == "remove_worktree" for call in git.calls)
    assert not logs.exists(f"{run.id}/001-1.log")
    assert runs.runs[run.id].worktrees_removed is True


def test_every_worktree_of_a_run_is_removed() -> None:
    run = a_run(
        worktrees=(
            a_worktree("/work/p/r/wt/a", "a"),
            a_worktree("/work/p/r/wt/b", "b"),
        )
    )
    runs = FakeRunRepository([run])
    git = FakeGit()
    ports = a_ports(runs, git, a_logs_workspace(), known={run.id: an_environment(run.id)})

    run_worktree_gc(ports)

    removed = [call[1][1] for call in git.calls if call[0] == "remove_worktree"]
    assert removed == [Path("/work/p/r/wt/a"), Path("/work/p/r/wt/b")]
