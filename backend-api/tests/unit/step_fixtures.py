"""What every git-kind test builds a `StepContext` from, once (AD-18: fakes are shared).

Six modules assert on six executors that take the same context and the same four ports, so
the row, the attempt and the `StepPorts` are built here rather than six times over. Nothing
here decides anything: a test names the pieces it cares about and takes the defaults for the
rest, which is what keeps each test's own body about its own rule.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from orchestrator.application.steps.context import (
    RunEnvironment,
    StepContext,
    StepPorts,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.domain.ports.protected_paths import ProtectedPaths
from orchestrator.domain.statuses import GateEvent
from orchestrator.domain.values import Worktree
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.workspace import FakeWorkspace

WORK_DIR = "/work"
PROJECT_SLUG = "acme"
REPOSITORY_SLUG = "widgets"
REPOSITORY_URL = "https://github.com/acme/widgets.git"
DEFAULT_BRANCH = "main"
BMAD_VERSION = "6.11.0"
BRANCH = "chore/bmad-init"
BASE_DIR = f"{WORK_DIR}/{PROJECT_SLUG}/{REPOSITORY_SLUG}/base"
WORKTREE = f"{WORK_DIR}/{PROJECT_SLUG}/{REPOSITORY_SLUG}/wt/{BRANCH}"


def an_environment(**overrides: Any) -> RunEnvironment:
    """The Run's environment as the walker resolves it, with the story's own defaults."""
    fields: dict[str, Any] = {
        "run_id": new_id(),
        "project_slug": PROJECT_SLUG,
        "repository_slug": REPOSITORY_SLUG,
        "repository_url": REPOSITORY_URL,
        "default_branch": DEFAULT_BRANCH,
        "install_command": "",
        "bmad_version": BMAD_VERSION,
        "spec_folder": None,
    }
    fields.update(overrides)
    return RunEnvironment(**fields)


def a_worktree(
    *, branch: str = BRANCH, path: str = WORKTREE, created_branch: bool = True, pushed: bool = False
) -> Worktree:
    return Worktree(branch=branch, path=path, created_branch=created_branch, pushed=pushed)


def a_row(*, kind: str, with_resolved: dict[str, Any], path: str = "checkout") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=2,
        path=path,
        label=path,
        kind=kind,
        gate="deterministic",
        status="running",
        with_resolved=with_resolved,
    )


def a_context(  # noqa: PLR0913 — one keyword per port or context field, each optional
    row: StepRun,
    *,
    env: RunEnvironment | None = None,
    git: Git | None = None,
    process: ProcessRunner | None = None,
    workspace: FakeWorkspace | None = None,
    protected_paths: ProtectedPaths | None = None,
    cwd: str | None = WORKTREE,
    resume: GateEvent | None = None,
) -> StepContext:
    """One row's context: AD-9's field list, over whichever fakes the test named."""
    made = workspace if workspace is not None else FakeWorkspace()
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=cwd,
        frame_start_sha=None,
        previous_attempt=None,
        attempt=Attempt(id=new_id(), run_id=row.run_id, step_run_id=row.id, n=1, status="running"),
        resume_signal=_record(row, resume),
        ports=StepPorts(
            git=git if git is not None else FakeGit(),
            clock=FakeClock(EPOCH),
            work_dir=WORK_DIR,
            process=process,
            workspace=lambda _root: made,
            run_env=env if env is not None else an_environment(),
            protected_paths=protected_paths,
        ),
    )


def _record(row: StepRun, resume: GateEvent | None) -> GateRecord | None:
    """The gate record `signal_run` wrote for the signal that resumed this row (AD-9)."""
    if resume is None:
        return None
    return GateRecord(
        id=new_id(),
        run_id=row.run_id,
        at=EPOCH,
        event=resume,
        actor="operator",
        path=row.path,
        text="",
    )


def without(context: StepContext, **ports: Any) -> StepContext:
    """The same context with one port unset — what a composition-root wiring bug looks like."""
    return replace(context, ports=replace(context.ports, **ports))
