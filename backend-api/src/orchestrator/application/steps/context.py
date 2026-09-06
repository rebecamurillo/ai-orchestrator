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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.values import StepResult


@dataclass(frozen=True)
class StepPorts:
    """The outside world an executor is allowed to reach, built in the composition root."""

    git: Git
    clock: Clock
    #: `WORK_DIR`: the root every worktree and every log file of every Run lives under.
    work_dir: str


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
