"""4-2's `chat_thread` columns, their migration and the three notice lists, without a
database (story 4-2, AD-25). Statements are compiled for PostgreSQL, as in
`test_chat_repository_adapter.py`, whose session double and helpers this file reuses."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import CheckConstraint, DateTime, Text

from orchestrator.infrastructure.db import Base, ChatThreadRow
from orchestrator.infrastructure.db.repositories.chat import thread_values, to_thread
from tests.unit.conftest import REPO_ROOT
from tests.unit.test_chat_repository_adapter import (
    RecordingOp,
    RecordingSession,
    a_thread,
    sql,
    threads,
)

AT = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
THREADS = Base.metadata.tables["chat_thread"]
MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0030_chat_thread_close.py"
COLUMNS = {
    "closed_at": DateTime,
    "close_notice": Text,
    "close_notice_at": DateTime,
    "mention_notice": Text,
    "mention_notice_at": DateTime,
    "mention_cursor": Text,
}
CHECKS = {
    "close_notice": "close_notice IN ('due', 'sending', 'posted', 'failed')",
    "mention_notice": "mention_notice IN ('sending', 'posted', 'failed')",
    "close_notice_closed": "close_notice IS NULL OR state = 'closed'",
    "mention_notice_after_close": "mention_notice IS NULL OR close_notice = 'posted'",
}
PROJECT = UUID(int=9)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0030", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the table ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("column", "kind"), COLUMNS.items())
def test_each_new_column_is_nullable_and_typed(column: str, kind: type) -> None:
    assert THREADS.columns[column].nullable is True
    assert isinstance(THREADS.columns[column].type, kind)


def test_the_four_named_checks_hold_the_values_and_the_order() -> None:
    checks = {
        str(c.name): str(c.sqltext)
        for c in THREADS.constraints
        if isinstance(c, CheckConstraint) and str(c.name).startswith("ck_chat_thread_")
    }
    for name, text in CHECKS.items():
        assert checks[f"ck_chat_thread_{name}"] == text


# ── the migration ────────────────────────────────────────────────────────────


def test_the_migration_follows_the_chat_thread_revision() -> None:
    module = load_migration()

    assert (module.revision, module.down_revision) == ("0030_chat_thread_close", "0029_chat_thread")


def test_the_upgrade_adds_six_nullable_columns_and_four_checks_and_writes_no_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_migration()
    recorder = RecordingOp()
    monkeypatch.setattr(module, "op", recorder)

    module.upgrade()

    added = {args[1].name: args[1] for name, args, _ in recorder.calls if name == "add_column"}
    assert set(added) == set(COLUMNS)
    for column, kind in COLUMNS.items():
        assert added[column].nullable is True
        assert isinstance(added[column].type, kind)
    checks = {
        args[0]: args[2] for name, args, _ in recorder.calls if name == "create_check_constraint"
    }
    assert checks == {f"ck_chat_thread_{name}": text for name, text in CHECKS.items()}
    assert {name for name, _, _ in recorder.calls} <= {"add_column", "create_check_constraint", "f"}


def test_the_downgrade_drops_the_checks_then_the_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_migration()
    recorder = RecordingOp()
    monkeypatch.setattr(module, "op", recorder)

    module.downgrade()

    names = [name for name, _, _ in recorder.calls if name != "f"]
    assert names == ["drop_constraint"] * 4 + ["drop_column"] * 6
    dropped = {args[1] for name, args, _ in recorder.calls if name == "drop_column"}
    assert dropped == set(COLUMNS)


# ── the adapter ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("closed_at", AT),
        ("close_notice", "due"),
        ("close_notice_at", AT + timedelta(minutes=1)),
        ("mention_notice", "sending"),
        ("mention_notice_at", AT + timedelta(minutes=2)),
        ("mention_cursor", "c7"),
    ],
)
def test_each_new_column_round_trips_through_update_and_read(column: str, value: Any) -> None:
    thread = a_thread(state="closed", ref="root", **{column: value})
    session = RecordingSession()

    threads(session).update(thread)

    _, params = sql(session.executed[0])
    assert params[column] == value
    assert thread_values(thread)[column] == value
    assert to_thread(ChatThreadRow(**thread_values(thread))) == thread


def test_list_notices_due_reads_the_projects_due_threads_oldest_closed_first() -> None:
    thread = a_thread(state="closed", ref="r", closed_at=AT, close_notice="due")
    session = RecordingSession(rows=[ChatThreadRow(**thread_values(thread))])

    assert threads(session).list_notices_due(PROJECT) == [thread]
    text, params = sql(session.executed[0])
    assert "JOIN run ON run.id = chat_thread.run_id" in text
    assert "run.project_id = " in text
    assert "chat_thread.close_notice = " in text
    assert text.endswith("ORDER BY chat_thread.closed_at, chat_thread.id")
    assert set(params.values()) == {PROJECT, "due"}


def test_list_notices_in_reads_either_field_across_projects_oldest_first() -> None:
    session = RecordingSession()

    assert threads(session).list_notices_in("sending") == []
    text, params = sql(session.executed[0])
    assert "JOIN" not in text
    assert "chat_thread.close_notice = %(close_notice_1)s OR chat_thread.mention_notice = " in text
    assert text.endswith("ORDER BY chat_thread.created_at, chat_thread.id")
    assert set(params.values()) == {"sending"}


def test_list_watched_holds_every_filter_newest_closed_first_and_the_limit() -> None:
    session = RecordingSession()

    assert threads(session).list_watched(PROJECT, "slack", "C1", AT, 5) == []
    text, params = sql(session.executed[0])
    assert "JOIN run ON run.id = chat_thread.run_id" in text
    for fragment in (
        "run.project_id = ",
        "chat_thread.state = ",
        "chat_thread.close_notice = ",
        "chat_thread.mention_notice IS NULL",
        "chat_thread.provider = ",
        "chat_thread.channel_id = ",
        "chat_thread.closed_at >= ",
    ):
        assert fragment in text
    assert "ORDER BY chat_thread.closed_at DESC, chat_thread.id DESC" in text
    assert "LIMIT" in text
    assert set(params.values()) == {PROJECT, "closed", "posted", "slack", "C1", AT, 5}
