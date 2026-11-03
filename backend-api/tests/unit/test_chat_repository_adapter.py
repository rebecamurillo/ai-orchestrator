"""The `chat_thread` and `chat_notice` tables, their migration and their adapters, without a
database (story 3-3, AD-25).

Tables are read off `Base.metadata`, the object Alembic compares against. The migration runs
against a recording `op`. The adapters run over a session double that records statements;
each statement is compiled for PostgreSQL, so the SQL a database would receive is pinned:
`add` is `ON CONFLICT DO NOTHING` with no conflict target, the locks are `FOR UPDATE`, and
the notice selection is an anti-join.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import CheckConstraint, DateTime, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects import postgresql

from orchestrator.domain.entities.chat_thread import ChatNotice, ChatThread
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatUser
from orchestrator.domain.ports.repositories import (
    ChatNoticeRepository,
    ChatThreadRepository,
    ProjectChannelRepository,
)
from orchestrator.infrastructure.db import (
    Base,
    ChatNoticeRow,
    ChatThreadRow,
    ProjectChannelRow,
    SQLAlchemyChatNoticeRepository,
    SQLAlchemyChatThreadRepository,
    SQLAlchemyProjectChannelRepository,
)
from orchestrator.infrastructure.db.models.run import GateRecordRow
from orchestrator.infrastructure.db.repositories.chat import thread_values, to_thread
from tests.unit.conftest import REPO_ROOT

AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
THREADS = Base.metadata.tables["chat_thread"]
NOTICES = Base.metadata.tables["chat_notice"]
MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0029_chat_thread.py"
#: Revised under hard rule 1(b), story 4-2, 2026-11-03: 4-2 adds these six nullable columns
#: and four CHECKs in migration 0030; `test_chat_repository_close.py` pins them.
CLOSE_COLUMNS = {
    "closed_at",
    "close_notice",
    "close_notice_at",
    "mention_notice",
    "mention_notice_at",
    "mention_cursor",
}
CLOSE_CHECKS = {
    "close_notice IN ('due', 'sending', 'posted', 'failed')",
    "mention_notice IN ('sending', 'posted', 'failed')",
    "close_notice IS NULL OR state = 'closed'",
    "mention_notice IS NULL OR close_notice = 'posted'",
}


def a_thread(**overrides: Any) -> ChatThread:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": new_id(),
        "park_seq": 3,
        "park_kind": "blocked",
        "provider": "mattermost",
        "channel_id": "c1",
        "ref": None,
        "cursor": None,
        "state": "posting",
        "error": None,
        "last_reminded_at": None,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return ChatThread(**fields)


class RecordingSession:
    """Records every statement, answers `rowcount` and `scalars` from what a test set."""

    def __init__(self, rowcount: int = 1, rows: list[Any] | None = None) -> None:
        self.executed: list[Any] = []
        self.rowcount = rowcount
        self.rows = rows or []
        self.got: list[tuple[type, Any]] = []
        self.flushed = 0

    def execute(self, statement: Any) -> SimpleNamespace:
        self.executed.append(statement)
        return SimpleNamespace(rowcount=self.rowcount)

    def scalars(self, statement: Any) -> SimpleNamespace:
        self.executed.append(statement)
        rows = self.rows
        return SimpleNamespace(all=lambda: list(rows), first=lambda: rows[0] if rows else None)

    def get(self, entity: type, key: Any) -> Any:
        self.got.append((entity, key))
        return next((row for row in self.rows if isinstance(row, entity)), None)

    def flush(self) -> None:
        self.flushed += 1


def sql(statement: Any) -> tuple[str, dict[str, Any]]:
    compiled = statement.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).split()), dict(compiled.params)


def threads(session: RecordingSession) -> SQLAlchemyChatThreadRepository:
    return SQLAlchemyChatThreadRepository(session)  # type: ignore[arg-type]


def notices(session: RecordingSession) -> SQLAlchemyChatNoticeRepository:
    return SQLAlchemyChatNoticeRepository(session)  # type: ignore[arg-type]


# ── the tables ───────────────────────────────────────────────────────────────


def test_the_thread_table_carries_4_1s_and_4_2s_columns_and_only_ten_are_nullable() -> None:
    assert set(THREADS.columns.keys()) == CLOSE_COLUMNS | {
        "id",
        "run_id",
        "park_seq",
        "park_kind",
        "provider",
        "channel_id",
        "ref",
        "cursor",
        "state",
        "error",
        "last_reminded_at",
        "created_at",
        "updated_at",
    }
    nullable = {name for name, column in THREADS.columns.items() if column.nullable}
    assert nullable == CLOSE_COLUMNS | {"ref", "cursor", "error", "last_reminded_at"}


@pytest.mark.parametrize(
    ("column", "kind"),
    [
        ("id", Uuid),
        ("run_id", Uuid),
        ("park_seq", Integer),
        ("park_kind", Text),
        ("provider", Text),
        ("channel_id", Text),
        ("ref", Text),
        ("cursor", Text),
        ("state", Text),
        ("error", Text),
        ("last_reminded_at", DateTime),
        ("created_at", DateTime),
        ("updated_at", DateTime),
    ],
)
def test_every_thread_column_has_its_type(column: str, kind: type) -> None:
    assert isinstance(THREADS.columns[column].type, kind)


def test_a_thread_is_keyed_by_id_and_goes_with_its_run() -> None:
    assert [column.name for column in THREADS.primary_key.columns] == ["id"]
    (foreign_key,) = THREADS.columns["run_id"].foreign_keys
    assert (foreign_key.target_fullname, foreign_key.ondelete) == ("run.id", "CASCADE")


def test_a_thread_is_unique_per_stop_and_per_ref() -> None:
    uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in THREADS.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert uniques == {("run_id", "park_seq"), ("ref",)}


def test_the_thread_state_and_provider_are_checked() -> None:
    checks = {str(c.sqltext) for c in THREADS.constraints if isinstance(c, CheckConstraint)}
    assert checks == CLOSE_CHECKS | {
        "state IN ('posting', 'open', 'closed', 'failed')",
        "provider IN ('mattermost', 'slack')",
    }


def test_the_notice_table_is_a_claim_row_on_its_gate_record() -> None:
    assert set(NOTICES.columns.keys()) == {"gate_record_id", "run_id", "created_at", "error"}
    nullable = {name for name, column in NOTICES.columns.items() if column.nullable}
    assert nullable == {"error"}
    assert [column.name for column in NOTICES.primary_key.columns] == ["gate_record_id"]
    (record_key,) = NOTICES.columns["gate_record_id"].foreign_keys
    (run_key,) = NOTICES.columns["run_id"].foreign_keys
    assert (record_key.target_fullname, record_key.ondelete) == ("gate_record.id", "CASCADE")
    assert (run_key.target_fullname, run_key.ondelete) == ("run.id", "CASCADE")


# ── the migration ────────────────────────────────────────────────────────────


class RecordingOp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            return args[0] if name == "f" else None

        return record


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0029", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_revises_the_head_before_it() -> None:
    module = load_migration()

    assert module.revision == "0029_chat_thread"
    assert module.down_revision == "0028_project_channel"


def test_the_migration_creates_both_tables_as_the_models_declare_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_migration()
    recorder = RecordingOp()
    monkeypatch.setattr(module, "op", recorder)

    module.upgrade()

    created = {args[0]: args for name, args, _ in recorder.calls if name == "create_table"}
    assert set(created) == {"chat_thread", "chat_notice"}
    for table, model in (("chat_thread", THREADS), ("chat_notice", NOTICES)):
        columns = {arg.name: arg for arg in created[table][1:] if hasattr(arg, "nullable")}
        later = CLOSE_COLUMNS if table == "chat_thread" else set()
        assert set(columns) == set(model.columns.keys()) - later
        for name, column in columns.items():
            assert column.nullable is model.columns[name].nullable, (table, name)
        assert repr(created[table]).count("CASCADE") == (1 if table == "chat_thread" else 2)
    thread_checks = {
        str(arg.sqltext) for arg in created["chat_thread"] if isinstance(arg, CheckConstraint)
    }
    assert thread_checks == {
        "state IN ('posting', 'open', 'closed', 'failed')",
        "provider IN ('mattermost', 'slack')",
    }
    uniques = {
        tuple(arg._pending_colargs)
        for arg in created["chat_thread"]
        if isinstance(arg, UniqueConstraint)
    }
    assert uniques == {("run_id", "park_seq"), ("ref",)}


def test_the_downgrade_drops_both_tables_notices_first(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_migration()
    recorder = RecordingOp()
    monkeypatch.setattr(module, "op", recorder)

    module.downgrade()

    assert [(name, args) for name, args, _ in recorder.calls] == [
        ("drop_table", ("chat_notice",)),
        ("drop_table", ("chat_thread",)),
    ]


# ── the thread adapter ───────────────────────────────────────────────────────


def test_the_adapters_satisfy_their_ports() -> None:
    assert isinstance(threads(RecordingSession()), ChatThreadRepository)
    assert isinstance(notices(RecordingSession()), ChatNoticeRepository)


def test_add_is_one_insert_that_does_nothing_on_any_conflict() -> None:
    session = RecordingSession(rowcount=1)
    thread = a_thread()

    assert threads(session).add(thread) is True

    (statement,) = session.executed
    text, params = sql(statement)
    assert text.startswith("INSERT INTO chat_thread ")
    assert text.endswith("ON CONFLICT DO NOTHING")
    assert params == thread_values(thread)


def test_add_answers_false_when_the_insert_wrote_no_row() -> None:
    assert threads(RecordingSession(rowcount=0)).add(a_thread()) is False


def test_a_row_reads_back_as_the_thread_it_was_built_from() -> None:
    thread = a_thread(ref="root", cursor="c", state="open", last_reminded_at=AT)

    assert to_thread(ChatThreadRow(**thread_values(thread))) == thread


def test_get_reads_by_id_and_answers_none_when_absent() -> None:
    thread = a_thread()
    session = RecordingSession(rows=[ChatThreadRow(**thread_values(thread))])

    assert threads(session).get(thread.id) == thread
    assert session.got == [(ChatThreadRow, thread.id)]
    assert threads(RecordingSession()).get(thread.id) is None


def test_get_for_update_locks_the_row() -> None:
    thread = a_thread()
    session = RecordingSession(rows=[ChatThreadRow(**thread_values(thread))])

    assert threads(session).get_for_update(thread.id) == thread
    text, _ = sql(session.executed[0])
    assert text.endswith("FOR UPDATE")
    assert "WHERE chat_thread.id = " in text
    assert threads(RecordingSession()).get_for_update(thread.id) is None


def test_get_by_stop_reads_the_run_and_park_seq() -> None:
    thread = a_thread()
    session = RecordingSession(rows=[ChatThreadRow(**thread_values(thread))])

    assert threads(session).get_by_stop(thread.run_id, 3) == thread
    text, params = sql(session.executed[0])
    assert "chat_thread.run_id = " in text
    assert "chat_thread.park_seq = " in text
    assert set(params.values()) == {thread.run_id, 3}
    assert threads(RecordingSession()).get_by_stop(thread.run_id, 3) is None


def test_list_open_for_project_joins_the_run_and_reads_oldest_first() -> None:
    thread = a_thread(state="open", ref="r")
    session = RecordingSession(rows=[ChatThreadRow(**thread_values(thread))])
    project_id = UUID(int=9)

    assert threads(session).list_open_for_project(project_id) == [thread]
    text, params = sql(session.executed[0])
    assert "JOIN run ON run.id = chat_thread.run_id" in text
    assert "run.project_id = " in text
    assert "chat_thread.state = " in text
    assert text.endswith("ORDER BY chat_thread.created_at, chat_thread.id")
    assert set(params.values()) == {project_id, "open"}


def test_list_by_state_reads_oldest_first() -> None:
    session = RecordingSession()

    assert threads(session).list_by_state("posting") == []
    text, params = sql(session.executed[0])
    assert text.endswith("ORDER BY chat_thread.created_at, chat_thread.id")
    assert list(params.values()) == ["posting"]


def test_update_writes_every_column_but_the_key_by_id() -> None:
    session = RecordingSession()
    thread = a_thread(state="open", ref="root")

    threads(session).update(thread)

    (statement,) = session.executed
    text, params = sql(statement)
    assert text.startswith("UPDATE chat_thread SET ")
    assert "WHERE chat_thread.id = " in text
    assert params["ref"] == "root"
    assert params["state"] == "open"
    assert params["id_1"] == thread.id


# ── the notice adapter ───────────────────────────────────────────────────────


def test_a_notice_claim_is_one_insert_that_does_nothing_on_conflict() -> None:
    session = RecordingSession(rowcount=1)
    notice = ChatNotice(gate_record_id=new_id(), run_id=new_id(), created_at=AT)

    assert notices(session).add(notice) is True
    assert notices(RecordingSession(rowcount=0)).add(notice) is False

    text, params = sql(session.executed[0])
    assert text.startswith("INSERT INTO chat_notice ")
    assert text.endswith("ON CONFLICT DO NOTHING")
    assert params == {
        "gate_record_id": notice.gate_record_id,
        "run_id": notice.run_id,
        "created_at": AT,
        "error": None,
    }


def test_unposted_accepts_is_an_anti_join_on_the_projects_runs() -> None:
    record = GateRecordRow(
        id=new_id(),
        run_id=new_id(),
        at=AT,
        path="p",
        event="senior_accept",
        actor="senior",
        text="t",
        attempt_n=None,
        payload={"files": ["a"]},
    )
    session = RecordingSession(rows=[record])
    project_id = UUID(int=9)

    found = notices(session).unposted_accepts(project_id, AT)

    assert [r.id for r in found] == [record.id]
    text, params = sql(session.executed[0])
    assert "JOIN run ON run.id = gate_record.run_id" in text
    assert "run.project_id = " in text
    assert "gate_record.event = " in text
    assert "gate_record.at >= " in text
    assert (
        "NOT (EXISTS (SELECT * FROM chat_notice WHERE chat_notice.gate_record_id = gate_record.id))"
    ) in text
    assert text.endswith("ORDER BY gate_record.at, gate_record.id")
    assert set(params.values()) == {project_id, "senior_accept", AT}
    assert "status" not in text


def test_set_error_updates_the_claim_row() -> None:
    session = RecordingSession()
    record_id = new_id()

    notices(session).set_error(record_id, "403 ***")

    text, params = sql(session.executed[0])
    assert text.startswith("UPDATE chat_notice SET error=")
    assert "WHERE chat_notice.gate_record_id = " in text
    assert set(params.values()) == {"403 ***", record_id}


# ── project channels ─────────────────────────────────────────────────────────


def test_list_all_reads_every_channel_ordered_by_project() -> None:
    row = ProjectChannelRow(
        project_id=UUID(int=1),
        provider="slack",
        base_url="https://slack.com/api",
        channel_id="C1",
        token_enc="enc",
        allowed_users=[{"id": "U1", "handle": "ana"}],
        metadata_only=False,
        created_at=AT,
        updated_at=AT,
    )
    session = RecordingSession(rows=[row])
    repository = SQLAlchemyProjectChannelRepository(session)  # type: ignore[arg-type]

    assert isinstance(repository, ProjectChannelRepository)
    assert repository.list_all() == [
        ProjectChannel(
            project_id=UUID(int=1),
            provider="slack",
            base_url="https://slack.com/api",
            channel_id="C1",
            token_enc="enc",
            allowed_users=(ChatUser("U1", "ana"),),
            metadata_only=False,
            created_at=AT,
            updated_at=AT,
        )
    ]
    text, _ = sql(session.executed[0])
    assert text.endswith("ORDER BY project_channel.project_id")


def test_the_notice_row_model_is_exported() -> None:
    assert ChatNoticeRow.__tablename__ == "chat_notice"
