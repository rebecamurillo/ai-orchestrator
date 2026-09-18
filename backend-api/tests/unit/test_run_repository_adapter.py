"""The four Run tables and their four adapters, without a database (AD-18).

Two halves, the same two as `test_template_repository_adapter.py`. The tables are read off
`Base.metadata` — the same object Alembic compares against, so a column the model forgot is
a column the migration would not have created either. The adapters are driven over a session
double that records calls instead of executing SQL, which is what lets the whole shape of a
`Run` round trip — `Decimal` money, `jsonb` lists, the pinned versions — in the unit suite,
where `tests/e2e/test_run_persistence.py` proves the same thing against Postgres.

The unique indexes are asserted here as declarations and in the e2e module as `pg_index`
rows, because a model that declares one and a migration that never created it look identical
from this side.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Boolean, DateTime, Integer, Numeric, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.values import Worktree
from orchestrator.infrastructure.db import (
    Base,
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
)
from orchestrator.infrastructure.db.models.run import (
    AttemptRow,
    GateRecordRow,
    RunRow,
    StepRunRow,
)
from orchestrator.infrastructure.db.repositories import attempts as attempts_module
from orchestrator.infrastructure.db.repositories import gate_records as gate_records_module
from orchestrator.infrastructure.db.repositories import runs as runs_module
from orchestrator.infrastructure.db.repositories import step_runs as step_runs_module

AT = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

RUN_TABLE = Base.metadata.tables["run"]
STEP_RUN_TABLE = Base.metadata.tables["step_run"]
ATTEMPT_TABLE = Base.metadata.tables["attempt"]
GATE_RECORD_TABLE = Base.metadata.tables["gate_record"]


# ── entities under test ──────────────────────────────────────────────────────


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "story",
        "template_version": 1,
        "status": "queued",
        "budget_usd": Decimal("10.000000"),
        "created_at": AT,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_full_run() -> Run:
    """A Run with every optional field filled — what the round trip has to survive."""
    return a_run(
        pinned_versions=(TemplateRef(name="story", version=1), TemplateRef(name="epic", version=2)),
        inputs={"base_branch": "main", "harness": "claude"},
        status="needs_you",
        plan_ref="abc123",
        plan_refs={"docs/stories.yaml": "def456"},
        engine_ref={"workflow_id": "w-1"},
        spend_usd=Decimal("1.250000"),
        manual_estimate_h=Decimal("2.50"),
        re_review_done=True,
        park_kind="checkpoint",
        park_path="steps[2]",
        park_reason="review the diff",
        accepted_paths=("tests/unit/a.py",),
        worktree_path="/work/wt/a",
        worktrees=(
            Worktree(branch="story/4-1", path="/work/wt/a", created_branch=True, pushed=False),
        ),
        compare_urls=("https://example.invalid/compare/a...b",),
        trace_id="trace-1",
        terminal_session=True,
        active_seconds=120,
        last_opened_at=AT,
        started_at=AT,
        ended_at=AT,
    )


def a_step(run_id: UUID, seq: int = 1, **overrides: object) -> StepRun:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": run_id,
        "seq": seq,
        "path": f"steps[{seq}]",
        "label": f"step {seq}",
        "kind": "shell",
        "gate": "deterministic",
        "status": "planned",
    }
    fields.update(overrides)
    return StepRun(**fields)  # type: ignore[arg-type]


def an_attempt(**overrides: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 1,
        "status": "running",
    }
    fields.update(overrides)
    return Attempt(**fields)  # type: ignore[arg-type]


def a_full_attempt() -> Attempt:
    return an_attempt(
        status="done",
        started_at=AT,
        ended_at=AT,
        engine_ref={"step": "agent"},
        start_sha="aaa",
        end_sha="bbb",
        frozen_test_files=("tests/unit/a.py",),
        log_path="/work/logs/1.log",
        exit_code=0,
        output_ref="/work/logs/1.log",
        harness="claude",
        model="sonnet",
        session_id="s-1",
        pgid=4321,
        tokens_in=10,
        tokens_out=20,
        cost_usd=Decimal("0.012345"),
        cost_provisional=True,
    )


def a_record(run_id: UUID, **overrides: object) -> GateRecord:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": run_id,
        "at": AT,
        "event": "start",
        "actor": "machine",
        "text": "run started",
    }
    fields.update(overrides)
    return GateRecord(**fields)  # type: ignore[arg-type]


# ── the session double ───────────────────────────────────────────────────────


class RecordingResult:
    """What `Session.scalars` returns: one canned answer, whatever shape it holds."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect.

    `order` holds the write calls in the order they were made, which is what the flush
    assertions below read: an adapter that flushed before adding would emit an empty flush
    and still leave the insert unordered, so "it flushed" is not the claim — "it flushed
    after the add" is.
    """

    def __init__(
        self,
        rows: dict[Any, Any] | None = None,
        scalars_queue: list[list[Any]] | None = None,
    ) -> None:
        self.added: list[Any] = []
        self.gets: list[tuple[type, Any]] = []
        self.statements: list[Any] = []
        self.order: list[str] = []
        self.flushes = 0
        self._rows = dict(rows or {})
        self._scalars_queue = list(scalars_queue or [])

    def add(self, row: Any) -> None:
        self.added.append(row)
        self.order.append("add")

    def flush(self) -> None:
        self.flushes += 1
        self.order.append("flush")

    def get(self, entity: type, key: Any) -> Any:
        self.gets.append((entity, key))
        return self._rows.get(key)

    def scalars(self, statement: Any) -> RecordingResult:
        self.statements.append(statement)
        return RecordingResult(self._scalars_queue.pop(0))


def runs_repository(session: RecordingSession) -> SQLAlchemyRunRepository:
    return SQLAlchemyRunRepository(session)  # type: ignore[arg-type]


def steps_repository(session: RecordingSession) -> SQLAlchemyStepRunRepository:
    return SQLAlchemyStepRunRepository(session)  # type: ignore[arg-type]


def attempts_repository(session: RecordingSession) -> SQLAlchemyAttemptRepository:
    return SQLAlchemyAttemptRepository(session)  # type: ignore[arg-type]


def records_repository(session: RecordingSession) -> SQLAlchemyGateRecordRepository:
    return SQLAlchemyGateRecordRepository(session)  # type: ignore[arg-type]


# ── the tables ───────────────────────────────────────────────────────────────


def test_the_models_declare_the_four_tables_the_migration_creates() -> None:
    assert RunRow.__tablename__ == "run"
    assert StepRunRow.__tablename__ == "step_run"
    assert AttemptRow.__tablename__ == "attempt"
    assert GateRecordRow.__tablename__ == "gate_record"
    assert {"run", "step_run", "attempt", "gate_record"} <= set(Base.metadata.tables)


def test_the_run_table_carries_exactly_the_columns_the_entity_needs() -> None:
    assert set(RUN_TABLE.columns.keys()) == set(Run.model_fields)


def test_the_step_run_table_carries_exactly_the_columns_the_entity_needs() -> None:
    assert set(STEP_RUN_TABLE.columns.keys()) == set(StepRun.model_fields)


def test_the_attempt_table_carries_exactly_the_columns_the_entity_needs() -> None:
    assert set(ATTEMPT_TABLE.columns.keys()) == set(Attempt.model_fields)


def test_the_gate_record_table_carries_exactly_the_columns_the_entity_needs() -> None:
    assert set(GATE_RECORD_TABLE.columns.keys()) == set(GateRecord.model_fields)


@pytest.mark.parametrize(
    ("column", "kind"),
    [
        ("id", Uuid),
        ("project_id", Uuid),
        ("repository_id", Uuid),
        ("template_name", Text),
        ("template_version", Integer),
        ("pinned_versions", JSONB),
        ("inputs", JSONB),
        ("status", Text),
        ("plan_refs", JSONB),
        ("engine_ref", JSONB),
        ("budget_usd", Numeric),
        ("spend_usd", Numeric),
        ("manual_estimate_h", Numeric),
        ("re_review_done", Boolean),
        ("accepted_paths", JSONB),
        ("worktrees", JSONB),
        ("compare_urls", JSONB),
        ("terminal_session", Boolean),
        ("active_seconds", Integer),
        ("created_at", DateTime),
    ],
)
def test_each_run_column_has_the_type_the_migration_creates(column: str, kind: type) -> None:
    assert isinstance(RUN_TABLE.columns[column].type, kind)


def test_money_is_numeric_twelve_six_and_the_estimate_is_numeric_ten_two() -> None:
    """Consistency Conventions: money is `numeric(12,6)` USD, never a float."""
    money_precision, money_scale = 12, 6
    for column in ("budget_usd", "spend_usd"):
        assert RUN_TABLE.columns[column].type.precision == money_precision  # type: ignore[attr-defined]
        assert RUN_TABLE.columns[column].type.scale == money_scale  # type: ignore[attr-defined]
    assert ATTEMPT_TABLE.columns["cost_usd"].type.precision == money_precision  # type: ignore[attr-defined]
    assert ATTEMPT_TABLE.columns["cost_usd"].type.scale == money_scale  # type: ignore[attr-defined]
    hours_precision, hours_scale = 10, 2
    estimate = RUN_TABLE.columns["manual_estimate_h"].type
    assert (estimate.precision, estimate.scale) == (hours_precision, hours_scale)  # type: ignore[attr-defined]


@pytest.mark.parametrize("column", ["created_at", "started_at", "ended_at", "last_opened_at"])
def test_every_run_timestamp_carries_its_zone(column: str) -> None:
    assert RUN_TABLE.columns[column].type.timezone is True  # type: ignore[attr-defined]


def test_the_gate_record_timestamp_carries_its_zone() -> None:
    assert GATE_RECORD_TABLE.columns["at"].type.timezone is True  # type: ignore[attr-defined]


#: The columns a later story fills, which therefore start `NULL`.
NULLABLE = {
    "run": {
        "budget_usd",  # Operator decision 2026-09-17: run.budget_usd nullable (story 3-2)
        "plan_ref",
        "manual_estimate_h",
        "park_kind",
        "park_path",
        "park_reason",
        "worktree_path",
        "trace_id",
        "last_opened_at",
        "last_opened_before",
        "started_at",
        "ended_at",
        # operator revision 2026-09-15: added by story 5-1 (nullable for old runs)
        "partition_branch",
        # operator revision 2026-09-18: added by story 5-3 (nullable; predecessor run ref)
        "after_run_id",
    },
    "step_run": {"reason", "frame", "story_id"},
    "attempt": {
        "started_at",
        "ended_at",
        "start_sha",
        "end_sha",
        "frozen_test_files",
        "log_path",
        "exit_code",
        "output_ref",
        "harness",
        "model",
        "session_id",
        "pgid",
        "tokens_in",
        "tokens_out",
        "cost_usd",
    },
    "gate_record": {"path", "attempt_n"},
}


@pytest.mark.parametrize(
    "table", [RUN_TABLE, STEP_RUN_TABLE, ATTEMPT_TABLE, GATE_RECORD_TABLE], ids=lambda t: t.name
)
def test_only_the_columns_a_later_story_fills_may_be_null(table: Any) -> None:
    nullable = {column.name for column in table.columns if column.nullable}

    assert nullable == NULLABLE[table.name]


@pytest.mark.parametrize(
    "table", [RUN_TABLE, STEP_RUN_TABLE, ATTEMPT_TABLE, GATE_RECORD_TABLE], ids=lambda t: t.name
)
def test_every_table_is_keyed_by_its_uuid_v7_id(table: Any) -> None:
    assert [column.name for column in table.primary_key.columns] == ["id"]


def test_the_run_table_indexes_the_columns_the_board_and_the_queue_filter_on() -> None:
    indexes = {index.name: index for index in RUN_TABLE.indexes}

    assert set(indexes) == {"ix_run_project_id", "ix_run_status", "ix_run_repository_id_status"}
    for index in indexes.values():
        assert index.unique is False, index.name
    assert [c.name for c in indexes["ix_run_repository_id_status"].columns] == [
        "repository_id",
        "status",
    ]


def test_the_step_run_table_is_unique_on_seq_and_on_path_within_one_run() -> None:
    indexes = {index.name: index for index in STEP_RUN_TABLE.indexes}

    assert set(indexes) == {"ix_step_run_run_id_seq", "ix_step_run_run_id_path"}
    for index in indexes.values():
        assert index.unique is True, index.name
    assert [c.name for c in indexes["ix_step_run_run_id_seq"].columns] == ["run_id", "seq"]
    assert [c.name for c in indexes["ix_step_run_run_id_path"].columns] == ["run_id", "path"]


def test_the_attempt_table_is_unique_on_n_within_one_row() -> None:
    indexes = {index.name: index for index in ATTEMPT_TABLE.indexes}

    assert set(indexes) == {"ix_attempt_step_run_id_n"}
    index = indexes["ix_attempt_step_run_id_n"]
    assert index.unique is True
    assert [c.name for c in index.columns] == ["step_run_id", "n"]


def test_the_gate_record_table_is_indexed_the_way_it_is_read() -> None:
    indexes = {index.name: index for index in GATE_RECORD_TABLE.indexes}

    assert set(indexes) == {"ix_gate_record_run_id_at"}
    index = indexes["ix_gate_record_run_id_at"]
    assert index.unique is False
    assert [c.name for c in index.columns] == ["run_id", "at"]


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        (RUN_TABLE, {("project_id", "project"), ("repository_id", "repository")}),
        (STEP_RUN_TABLE, {("run_id", "run")}),
        (ATTEMPT_TABLE, {("run_id", "run"), ("step_run_id", "step_run")}),
        (GATE_RECORD_TABLE, {("run_id", "run")}),
    ],
    ids=lambda value: getattr(value, "name", "expected"),
)
def test_every_foreign_key_points_where_the_er_diagram_says(
    table: Any, expected: set[tuple[str, str]]
) -> None:
    assert {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys} == expected


# ── the converters ───────────────────────────────────────────────────────────


def test_a_minimal_run_round_trips_through_its_row() -> None:
    run = a_run()

    assert runs_module.to_entity(RunRow(**runs_module.row_values(run))) == run


def test_a_fully_filled_run_round_trips_through_its_row() -> None:
    run = a_full_run()

    assert runs_module.to_entity(RunRow(**runs_module.row_values(run))) == run


def test_the_pinned_versions_column_holds_the_pairs_in_order() -> None:
    run = a_full_run()

    assert runs_module.row_values(run)["pinned_versions"] == [
        {"name": "story", "version": 1},
        {"name": "epic", "version": 2},
    ]


def test_the_worktrees_column_holds_one_object_per_worktree() -> None:
    run = a_full_run()

    assert runs_module.row_values(run)["worktrees"] == [
        {"branch": "story/4-1", "path": "/work/wt/a", "created_branch": True, "pushed": False}
    ]


def test_the_tuple_columns_are_stored_as_json_lists() -> None:
    values = runs_module.row_values(a_full_run())

    assert values["accepted_paths"] == ["tests/unit/a.py"]
    assert values["compare_urls"] == ["https://example.invalid/compare/a...b"]


def test_a_step_run_round_trips_through_its_row() -> None:
    row = a_step(new_id(), 2, reason="skipped by operator", frame="steps[1]", story_id="4-1")

    assert step_runs_module.to_entity(StepRunRow(**step_runs_module.row_values(row))) == row


def test_a_minimal_attempt_round_trips_through_its_row() -> None:
    attempt = an_attempt()

    assert attempts_module.to_entity(AttemptRow(**attempts_module.row_values(attempt))) == attempt


def test_a_fully_filled_attempt_round_trips_through_its_row() -> None:
    attempt = a_full_attempt()

    assert attempts_module.to_entity(AttemptRow(**attempts_module.row_values(attempt))) == attempt


def test_the_frozen_test_files_column_is_null_when_the_attempt_froze_nothing() -> None:
    assert attempts_module.row_values(an_attempt())["frozen_test_files"] is None


def test_a_gate_record_round_trips_through_its_row() -> None:
    record = a_record(new_id(), path="steps[2]", attempt_n=2, payload={"accepted": ["a.py"]})

    assert (
        gate_records_module.to_entity(GateRecordRow(**gate_records_module.row_values(record)))
        == record
    )


# ── the adapters satisfy the ports ───────────────────────────────────────────


def test_the_run_adapter_satisfies_the_port() -> None:
    runs: RunRepository = runs_repository(RecordingSession())

    assert isinstance(runs, RunRepository)


def test_the_step_run_adapter_satisfies_the_port() -> None:
    steps: StepRunRepository = steps_repository(RecordingSession())

    assert isinstance(steps, StepRunRepository)


def test_the_attempt_adapter_satisfies_the_port() -> None:
    attempts: AttemptRepository = attempts_repository(RecordingSession())

    assert isinstance(attempts, AttemptRepository)


def test_the_gate_record_adapter_satisfies_the_port() -> None:
    records: GateRecordRepository = records_repository(RecordingSession())

    assert isinstance(records, GateRecordRepository)


# ── SQLAlchemyRunRepository ──────────────────────────────────────────────────


def test_add_inserts_one_row_carrying_the_whole_run() -> None:
    session = RecordingSession()
    run = a_full_run()

    runs_repository(session).add(run)

    (row,) = session.added
    assert isinstance(row, RunRow)
    assert runs_module.to_entity(row) == run


def test_get_reads_the_row_by_primary_key() -> None:
    run = a_run()
    session = RecordingSession(rows={run.id: RunRow(**runs_module.row_values(run))})

    assert runs_repository(session).get(run.id) == run
    assert session.gets == [(RunRow, run.id)]


def test_get_answers_none_for_an_id_that_is_not_stored() -> None:
    assert runs_repository(RecordingSession()).get(new_id()) is None


def test_update_writes_every_mutable_column_back_onto_the_row() -> None:
    run = a_run()
    row = RunRow(**runs_module.row_values(run))
    session = RecordingSession(rows={run.id: row})
    changed = run.model_copy(
        update={
            "status": "needs_you",
            "spend_usd": Decimal("3.000000"),
            "park_kind": "budget",
            "worktrees": (Worktree(branch="b", path="/p", created_branch=False, pushed=True),),
        }
    )

    runs_repository(session).update(changed)

    assert runs_module.to_entity(row) == changed


def test_update_refuses_an_id_the_table_does_not_hold() -> None:
    with pytest.raises(ValueError, match="no run with id"):
        runs_repository(RecordingSession()).update(a_run())


def test_update_never_rewrites_the_primary_key() -> None:
    run = a_run()
    row = RunRow(**runs_module.row_values(run))
    session = RecordingSession(rows={run.id: row})

    runs_repository(session).update(run.model_copy(update={"status": "running"}))

    assert row.id == run.id
    assert "id" not in runs_module.MUTABLE_COLUMNS


def test_list_is_newest_first_and_unfiltered_by_default() -> None:
    run = a_run()
    session = RecordingSession(scalars_queue=[[RunRow(**runs_module.row_values(run))]])

    assert runs_repository(session).list() == [run]
    rendered = str(session.statements[0])
    assert "ORDER BY run.created_at DESC, run.id DESC" in rendered
    assert "WHERE" not in rendered


def test_list_filters_by_project_when_one_is_given() -> None:
    project_id = new_id()
    session = RecordingSession(scalars_queue=[[]])

    assert runs_repository(session).list(project_id=project_id) == []
    assert "run.project_id" in str(session.statements[0])


def test_list_by_status_filters_on_the_status_column() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert runs_repository(session).list_by_status("running") == []
    rendered = str(session.statements[0])
    assert "run.status" in rendered
    assert "ORDER BY run.created_at DESC" in rendered


def test_list_by_repository_non_terminal_excludes_the_three_terminal_statuses() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert runs_repository(session).list_by_repository_non_terminal(new_id()) == []
    rendered = str(session.statements[0])
    assert "run.repository_id" in rendered
    assert "run.status NOT IN" in rendered


# ── SQLAlchemyStepRunRepository ──────────────────────────────────────────────


def test_add_many_inserts_one_row_per_planned_row() -> None:
    session = RecordingSession()
    run_id = new_id()
    rows = [a_step(run_id, 1), a_step(run_id, 2)]

    steps_repository(session).add_many(rows)

    assert [step_runs_module.to_entity(row) for row in session.added] == rows


def test_add_many_inserts_nothing_for_an_empty_plan() -> None:
    session = RecordingSession()

    steps_repository(session).add_many([])

    assert session.added == []


def test_get_by_seq_selects_on_the_run_and_the_seq() -> None:
    run_id = new_id()
    row = a_step(run_id, 3)
    session = RecordingSession(scalars_queue=[[StepRunRow(**step_runs_module.row_values(row))]])

    assert steps_repository(session).get_by_seq(run_id, 3) == row
    rendered = str(session.statements[0])
    assert "step_run.run_id" in rendered
    assert "step_run.seq" in rendered


def test_get_by_seq_answers_none_for_a_row_that_is_not_stored() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert steps_repository(session).get_by_seq(new_id(), 1) is None


def test_list_for_run_is_ordered_by_seq() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert steps_repository(session).list_for_run(new_id()) == []
    assert "ORDER BY step_run.seq" in str(session.statements[0])


def test_step_update_writes_the_mutable_columns_back() -> None:
    row = a_step(new_id(), 1)
    stored = StepRunRow(**step_runs_module.row_values(row))
    session = RecordingSession(rows={row.id: stored})
    changed = row.model_copy(
        update={"status": "error", "reason": "exit 1", "retry_count": 1, "with_resolved": {"a": 1}}
    )

    steps_repository(session).update(changed)

    assert step_runs_module.to_entity(stored) == changed


def test_step_update_refuses_an_id_the_table_does_not_hold() -> None:
    with pytest.raises(ValueError, match="no step run with id"):
        steps_repository(RecordingSession()).update(a_step(new_id()))


def test_first_queued_selects_the_lowest_queued_seq() -> None:
    run_id = new_id()
    row = a_step(run_id, 2, status="queued")
    session = RecordingSession(scalars_queue=[[StepRunRow(**step_runs_module.row_values(row))]])

    assert steps_repository(session).first_queued(run_id) == row
    rendered = str(session.statements[0])
    assert "step_run.status" in rendered
    assert "ORDER BY step_run.seq" in rendered


def test_first_queued_is_none_when_nothing_is_waiting() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert steps_repository(session).first_queued(new_id()) is None


# ── SQLAlchemyAttemptRepository ──────────────────────────────────────────────


def test_attempt_add_inserts_one_row() -> None:
    session = RecordingSession()
    attempt = a_full_attempt()

    attempts_repository(session).add(attempt)

    (row,) = session.added
    assert attempts_module.to_entity(row) == attempt


def test_get_latest_orders_by_n_descending() -> None:
    attempt = an_attempt(n=2)
    session = RecordingSession(scalars_queue=[[AttemptRow(**attempts_module.row_values(attempt))]])

    assert attempts_repository(session).get_latest(attempt.step_run_id) == attempt
    rendered = str(session.statements[0])
    assert "attempt.step_run_id" in rendered
    assert "ORDER BY attempt.n DESC" in rendered


def test_get_latest_is_none_for_a_row_that_never_ran() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert attempts_repository(session).get_latest(new_id()) is None


def test_list_for_row_is_ordered_by_n() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert attempts_repository(session).list_for_row(new_id()) == []
    assert "ORDER BY attempt.n" in str(session.statements[0])


def test_mark_started_writes_only_the_start_half() -> None:
    attempt = an_attempt()
    row = AttemptRow(**attempts_module.row_values(attempt))
    session = RecordingSession(rows={attempt.id: row})
    started = attempt.model_copy(
        update={
            "started_at": AT,
            "start_sha": "aaa",
            "frozen_test_files": ("tests/unit/a.py",),
            "pgid": 4321,
            # the finish half is set on the entity and must not reach the row
            "end_sha": "bbb",
            "exit_code": 0,
        }
    )

    attempts_repository(session).mark_started(started)

    assert (row.started_at, row.start_sha, row.pgid) == (AT, "aaa", 4321)
    assert row.frozen_test_files == ["tests/unit/a.py"]
    assert row.end_sha is None
    assert row.exit_code is None


def test_mark_finished_writes_only_the_finish_half() -> None:
    attempt = an_attempt(start_sha="aaa")
    row = AttemptRow(**attempts_module.row_values(attempt))
    session = RecordingSession(rows={attempt.id: row})
    finished = attempt.model_copy(
        update={
            "status": "done",
            "ended_at": AT,
            "end_sha": "bbb",
            "exit_code": 0,
            "session_id": "s-1",
            "log_path": "/work/logs/1.log",
            "tokens_in": 10,
            "cost_usd": Decimal("0.010000"),
            "start_sha": "overwritten",
        }
    )

    attempts_repository(session).mark_finished(finished)

    assert (row.status, row.ended_at, row.end_sha, row.exit_code) == ("done", AT, "bbb", 0)
    assert row.cost_usd == Decimal("0.010000")
    assert row.start_sha == "aaa"


def test_attempt_update_writes_every_mutable_column() -> None:
    attempt = an_attempt()
    row = AttemptRow(**attempts_module.row_values(attempt))
    session = RecordingSession(rows={attempt.id: row})
    changed = a_full_attempt().model_copy(
        update={"id": attempt.id, "run_id": attempt.run_id, "step_run_id": attempt.step_run_id}
    )

    attempts_repository(session).update(changed)

    assert attempts_module.to_entity(row) == changed


@pytest.mark.parametrize("method", ["mark_started", "mark_finished", "update"])
def test_writing_an_attempt_the_table_does_not_hold_is_refused(method: str) -> None:
    session = RecordingSession()

    with pytest.raises(ValueError, match="no attempt with id"):
        getattr(attempts_repository(session), method)(an_attempt())


def test_latest_for_run_orders_by_started_at_descending() -> None:
    attempt = an_attempt(n=2)
    session = RecordingSession(scalars_queue=[[AttemptRow(**attempts_module.row_values(attempt))]])

    assert attempts_repository(session).latest_for_run(attempt.run_id) == attempt
    rendered = str(session.statements[0])
    assert "attempt.run_id" in rendered
    assert "ORDER BY attempt.started_at DESC" in rendered


def test_latest_for_run_is_none_when_no_attempts_exist() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert attempts_repository(session).latest_for_run(new_id()) is None


# ── SQLAlchemyGateRecordRepository ───────────────────────────────────────────


def test_a_gate_record_is_appended_as_one_row() -> None:
    session = RecordingSession()
    record = a_record(new_id(), path="steps[2]", attempt_n=1)

    records_repository(session).add(record)

    (row,) = session.added
    assert gate_records_module.to_entity(row) == record


def test_gate_records_are_read_oldest_first_with_the_id_breaking_a_tie() -> None:
    run_id = new_id()
    record = a_record(run_id)
    session = RecordingSession(
        scalars_queue=[[GateRecordRow(**gate_records_module.row_values(record))]]
    )

    assert records_repository(session).list_for_run(run_id) == [record]
    rendered = str(session.statements[0])
    assert "gate_record.run_id" in rendered
    assert "ORDER BY gate_record.at, gate_record.id" in rendered


def test_the_gate_record_adapter_has_no_way_to_change_a_record() -> None:
    """Append-only is kept by the class not having the method, not by remembering."""
    public = {name for name in vars(SQLAlchemyGateRecordRepository) if not name.startswith("_")}

    assert public == {"add", "list_for_run"}


# ── the inserts are ordered against each other (AD-8: one unit of work) ──────


def test_adding_a_run_emits_its_insert_before_returning() -> None:
    """`attempt` references `run`; with no `relationship()` the ORM will not order them."""
    session = RecordingSession()

    runs_repository(session).add(a_run())

    assert session.order == ["add", "flush"]


def test_adding_a_plan_emits_every_insert_before_returning() -> None:
    session = RecordingSession()
    run_id = new_id()

    steps_repository(session).add_many([a_step(run_id, 1), a_step(run_id, 2)])

    assert session.order == ["add", "add", "flush"]


def test_an_empty_plan_still_flushes_only_once_and_adds_nothing() -> None:
    session = RecordingSession()

    steps_repository(session).add_many([])

    assert session.order == ["flush"]


def test_adding_an_attempt_emits_its_insert_before_returning() -> None:
    session = RecordingSession()

    attempts_repository(session).add(an_attempt())

    assert session.order == ["add", "flush"]


def test_adding_a_gate_record_emits_its_insert_before_returning() -> None:
    session = RecordingSession()

    records_repository(session).add(a_record(new_id()))

    assert session.order == ["add", "flush"]


@pytest.mark.parametrize(
    "call",
    [
        lambda session: runs_repository(session).get(new_id()),
        lambda session: runs_repository(session).list(),
        lambda session: steps_repository(session).list_for_run(new_id()),
        lambda session: attempts_repository(session).get_latest(new_id()),
        lambda session: records_repository(session).list_for_run(new_id()),
    ],
    ids=["run get", "run list", "step list", "attempt latest", "gate record list"],
)
def test_a_read_never_flushes(call: Any) -> None:
    """Flushing is the insert methods' business; a read has no write to order."""
    session = RecordingSession(scalars_queue=[[], [], [], [], []])

    call(session)

    assert session.flushes == 0


@pytest.mark.parametrize(
    "call",
    [
        lambda session, run: runs_repository(session).update(run),
    ],
    ids=["run update"],
)
def test_an_update_never_flushes(call: Any) -> None:
    """An update writes onto a row the database already holds; nothing is waiting on it."""
    run = a_run()
    session = RecordingSession(rows={run.id: RunRow(**runs_module.row_values(run))})

    call(session, run.model_copy(update={"status": "running"}))

    assert session.flushes == 0
