"""The instance hold (SPEC CAP-4, AD-30): an upgrade's promise that no step starts.

`place_hold` takes the hold's write lock, reads the working steps of `instance_activity`, and
refuses when any stand; nothing is written then. `hold_active` is the reader `start_attempt`
and `run_turn` call inside their own unit of work, under the shared lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from orchestrator.application.use_cases.instance_activity import WorkingStep, working_steps
from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.instance_hold import InstanceHoldRepository
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork

HOLD_REFUSED = "{count} working steps stand against the hold; nothing was held"


class HoldRefused(Conflict):
    def __init__(self, working: list[WorkingStep]) -> None:
        super().__init__(HOLD_REFUSED.format(count=len(working)))
        self.working = working


@dataclass(frozen=True)
class HoldPorts:
    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    holds: InstanceHoldRepository
    uow: UnitOfWork
    clock: Clock


def place_hold(ports: HoldPorts, ttl_seconds: int, reason: str) -> InstanceHold:
    """Hold the instance for `ttl_seconds`, or raise `HoldRefused` naming the working steps."""
    with ports.uow:
        current = ports.holds.get_for_update()
        working = working_steps(ports.runs, ports.steps, ports.attempts)
        if working:
            raise HoldRefused(working)
        now = ports.clock.now()
        hold = InstanceHold(
            id=current.id if current else new_id(),
            held_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            reason=reason,
        )
        ports.holds.put(hold)
        ports.uow.commit()
    return hold


def release_hold(holds: InstanceHoldRepository, uow: UnitOfWork) -> None:
    """Delete every hold row. Safe when there is none."""
    with uow:
        holds.delete_all()
        uow.commit()


def hold_active(holds: InstanceHoldRepository | None, now: datetime) -> bool:
    """Whether a hold stands, read under the shared lock inside the caller's open unit of work."""
    if holds is None:
        return False
    hold = holds.get_shared()
    return hold is not None and hold.active(now)
