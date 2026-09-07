"""What an executor is handed and what it must be (AD-9): `StepContext` and `StepExecutor`.

One kind, one module, one protocol. An executor is a pure function over its context: it
reads the row the planner recorded, does the kind's work through the ports it was given,
and returns a `StepResult`. It never writes a status, never reaches a repository, and never
imports `infrastructure` — `StepPorts` is built once in `main.py` and travels here (AD-2,
AD-8).

`StepContext` is the spine's own field list. Two of them carry a rule:

- **`with_resolved` is the row's, not the Template's.** The planner resolved every
  expression before the Run started (AD-7); an executor that re-read a Template would be
  re-planning mid-Run.
- **`resume_signal` is a `GateRecord`, not a `Signal`.** AD-9 says the worktree effects of
  a signal happen in the resumed row's executor, and the record is what `signal_run` wrote
  and committed — so the executor reads a durable row rather than a message the engine
  happened to carry.

`StepPorts` holds what the executors of this epic can reach today. It grows with them:
4.7 adds the `ProcessRunner` and the `Workspace`, 4.8 needs nothing new, Epic 5 adds the
harnesses and the gateway. Every field is a port or a plain value, so a unit test builds
one from the shared fakes.

**`workspace` is a factory, not an instance.** `Git`, `Clock` and `process` are the same
object for every row of every Run — nothing about them depends on which Run is executing.
A `Workspace` is rooted at `run.worktree_path`, which is a fact of one Run, so `StepPorts`
(built once, in the composition root, before any Run exists) cannot hold a rooted instance
without holding a stale one for every Run after the first. `StepPorts.workspace(ctx.cwd)`
builds the one the current row needs, on demand, from the root the walker already read.

**`run_env` is resolved by the walker, not fetched by the executor.** AD-9 closes
`StepContext`'s field list, and an executor needs facts the row cannot carry: where this
Repository's clone lives, what its `install_command` says, which branch is its default, and
which worktrees this Run has already made. `ports` is the field AD-9 leaves open, so the
walker's `attempt_row` step reads those once, before the executor runs, and hands them over
as a frozen `RunEnvironment` inside `StepPorts` (`infrastructure/dbos/walker.py`). The
executor therefore reads a value and never a repository, which is what AD-8 asks for.

`process`, `workspace`, `run_env` and `protected_paths` default to `None` so
`tests/unit/test_step_executor_registry.py`
and the walk's own tests — written before 4.7 existed — keep constructing `StepPorts` from
`git`, `clock` and `work_dir` alone; only a kind that actually starts a process or touches
the worktree needs either one set.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.domain.ports.protected_paths import ProtectedPaths
from orchestrator.domain.ports.tracer import Tracer
from orchestrator.domain.ports.workspace import Workspace
from orchestrator.domain.values import StepResult, Worktree

#: What `StepPorts.workspace` is: a `Workspace` rooted at whichever path the caller names.
WorkspaceFactory = Callable[[str | None], Workspace]

#: The directory a Repository's base clone lives in, under its Project's (AD-14). The same
#: word `use_cases/clone_check.py` uses, because it is the same directory.
BASE_DIRECTORY = "base"

#: The directory every worktree of a Repository lives under (AD-14). A `/` in a branch name
#: becomes a directory level, which is what `Path` does with it anyway.
WORKTREES_DIRECTORY = "wt"


@dataclass(frozen=True)
class RunEnvironment:
    """One Run's own facts, as the walker read them just before this row ran.

    A snapshot, not a handle: an executor cannot ask it a second question and cannot write
    through it. Everything here is either a Project/Repository column the plan was built from
    or a Run column an earlier row's `RunUpdates` set, so a row always sees what the row
    before it committed.
    """

    run_id: UUID
    project_slug: str
    repository_slug: str
    repository_url: str
    default_branch: str
    #: `""` when the Repository declares none — `git.worktree` then runs nothing.
    install_command: str
    #: The `BMAD_VERSION` this instance runs (AD-16), for `bmad.install`.
    bmad_version: str
    #: The Run input every dev-loop Template declares, or `None` (`repo-init@1` has none).
    spec_folder: str | None
    #: Every worktree this Run has made so far, as `run.worktrees[]` stands now.
    worktrees: tuple[Worktree, ...] = ()
    #: Every compare URL this Run has recorded so far (`initiative@1` records one per epic).
    compare_urls: tuple[str, ...] = ()
    #: `run.accepted_paths` — files an earlier `continue` let through (AD-9).
    accepted_paths: tuple[str, ...] = ()

    def base_dir(self, work_dir: str) -> Path:
        """`{work_dir}/{project.slug}/{repository.slug}/base` — the one layout (AD-14)."""
        return Path(work_dir) / self.project_slug / self.repository_slug / BASE_DIRECTORY

    def worktree_dir(self, work_dir: str, branch: str) -> Path:
        """`{work_dir}/{project.slug}/{repository.slug}/wt/{branch}` (AD-14)."""
        root = Path(work_dir) / self.project_slug / self.repository_slug / WORKTREES_DIRECTORY
        return root / branch

    def worktree_at(self, path: str | None) -> Worktree | None:
        """The recorded worktree this Run is standing in, or `None` before there is one."""
        return next((entry for entry in self.worktrees if entry.path == path), None)


@dataclass(frozen=True)
class StepPorts:
    """The outside world an executor is allowed to reach, built in the composition root."""

    git: Git
    clock: Clock
    #: `WORK_DIR`: the root every worktree and every log file of every Run lives under.
    work_dir: str
    #: `None` until a kind that runs a command needs it (4.7 registers the first one).
    process: ProcessRunner | None = None
    #: `None` until a kind that reads or writes the worktree needs it (4.7 registers the
    #: first one). A factory rather than an instance — see the module docstring.
    workspace: WorkspaceFactory | None = None
    #: The Run this row belongs to, as the walker read it (4.8). `None` in a process that
    #: never resolved one, which is every unit test not about a git kind.
    run_env: RunEnvironment | None = None
    #: AD-17's frozen-anchor rule. `None` throughout Epic 4 — the port is the seam Epic 5
    #: fills; `domain/ports/protected_paths.py` says why that is not a green check.
    protected_paths: ProtectedPaths | None = None
    #: `None` until a caller wires a real one (5.2). `run_row` degrades to "no span opened"
    #: when unset — every frozen `StepPorts(...)` construction predating this story keeps
    #: working unchanged; 5.4's agent executor reaches this the same way, through
    #: `context.ports.tracer`, so `WalkPorts` itself needs no `Tracer` of its own (AD-11).
    tracer: Tracer | None = None


@dataclass(frozen=True)
class StepContext:
    """Everything the executor of one row needs, and nothing it could use to write state."""

    row: StepRun
    with_resolved: dict[str, Any]
    #: `run.worktree_path` — `None` before `git.worktree` has made one (4.8).
    cwd: str | None
    #: The commit the row's Story frame started at, or `None` outside a frame (Epic 5).
    frame_start_sha: str | None
    #: The attempt before this one at the same row, or `None` for a row's first attempt.
    previous_attempt: Attempt | None
    attempt: Attempt
    #: The gate record of the Operator signal that resumed this row, or `None` (AD-9).
    resume_signal: GateRecord | None
    ports: StepPorts


@runtime_checkable
class StepExecutor(Protocol):
    """One step kind's whole behaviour: context in, result out, no status written."""

    def execute(self, ctx: StepContext) -> StepResult:
        """Do the kind's work and report what the row reached."""
        ...


