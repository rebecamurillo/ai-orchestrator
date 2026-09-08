"""The SQLAlchemy adapter for the `TrajectoryRepository` port (SPEC CAP-9, AD-19).

`add` is idempotent on `(run_id, frame)`: a second call for a pair already stored reads it
back and does nothing further, which is what lets `record_trajectory` be called on every
durable-step replay without a second row landing (AD-19, AD-6). The table's own unique index
(`models/trajectory.py`) is the same guarantee restated for a caller that reaches the
database directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.trajectory import (
    AttemptRecord,
    GateResults,
    HumanAction,
    ProtectedPathHit,
    ProtectedPathsResult,
    Trajectory,
)
from orchestrator.infrastructure.db.models.trajectory import TrajectoryRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def to_entity(row: TrajectoryRow) -> Trajectory:
    """A row as the domain entity every layer above works with."""
    gate = dict(row.gate_results)
    protected = dict(gate.get("protected_paths") or {})
    return Trajectory(
        id=row.id,
        run_id=row.run_id,
        project_id=row.project_id,
        repository_id=row.repository_id,
        story_id=row.story_id,
        epic_index=row.epic_index,
        frame=row.frame,
        harness=row.harness,
        model=row.model,
        attempts=tuple(AttemptRecord(**entry) for entry in row.attempts),
        gate_results=GateResults(
            build=gate["build"],
            verify=gate["verify"],
            commit_guard=gate["commit_guard"],
            protected_paths=ProtectedPathsResult(
                hits=tuple(ProtectedPathHit(**hit) for hit in protected.get("hits", [])),
                accepted=tuple(protected.get("accepted", [])),
            ),
        ),
        cost_usd=row.cost_usd,
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        wall_clock_seconds=row.wall_clock_seconds,
        story_file=row.story_file,
        start_sha=row.start_sha,
        end_sha=row.end_sha,
        human_actions=tuple(HumanAction(**entry) for entry in row.human_actions),
        recorded_at=row.recorded_at,
    )


def _row_values(trajectory: Trajectory) -> dict[str, Any]:
    """Every column of the `trajectory` table, keyed by name."""
    return {
        "id": trajectory.id,
        "run_id": trajectory.run_id,
        "project_id": trajectory.project_id,
        "repository_id": trajectory.repository_id,
        "story_id": trajectory.story_id,
        "epic_index": trajectory.epic_index,
        "frame": trajectory.frame,
        "harness": trajectory.harness,
        "model": trajectory.model,
        "attempts": [entry.model_dump(mode="json") for entry in trajectory.attempts],
        "gate_results": trajectory.gate_results.model_dump(mode="json"),
        "cost_usd": trajectory.cost_usd,
        "tokens_in": trajectory.tokens_in,
        "tokens_out": trajectory.tokens_out,
        "wall_clock_seconds": trajectory.wall_clock_seconds,
        "story_file": trajectory.story_file,
        "start_sha": trajectory.start_sha,
        "end_sha": trajectory.end_sha,
        "human_actions": [entry.model_dump(mode="json") for entry in trajectory.human_actions],
        "recorded_at": trajectory.recorded_at,
    }


class SQLAlchemyTrajectoryRepository:
    """Stored trajectories, over one open session. `add` and `list_for_project`, nothing else."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, trajectory: Trajectory) -> None:
        exists = self._session.scalars(
            select(TrajectoryRow).where(
                TrajectoryRow.run_id == trajectory.run_id,
                TrajectoryRow.frame == trajectory.frame,
            )
        ).first()
        if exists is not None:
            return
        self._session.add(TrajectoryRow(**_row_values(trajectory)))

    def list_for_project(self, project_id: UUID) -> list[Trajectory]:
        rows = self._session.scalars(
            select(TrajectoryRow)
            .where(TrajectoryRow.project_id == project_id)
            .order_by(TrajectoryRow.recorded_at.desc())
        ).all()
        return [to_entity(row) for row in rows]
