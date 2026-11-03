"""`step_run.consults` in the model, the adapter and migration 0024 (story 1-4, spine AD-22).

`JSONB NOT NULL` with server default `'{}'`, so every row stored before 0024 reads `{}` and
the column stays out of the nullable set."""

from __future__ import annotations

import ast

from sqlalchemy.dialects.postgresql import JSONB

from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import StepRunRow
from orchestrator.infrastructure.db.repositories import step_runs as step_runs_module
from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0024_step_run_consults.py"
ENTRY = {"blocked": {"state": "due", "question": "q", "snapshot": {}}}


def a_row(**over: object) -> StepRun:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "seq": 1,
        "path": "build",
        "label": "build",
        "kind": "agent",
        "gate": "liveness",
        "status": "queued",
    }
    fields.update(over)
    return StepRun(**fields)  # type: ignore[arg-type]


def test_the_consults_column_is_jsonb_not_null_with_an_empty_default() -> None:
    column = StepRunRow.__table__.columns["consults"]

    assert isinstance(column.type, JSONB)
    assert column.nullable is False
    assert column.server_default is not None
    assert str(column.server_default.arg) == "'{}'::jsonb"  # type: ignore[attr-defined]


def test_a_row_round_trips_its_consults() -> None:
    step = a_row(consults=ENTRY)

    row = StepRunRow(**step_runs_module.row_values(step))

    assert row.consults == ENTRY
    assert step_runs_module.to_entity(row) == step
    assert "consults" in step_runs_module.MUTABLE_COLUMNS


def test_a_row_built_without_consults_reads_empty() -> None:
    values = step_runs_module.row_values(a_row())
    del values["consults"]

    assert step_runs_module.to_entity(StepRunRow(**values)).consults == {}


def test_a_step_run_defaults_to_no_consults() -> None:
    assert a_row().consults == {}


def test_migration_0024_adds_the_column_with_the_empty_default() -> None:
    source = MIGRATION.read_text()
    tree = ast.parse(source)
    assigned = {
        node.target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value
    }

    assert assigned["revision"] == "0024_step_run_consults"
    assert assigned["down_revision"] == "0023_attempt_role"
    assert '"step_run"' in source
    assert "server_default=sa.text(\"'{}'::jsonb\")" in source
    assert "nullable=False" in source
    assert 'op.drop_column("step_run", "consults")' in source
