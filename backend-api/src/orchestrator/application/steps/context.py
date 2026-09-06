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

`process` and `workspace` default to `None` so `tests/unit/test_step_executor_registry.py`
and the walk's own tests — written before 4.7 existed — keep constructing `StepPorts` from
`git`, `clock` and `work_dir` alone; only a kind that actually starts a process or touches
the worktree needs either one set.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.domain.ports.workspace import Workspace
from orchestrator.domain.values import StepResult

#: What `StepPorts.workspace` is: a `Workspace` rooted at whichever path the caller names.
WorkspaceFactory = Callable[[str | None], Workspace]


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
