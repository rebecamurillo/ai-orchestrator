"""The `InstanceHoldRepository` port (SPEC CAP-4, AD-30): the one hold row, and its locks."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.entities.instance_hold import InstanceHold


@runtime_checkable
class InstanceHoldRepository(Protocol):
    def get(self) -> InstanceHold | None:
        """The hold, read with no lock."""
        ...

    def get_shared(self) -> InstanceHold | None:
        """The hold under a lock every other shared reader passes and a writer waits on,
        held to the end of the transaction."""
        ...

    def get_for_update(self) -> InstanceHold | None:
        """The writer's lock: excludes other writers and shared readers until the
        transaction ends, also when no row exists."""
        ...

    def put(self, hold: InstanceHold) -> None:
        """Afterwards the table holds exactly this row."""
        ...

    def delete_all(self) -> None: ...
