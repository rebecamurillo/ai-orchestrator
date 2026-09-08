"""The `trajectory` table and its adapter, without a database (AD-18, SPEC CAP-9).

Two halves, the same two `test_run_repository_adapter.py` uses: the table is read off
`Base.metadata` — the same object Alembic compares against, so a column the model forgot is
a column the migration would not have created either — and the adapter is driven over a
session double that records calls instead of executing SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.domain.entities.trajectory import (
    AttemptRecord,
    GateResults,
    HumanAction,
    ProtectedPathHit,
    ProtectedPathsResult,
    Trajectory,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.trajectories import TrajectoryRepository
from orchestrator.infrastructure.db import Base, SQLAlchemyTrajectoryRepository
from orchestrator.infrastructure.db.models.trajectory import TrajectoryRow
from orchestrator.infrastructure.db.repositories import trajectories as trajectories_module

AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)

TRAJECTORY_TABLE = Base.metadata.tables["trajectory"]


def a_trajectory(**overrides: object) -> Trajectory:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "epic_index": 0,
        "frame": "stories[0]",
        "gate_results": GateResults(build="liveness", verify="done", commit_guard="done"),
        "recorded_at": AT,
    }
    fields.update(overrides)
    return Trajectory(**fields)  # type: ignore[arg-type]


def a_full_trajectory() -> Trajectory:
    return a_trajectory(
        story_id="5-9",
        harness="claude",
        model="sonnet",
        attempts=(
            AttemptRecord(n=1, route="error", exit_code=1),
            AttemptRecord(
                n=2,
                started_at=AT,
                ended_at=AT,
                exit_code=0,
                session_id="s-1",
                cost_usd=Decimal("0.012345"),
                tokens_in=10,
                tokens_out=20,
                route="done",
            ),
        ),
        gate_results=GateResults(
            build="liveness",
            verify="done",
            commit_guard="no changes",
            protected_paths=ProtectedPathsResult(
                hits=(ProtectedPathHit(path="tests/unit/a.py", kind="modified"),),
                accepted=("docs/spec.md",),
            ),
        ),
        cost_usd=Decimal("0.012345"),
        tokens_in=10,
        tokens_out=20,
        wall_clock_seconds=42.5,
        story_file="status: done\n",
        start_sha="aaa",
        end_sha="bbb",
        human_actions=(HumanAction(event="blocked", at=AT), HumanAction(event="answer", at=AT)),
    )


# ── the session double ───────────────────────────────────────────────────────


class RecordingResult:
    """What `Session.scalars` returns: one canned answer, whatever shape it holds."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect."""

    def __init__(self, scalars_queue: list[list[Any]] | None = None) -> None:
        self.added: list[Any] = []
        self.statements: list[Any] = []
        self._scalars_queue = list(scalars_queue or [])

    def add(self, row: Any) -> None:
        self.added.append(row)

    def scalars(self, statement: Any) -> RecordingResult:
        self.statements.append(statement)
        return RecordingResult(self._scalars_queue.pop(0))


def repository(session: RecordingSession) -> SQLAlchemyTrajectoryRepository:
    return SQLAlchemyTrajectoryRepository(session)  # type: ignore[arg-type]


# ── the table ─────────────────────────────────────────────────────────────────


def test_the_model_declares_the_table_the_migration_creates() -> None:
    assert TRAJECTORY_TABLE.name == "trajectory"


def test_the_table_carries_exactly_the_columns_the_entity_needs() -> None:
    assert {column.name for column in TRAJECTORY_TABLE.columns} == {
        "id",
        "run_id",
        "project_id",
        "repository_id",
        "story_id",
        "epic_index",
        "frame",
        "harness",
        "model",
        "attempts",
        "gate_results",
        "cost_usd",
        "tokens_in",
        "tokens_out",
        "wall_clock_seconds",
        "story_file",
        "start_sha",
        "end_sha",
        "human_actions",
        "recorded_at",
    }


def test_the_table_is_unique_on_run_id_and_frame() -> None:
    names = {constraint.name for constraint in TRAJECTORY_TABLE.constraints}
    assert "uq_trajectory_run_id_frame" in names


def test_the_table_is_keyed_by_its_uuid_v7_id() -> None:
    (pk,) = TRAJECTORY_TABLE.primary_key.columns
    assert pk.name == "id"


# ── the round trip ───────────────────────────────────────────────────────────


def test_a_minimal_trajectory_round_trips_through_its_row() -> None:
    trajectory = a_trajectory()

    row = TrajectoryRow(**trajectories_module._row_values(trajectory))

    assert trajectories_module.to_entity(row) == trajectory


def test_a_fully_filled_trajectory_round_trips_through_its_row() -> None:
    trajectory = a_full_trajectory()

    row = TrajectoryRow(**trajectories_module._row_values(trajectory))

    assert trajectories_module.to_entity(row) == trajectory


def test_the_attempts_column_holds_one_object_per_attempt_in_order() -> None:
    trajectory = a_full_trajectory()

    values = trajectories_module._row_values(trajectory)

    assert [entry["n"] for entry in values["attempts"]] == [1, 2]


# ── the adapter ───────────────────────────────────────────────────────────────


def test_the_adapter_satisfies_the_port() -> None:
    trajectories: TrajectoryRepository = repository(RecordingSession())

    assert isinstance(trajectories, TrajectoryRepository)


def test_the_adapter_has_no_way_to_change_or_delete_a_trajectory() -> None:
    """AC5: the repository port exposes no update or delete method."""
    public = {name for name in vars(SQLAlchemyTrajectoryRepository) if not name.startswith("_")}

    assert public == {"add", "list_for_project"}


def test_add_inserts_the_row_when_the_pair_is_not_yet_stored() -> None:
    trajectory = a_trajectory()
    session = RecordingSession(scalars_queue=[[]])

    repository(session).add(trajectory)

    (row,) = session.added
    assert row.run_id == trajectory.run_id
    assert row.frame == trajectory.frame


def test_add_does_nothing_for_a_pair_already_stored() -> None:
    """AD-19, AD-6: a durable-step replay of `record_trajectory` records nothing twice."""
    trajectory = a_trajectory()
    existing = TrajectoryRow(**trajectories_module._row_values(trajectory))
    session = RecordingSession(scalars_queue=[[existing]])

    repository(session).add(trajectory)

    assert session.added == []


def test_list_for_project_reads_the_rows_newest_first() -> None:
    project_id = new_id()
    older = a_trajectory(project_id=project_id, frame="stories[0]", recorded_at=AT)
    newer = a_trajectory(
        project_id=project_id,
        frame="stories[1]",
        recorded_at=datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
    )
    rows = [TrajectoryRow(**trajectories_module._row_values(t)) for t in (newer, older)]
    session = RecordingSession(scalars_queue=[rows])

    result = repository(session).list_for_project(project_id)

    assert [t.frame for t in result] == ["stories[1]", "stories[0]"]


def test_list_for_project_scopes_to_the_project() -> None:
    project_id: UUID = new_id()
    session = RecordingSession(scalars_queue=[[]])

    repository(session).list_for_project(project_id)

    rendered = str(session.statements[0])
    assert "trajectory.project_id" in rendered
