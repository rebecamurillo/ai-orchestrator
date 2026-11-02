"""`SQLAlchemyRunRepository.get_for_update`: the read two Run writers serialise on.

Driven over the session double of `test_run_repository_adapter.py`, so the claim is about the
statement the adapter builds: a `SELECT … FOR UPDATE` that refreshes a row the session
already holds, because a stale identity-map entry is what the lock exists to avoid."""

from __future__ import annotations

from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import RunRow
from orchestrator.infrastructure.db.repositories import runs as runs_module
from tests.unit.application.writer_fixtures import build_run
from tests.unit.test_run_repository_adapter import RecordingSession, runs_repository


def test_the_query_carries_for_update_and_the_run_id() -> None:
    run = build_run("running")
    session = RecordingSession(scalars_queue=[[RunRow(**runs_module.row_values(run))]])

    assert runs_repository(session).get_for_update(run.id) == run

    statement = session.statements[0]
    assert "FOR UPDATE" in str(statement)
    assert "run.id" in str(statement)
    assert statement.get_execution_options()["populate_existing"] is True


def test_a_missing_run_reads_none() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert runs_repository(session).get_for_update(new_id()) is None
