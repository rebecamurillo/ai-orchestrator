"""`RealEngine.schedule` runs each fire's job in a fresh `contextvars.Context` (story 4-3,
AD-25): a recovered scheduled workflow replays a `send` by step number, not by destination,
so a job that answered Run A and crashed would skip Run B's message on recovery. With no
workflow context inside the job, every `send` stands alone."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from dbos._context import DBOSContext, _dbos_context_var, get_local_dbos_context

from orchestrator.infrastructure.dbos import facade
from orchestrator.infrastructure.dbos.facade import RealEngine

AN_INSTANT = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


@pytest.fixture
def applied(monkeypatch: pytest.MonkeyPatch) -> list[list[dict[str, Any]]]:
    calls: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(facade.DBOS, "workflow", lambda **kwargs: lambda function: function)
    monkeypatch.setattr(facade.DBOS, "apply_schedules", calls.append)
    return calls


def test_the_job_sees_no_workflow_context(applied: list[list[dict[str, Any]]]) -> None:
    seen: list[object] = []
    RealEngine().schedule(
        "chat_poll", "*/30 * * * * *", lambda: seen.append(get_local_dbos_context())
    )
    (entry,) = applied[0]

    token = _dbos_context_var.set(DBOSContext())
    try:
        assert get_local_dbos_context() is not None
        entry["workflow_fn"](AN_INSTANT, AN_INSTANT)
        assert get_local_dbos_context() is not None
    finally:
        _dbos_context_var.reset(token)

    assert seen == [None]


def test_what_the_job_sets_in_its_context_stays_there(applied: list[list[dict[str, Any]]]) -> None:
    def job() -> None:
        _dbos_context_var.set(DBOSContext())

    RealEngine().schedule("terminal_poll", "*/30 * * * * *", job)
    (entry,) = applied[0]

    entry["workflow_fn"](AN_INSTANT, AN_INSTANT)

    assert get_local_dbos_context() is None