def log_path(ctx: StepContext) -> Path:
    """`/work/logs/{run_id}/{seq:03d}-{attempt_n}.log` — one path, computed the same way

    by every kind that starts a process. Nothing here reads the filesystem: the path is a
    pure function of the Run, the row and the attempt, so any kind can compute it before
    `ProcessRunner.start` creates the file it names.
    """
    return (
        Path(ctx.ports.work_dir)
        / "logs"
        / str(ctx.attempt.run_id)
        / f"{ctx.row.seq:03d}-{ctx.attempt.n}.log"
    )


#: What an unset port on `StepPorts` means: a composition-root wiring bug, not a row's. The
#: three git kinds need all of them, so the refusal is here rather than six times over.
NO_ENVIRONMENT = "StepPorts.run_env is not set: a git kind needs the Run's environment"
NO_RUNNER = "StepPorts.process is not set: this kind needs a ProcessRunner"
NO_WORKSPACE = "StepPorts.workspace is not set: this kind needs a Workspace"
#: What a git kind says when it is reached before `git.worktree` has made a worktree.
NO_WORKTREE = "no worktree: {path} runs before git.worktree"


def require_env(ctx: StepContext) -> RunEnvironment:
    """The Run's environment, or the wiring bug that it was never resolved."""
    if ctx.ports.run_env is None:
        raise RuntimeError(NO_ENVIRONMENT)
    return ctx.ports.run_env


def require_process(ctx: StepContext) -> ProcessRunner:
    """The process runner, or the wiring bug that none was built."""
    if ctx.ports.process is None:
        raise RuntimeError(NO_RUNNER)
    return ctx.ports.process


def require_workspace(ctx: StepContext, root: str | None) -> Workspace:
    """A `Workspace` rooted where the caller says, or the wiring bug that none was built."""
    if ctx.ports.workspace is None:
        raise RuntimeError(NO_WORKSPACE)
    return ctx.ports.workspace(root)


def require_cwd(ctx: StepContext) -> Path:
    """The worktree this row runs in — a row reached before `git.worktree` has none."""
    if ctx.cwd is None:
        raise RuntimeError(NO_WORKTREE.format(path=ctx.row.path))
    return Path(ctx.cwd)
