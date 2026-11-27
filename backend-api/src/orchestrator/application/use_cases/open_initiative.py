"""Her last view of an initiative: `?opened=true` moves `last_opened_at` to now (story 6, epic 7).

The one write of the initiative page's read. It writes no Run, row or status (hard rule 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.use_cases.initiative_view_types import PriorView
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.initiatives import InitiativeRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class OpenInitiativePorts:
    initiatives: InitiativeRepository
    uow: UnitOfWork
    clock: Clock


def open_initiative(ports: OpenInitiativePorts, initiative_id: UUID) -> PriorView:
    """Stamp `last_opened_at`; answer the value that was there, the cutoff of `changed`."""
    # `get_for_update` is the lock every initiative writer takes first, so a concurrent
    # cancel's full-row `update` can neither lose this write nor be lost by it.
    initiative = ports.initiatives.get_for_update(initiative_id)
    if initiative is None:
        raise NotFound(f"no initiative {initiative_id}")
    ports.initiatives.mark_opened(initiative_id, ports.clock.now())
    ports.uow.commit()
    return PriorView(at=initiative.last_opened_at)
