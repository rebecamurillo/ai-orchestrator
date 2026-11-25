"""Reads of Runs by initiative (AD-36)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.initiative import InitiativeKey
from orchestrator.domain.entities.run import Run


@runtime_checkable
class InitiativeRunReads(Protocol):
    def get_by_initiative_key(self, key: InitiativeKey) -> Run | None: ...

    def list_for_initiative(self, initiative_id: UUID) -> list[Run]:
        """Ordered by `created_at`, oldest first."""
        ...
