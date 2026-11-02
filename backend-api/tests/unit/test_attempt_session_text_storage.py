"""`attempt.message` and `attempt.reply` (story 2-5, AD-23), and the start-up read of the
session turns a crash left open.

Both columns are `TEXT NOT NULL` with server default `''`, so every attempt stored before
migration 0027 reads empty. `message` is written once, by `add`; `reply` is the finish half's.
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
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.runs import FakeAttemptRepository
from tests.unit.test_run_repository_adapter import RecordingSession

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0027_attempt_session_text.py"


def a_turn(**over: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 2,
        "role": "session",
        "status": "queued",
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


def test_an_attempt_carries_no_message_and_no_reply_by_default() -> None:
    attempt = a_turn()

    assert (attempt.message, attempt.reply) == ("", "")


def test_both_columns_are_text_not_null_with_an_empty_server_default() -> None:
    for name in ("message", "reply"):
        column = AttemptRow.__table__.columns[name]
        assert isinstance(column.type, Text), name
        assert column.nullable is False, name
        assert column.server_default is not None, name
        assert column.server_default.arg == "", name  # type: ignore[attr-defined]


def test_a_turn_round_trips_through_its_row() -> None:
    attempt = a_turn(message="Why?", reply="Because.")

    row = AttemptRow(**attempts_module.row_values(attempt))

    assert (row.message, row.reply) == ("Why?", "Because.")
    assert attempts_module.to_entity(row) == attempt


def test_a_row_the_database_has_not_filled_yet_reads_empty() -> None:
    row = AttemptRow(
        id=new_id(), run_id=new_id(), step_run_id=new_id(), n=1, status="done", engine_ref={}
    )
    row.cost_provisional = False

    entity = attempts_module.to_entity(row)

    assert (entity.message, entity.reply) == ("", "")


def test_the_reply_is_the_finish_halfs_and_the_message_neithers() -> None:
    assert "reply" in attempts_module.FINISHED_COLUMNS
    assert "reply" not in attempts_module.STARTED_COLUMNS
    assert "message" not in attempts_module.FINISHED_COLUMNS
    assert "message" not in attempts_module.STARTED_COLUMNS
    assert {"message", "reply"} <= set(attempts_module.MUTABLE_COLUMNS)


def test_the_open_session_turns_are_read_in_sql() -> None:
    turn = a_turn()
    session = RecordingSession(scalars_queue=[[AttemptRow(**attempts_module.row_values(turn))]])

    found = SQLAlchemyAttemptRepository(session).list_open_sessions()  # type: ignore[arg-type]

    assert found == [turn]
    rendered = str(session.statements[0])
    assert "attempt.role = :role_1" in rendered
    assert "attempt.status =" not in rendered
    assert "attempt.ended_at IS NULL" in rendered
    assert "ORDER BY attempt.started_at" in rendered


def test_the_fake_reads_the_same_turns() -> None:
    queued = a_turn(started_at=EPOCH)
    running = a_turn(status="running")
    repository = FakeAttemptRepository(
        [
            queued,
            running,
            a_turn(role="agent"),
            a_turn(ended_at=EPOCH, status="queued", n=3),
        ]
    )

    assert repository.list_open_sessions() == [queued, running]


def test_migration_0027_adds_both_columns_with_an_empty_default() -> None:
    source = MIGRATION.read_text()
    tree = ast.parse(source)
    assigned = {
        node.target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value
    }

    assert assigned["revision"] == "0027_attempt_session_text"
    assert assigned["down_revision"] == "0026_run_senior_session"
    for name in ("message", "reply"):
        assert f'"{name}"' in source
    assert 'server_default=""' in source
    assert "nullable=False" in source
