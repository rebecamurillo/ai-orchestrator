"""The `HarnessRepository` port: stored harnesses, without a database.

`get` answers `None` for "not stored" (the port's usual convention); the three names are
always stored by the time any request reaches them, because seeding runs before the
application binds a socket (`main.run_migrations`), but the type still allows for it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.entities.harness import Harness


@runtime_checkable
class HarnessRepository(Protocol):
    """Stored harnesses, by name."""

    def get(self, name: str) -> Harness | None:
        """The harness named `name`, or `None`."""
        ...

    def add(self, harness: Harness) -> None:
        """Store a harness that does not exist yet."""
        ...

    def update(self, harness: Harness) -> None:
        """Replace the stored harness with this one, matched on its name."""
        ...

    def list(self) -> list[Harness]:
        """Every stored harness, ordered by name."""
        ...
