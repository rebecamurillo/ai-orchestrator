"""Run the advances a missing project budget blocked, once the budget is set (AD-37).

The advance reads the project's defaults and blocks with `no project budget` when there is no
budget; nothing else wakes it. `retry_budget_advances` clears that one reason in a committed
unit of work, then hands each advance to the engine, so a crash between the two leaves a block
the start-up sweep picks up.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.rules.initiative_transitions import NO_PROJECT_BUDGET
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.initiatives import InitiativeAdvanceRepository, InitiativeRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class AdvanceRetryPorts:
    initiatives: InitiativeRepository
    advances: InitiativeAdvanceRepository
    uow: UnitOfWork
    engine: WorkflowEngine


def retry_budget_advances(ports: AdvanceRetryPorts, project_id: UUID) -> list[UUID]:
    """Clear `no project budget` on the project's unconsumed advances, then enqueue them."""
    cleared: list[UUID] = []
    with ports.uow:
        for initiative in ports.initiatives.list(project_id=project_id):
            for advance in ports.advances.list_for_initiative(initiative.id):
                if advance.consumed_at is None and advance.blocked_reason == NO_PROJECT_BUDGET:
                    ports.advances.update(advance.model_copy(update={"blocked_reason": None}))
                    cleared.append(advance.id)
        ports.uow.commit()
    for advance_id in cleared:
        ports.engine.enqueue_advance(advance_id)
    return cleared
