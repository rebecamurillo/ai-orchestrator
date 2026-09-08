"""The `TrajectoryRepository` port: stored trajectories, without a database (SPEC CAP-9).

`add` is idempotent on `(run_id, frame)` — a second call for a pair already stored does
nothing — which is what lets `record_trajectory` be called on every durable-step replay
without a second row landing (AD-19, AD-6). Nothing here updates or deletes one: the two
methods below are all there is, on purpose (AD-19's "nothing updates or deletes it").
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.trajectory import Trajectory


@runtime_checkable
class TrajectoryRepository(Protocol):
    """Stored trajectories. `add` and `list_for_project`, and no third method."""

    def add(self, trajectory: Trajectory) -> None:
        """Store a Trajectory; a second `add` for the same `(run_id, frame)` does nothing."""
        ...

    def list_for_project(self, project_id: UUID) -> list[Trajectory]:
        """Every stored Trajectory of this Project, newest first."""
        ...
