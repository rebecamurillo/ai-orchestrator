"""`attempt.role` in the SQLAlchemy adapter and the model (story 1-7, spine AD-21, 2026-11-01).

The column is `NOT NULL` with server default `agent`, so every row stored before migration
0023 reads `agent`. `get_latest_agent` and `latest_for_run` filter on it in SQL.
"""

from __future__ import annotations

import ast

from sqlalchemy import Text

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import AttemptRow
from orchestrator.infrastructure.db.repositories import attempts as attempts_module
from orchestrator.infrastructure.db.repositories.attempts import SQLAlchemyAttemptRepository
from tests.unit.conftest import REPO_ROOT
from tests.unit.test_run_repository_adapter import RecordingSession

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0023_attempt_role.py"


def a_consult() -> Attempt:
    return Attempt(
        id=new_id(), run_id=new_id(), step_run_id=new_id(), n=2, role="consult", status="done"
    )


def test_the_role_column_is_text_not_null_with_server_default_agent() -> None:
    column = AttemptRow.__table__.columns["role"]

    assert isinstance(column.type, Text)
    assert column.nullable is False
    assert column.server_default is not None
    assert column.server_default.arg == "agent"  # type: ignore[attr-defined]


def test_a_consult_attempt_round_trips_through_its_row() -> None:
    attempt = a_consult()

    row = AttemptRow(**attempts_module.row_values(attempt))

    assert row.role == "consult"
    assert attempts_module.to_entity(row) == attempt


def test_a_row_built_without_a_role_reads_agent() -> None:
    row = AttemptRow(
        id=new_id(), run_id=new_id(), step_run_id=new_id(), n=1, status="done", engine_ref={}
    )
    row.cost_provisional = False

    assert attempts_module.to_entity(row).role == "agent"


def test_the_role_is_written_by_add_and_update_but_neither_half() -> None:
    assert "role" in attempts_module.MUTABLE_COLUMNS
    assert "role" not in attempts_module.STARTED_COLUMNS
    assert "role" not in attempts_module.FINISHED_COLUMNS


def test_get_latest_agent_filters_on_the_row_and_the_role() -> None:
    attempt = a_consult().model_copy(update={"role": "agent"})
    session = RecordingSession(scalars_queue=[[AttemptRow(**attempts_module.row_values(attempt))]])

    latest = SQLAlchemyAttemptRepository(session).get_latest_agent(attempt.step_run_id)  # type: ignore[arg-type]

    assert latest == attempt
    rendered = str(session.statements[0])
    assert "attempt.step_run_id" in rendered
    assert "attempt.role" in rendered
    assert "ORDER BY attempt.n DESC" in rendered


def test_get_latest_agent_is_none_when_the_row_has_no_agent_attempt() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert SQLAlchemyAttemptRepository(session).get_latest_agent(new_id()) is None  # type: ignore[arg-type]


def test_latest_for_run_filters_on_the_role() -> None:
    session = RecordingSession(scalars_queue=[[]])

    SQLAlchemyAttemptRepository(session).latest_for_run(new_id())  # type: ignore[arg-type]

    rendered = str(session.statements[0])
    assert "attempt.run_id" in rendered
    assert "attempt.role" in rendered


def test_migration_0023_adds_the_column_with_the_agent_default() -> None:
    source = MIGRATION.read_text()
    tree = ast.parse(source)
    assigned = {
        node.target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value
    }

    assert assigned["revision"] == "0023_attempt_role"
    assert assigned["down_revision"] == "0022_run_park_seq"
    assert 'sa.Column("role", sa.Text(), server_default="agent", nullable=False)' in source
