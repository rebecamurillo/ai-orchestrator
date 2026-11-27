"""`mark_logs_removed` and the `log_removed_at` mapping (epic 1 story 3, AD-40)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects import postgresql

from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import AttemptRow
from orchestrator.infrastructure.db.repositories.attempts import (
    FINISHED_COLUMNS,
    MUTABLE_COLUMNS,
    STARTED_COLUMNS,
    SQLAlchemyAttemptRepository,
    row_values,
    to_entity,
)
from tests.unit.fakes.runs import FakeAttemptRepository
from tests.unit.test_run_entities import an_attempt
from tests.unit.test_run_repository_adapter import RecordingSession

EARLIER = datetime(2026, 11, 1, tzinfo=UTC)
AT = datetime(2026, 11, 23, tzinfo=UTC)


class ExecutingSession(RecordingSession):
    def execute(self, statement: Any) -> None:
        self.statements.append(statement)


def test_the_sql_adapter_issues_one_update_scoped_to_unstamped_attempts_of_the_run() -> None:
    session = ExecutingSession()
    run_id = new_id()

    SQLAlchemyAttemptRepository(session).mark_logs_removed(run_id, AT)  # type: ignore[arg-type]

    assert len(session.statements) == 1
    sql = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert sql.startswith("UPDATE attempt SET log_removed_at=")
    assert "WHERE attempt.run_id = " in sql
    assert "attempt.log_removed_at IS NULL" in sql


def test_log_removed_at_round_trips_through_the_row() -> None:
    attempt = an_attempt(log_removed_at=AT)

    values = row_values(attempt)
    row = AttemptRow(**values)

    assert values["log_removed_at"] == AT
    assert to_entity(row).log_removed_at == AT


def test_log_removed_at_is_written_by_neither_half() -> None:
    assert "log_removed_at" in MUTABLE_COLUMNS
    assert "log_removed_at" not in STARTED_COLUMNS
    assert "log_removed_at" not in FINISHED_COLUMNS


def test_the_fake_stamps_only_unstamped_attempts_of_that_run() -> None:
    run_id = new_id()
    fresh = an_attempt(run_id=run_id)
    stamped = an_attempt(run_id=run_id, log_removed_at=EARLIER)
    other = an_attempt()
    fake = FakeAttemptRepository([fresh, stamped, other])

    fake.mark_logs_removed(run_id, AT)

    assert fake.attempts[fresh.id].log_removed_at == AT
    assert fake.attempts[stamped.id].log_removed_at == EARLIER
    assert fake.attempts[other.id].log_removed_at is None
    assert ("mark_logs_removed", run_id) in fake.calls
