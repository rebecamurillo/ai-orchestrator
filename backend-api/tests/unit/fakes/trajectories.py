"""In-memory `TrajectoryRepository` — the one fake for that port (AD-18). Reuse it.

`add` mirrors the adapter's own idempotency: a second call for a `(run_id, frame)` pair
already stored does nothing, which is what a test proves a replay is safe by calling twice.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.domain.entities.trajectory import Trajectory


class FakeTrajectoryRepository:
    """Stored trajectories in a list. `add` and `list_for_project`, nothing else."""

    def __init__(self, trajectories: list[Trajectory] | None = None) -> None:
        self.trajectories: list[Trajectory] = list(trajectories or [])
        self.calls: list[tuple[str, object]] = []

    def add(self, trajectory: Trajectory) -> None:
        self.calls.append(("add", trajectory.id))
        if any(
            stored.run_id == trajectory.run_id and stored.frame == trajectory.frame
            for stored in self.trajectories
        ):
            return
        self.trajectories.append(trajectory)

    def list_for_project(self, project_id: UUID) -> list[Trajectory]:
        self.calls.append(("list_for_project", project_id))
        return sorted(
            (t for t in self.trajectories if t.project_id == project_id),
            key=lambda t: t.recorded_at,
            reverse=True,
        )
