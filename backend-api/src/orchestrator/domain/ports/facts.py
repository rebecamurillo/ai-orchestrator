"""The fact ports: append-only storage of what attempts did (AGENTS.md "Data capture").

No update and no delete exist here, on purpose.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, FactSet, GatewayRead, UsageFact


@runtime_checkable
class FactSetRepository(Protocol):
    """Stored fact sets and their rows."""

    def add(self, fact_set: FactSet, facts: AttemptFacts) -> bool:
        """Store the set and its rows; `False`, nothing written, when the
        `(attempt_id, extractor, extractor_version)` triple is already stored."""
        ...

    def list_for_attempt(self, attempt_id: UUID) -> list[FactSet]:
        """Every fact set of this attempt."""
        ...

    def rows(self, fact_set_id: UUID) -> AttemptFacts:
        """The rows stored under one fact set."""
        ...

    def unrecorded_attempts(self, limit: int) -> list[Attempt]:
        """Ended attempts of a harness with no fact set of any extractor, oldest end first."""
        ...


@runtime_checkable
class GatewayReadRepository(Protocol):
    """Stored gateway reads and the usage rows each carries."""

    def add(self, read: GatewayRead, usage: tuple[UsageFact, ...]) -> None:
        """Store one read and its usage rows."""
        ...

    def list_for_attempt(self, attempt_id: UUID) -> list[GatewayRead]:
        """Every read of this attempt, newest first."""
        ...

    def usage(self, read_id: UUID) -> tuple[UsageFact, ...]:
        """The usage rows stored under one read."""
        ...
