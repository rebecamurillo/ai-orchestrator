"""`step_run.role` in the model and the adapter (story 1, epic 2)."""

from __future__ import annotations

from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import StepRunRow
from orchestrator.infrastructure.db.repositories import step_runs as step_runs_module
from tests.unit.fakes.chat_world import a_row


def test_the_role_column_is_not_null_with_an_empty_default() -> None:
    column = StepRunRow.__table__.columns["role"]

    assert column.nullable is False
    assert column.server_default is not None
    assert str(column.server_default.arg) == "''"  # type: ignore[attr-defined]


def test_a_row_round_trips_its_role() -> None:
    step = a_row(new_id(), 1, "build", role="implement")

    row = StepRunRow(**step_runs_module.row_values(step))

    assert row.role == "implement"
    assert step_runs_module.to_entity(row) == step
    assert "role" in step_runs_module.MUTABLE_COLUMNS
