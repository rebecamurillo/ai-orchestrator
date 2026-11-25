"""`SQLAlchemyRunRepository.list_for_initiative` refreshes rows the session already holds: a
cancel re-lists the initiative's Runs after `signal_run` committed their new status in a
session of its own (epic 7 story 3, 2026-11-25)."""

from __future__ import annotations

from orchestrator.domain.ids import new_id
from tests.unit.test_run_repository_adapter import RecordingSession, runs_repository


def test_the_listing_refreshes_rows_already_held() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert runs_repository(session).list_for_initiative(new_id()) == []

    statement = session.statements[0]
    assert "run.initiative_id" in str(statement)
    assert statement.get_execution_options()["populate_existing"] is True
