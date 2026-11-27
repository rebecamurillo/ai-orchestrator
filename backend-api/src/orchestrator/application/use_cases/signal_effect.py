"""The types a signal effect is made of: what it returns and what `cancel` leaves to its caller."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.values import Signal, Worktree


@dataclass(frozen=True)
class CancelPlan:
    """The worktree and process effects `cancel` leaves to its caller (4.9, AD-13)."""

    #: Every process group a live Attempt of this Run recorded.
    pgids: tuple[int, ...]
    #: Every worktree the Run holds, with the branch each one is on.
    worktrees: tuple[Worktree, ...]


@dataclass(frozen=True)
class Effect:
    """What one signal did to the rows, and what it asks `signal_run` to do to the Run."""

    #: Run fields the table lists beside the status change.
    run_update: dict[str, Any] = field(default_factory=dict)
    #: False when the Run keeps the status it had (the terminal kinds, a held budget raise).
    resume: bool = True
    #: True when the resumed Run has no row left to run and ends `done` instead.
    finished: bool = False
    #: Set by `cancel` only.
    cancel_plan: CancelPlan | None = None


#: One effect: the ports and the Run, the whole plan, the parked row, and the signal.
EffectFn = Callable[[WriterPorts, Run, Sequence[StepRun], StepRun | None, Signal], Effect]
