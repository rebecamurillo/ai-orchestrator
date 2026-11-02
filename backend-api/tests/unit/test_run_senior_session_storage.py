"""`run.senior_session`: the column, its mapping, and the revision that adds it (story 2-3)."""

from __future__ import annotations

import ast
from pathlib import Path

from orchestrator.infrastructure.db.models.run import RunRow
from orchestrator.infrastructure.db.repositories.runs import row_values, to_entity
from tests.unit.application.writer_fixtures import build_run

MIGRATION = Path(__file__).parents[2] / "alembic" / "versions" / "0026_run_senior_session.py"


def test_a_new_run_has_no_senior_session() -> None:
    assert build_run().senior_session is False


def test_the_flag_round_trips_through_the_row() -> None:
    run = build_run("needs_you", senior_session=True)

    assert row_values(run)["senior_session"] is True
    assert to_entity(RunRow(**row_values(run))).senior_session is True


def test_a_row_the_database_has_not_filled_yet_reads_false() -> None:
    stored = RunRow(**row_values(build_run("running")))
    stored.senior_session = None  # type: ignore[assignment]

    assert to_entity(stored).senior_session is False


def test_the_column_is_not_null_with_a_false_server_default() -> None:
    column = RunRow.__table__.c.senior_session

    assert column.nullable is False
    assert "false" in str(column.server_default.arg).lower()  # type: ignore[union-attr]


def test_migration_0026_adds_the_column_with_a_false_default() -> None:
    source = MIGRATION.read_text()
    tree = ast.parse(source)
    assigned = {
        node.target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value
    }

    assert assigned["revision"] == "0026_run_senior_session"
    assert assigned["down_revision"] == "0025_run_pause_requested"
    assert "senior_session" in source
    assert 'server_default=sa.text("false")' in source
    assert "nullable=False" in source
