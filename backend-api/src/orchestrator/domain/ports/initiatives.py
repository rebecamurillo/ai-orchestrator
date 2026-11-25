"""The initiative ports (AD-36)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance


@runtime_checkable
class InitiativeRepository(Protocol):
    """Stored initiatives."""

    def add(self, initiative: Initiative) -> None:
        """Insert; a second open `(repository_id, slug)` is refused."""
        ...

    def get(self, initiative_id: UUID) -> Initiative | None: ...

    def get_for_update(self, initiative_id: UUID) -> Initiative | None:
        """As `get`, holding a row lock until the unit of work ends."""
        ...

    def update(self, initiative: Initiative) -> None: ...

    def mark_opened(self, initiative_id: UUID, at: datetime) -> None:
        """Set `last_opened_at` only; `updated_at` stays as it was (a view is not a change)."""
        ...

    def get_open_by_slug(self, repository_id: UUID, slug: str) -> Initiative | None:
        """The initiative holding the slug (not cancelled), or `None`."""
        ...

    def list_by_slug(self, repository_id: UUID, slug: str) -> list[Initiative]:
        """Every initiative of the slug, in creation order."""
        ...

    def list_open_for_package(self, project_id: UUID, package_name: str) -> list[Initiative]:
        """Open initiatives whose sequence names the package, in creation order."""
        ...

    # Declared last: inside the class body `list` would shadow the builtin in the
    # annotations below it.
    def list(self, *, project_id: UUID | None = None) -> list[Initiative]:
        """Newest first."""
        ...


@runtime_checkable
class InitiativeAdvanceRepository(Protocol):
    """Stored advances."""

    def add(self, advance: InitiativeAdvance) -> None: ...

    def list_for_initiative(self, initiative_id: UUID) -> list[InitiativeAdvance]:
        """In `(round, position)` order."""
        ...

    def list_unconsumed(self) -> list[InitiativeAdvance]:
        """Every advance with no `consumed_at`, in `(round, position, id)` order."""
        ...

    def get(self, advance_id: UUID) -> InitiativeAdvance | None: ...

    def update(self, advance: InitiativeAdvance) -> None:
        """Write `blocked_reason` and `consumed_at` of a stored advance."""
        ...
