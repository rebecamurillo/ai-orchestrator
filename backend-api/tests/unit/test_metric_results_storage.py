"""The calculation, version and value models and adapters: columns, constraints, SQL, and the
absence of any update or delete on a version or a value (epic 2 story 5: AC10)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from orchestrator.domain.entities.metric_results import (
    MetricCalculation,
    Origin,
    ResultVersion,
    StoredMetricValue,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.metric_results import (
    MetricCalculationRepository,
    ResultVersionRepository,
)
from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.metric_results import (
    MetricValueRow,
    ResultVersionRow,
)
from orchestrator.infrastructure.db.repositories import metric_results as module
from orchestrator.infrastructure.db.repositories.metric_results import (
    SQLAlchemyMetricCalculationRepository,
    SQLAlchemyResultVersionRepository,
)
from tests.unit.fakes.metric_results import FakeResultVersionRepository

TWO = 2
FOUR = 4

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
RUN = UUID(int=5)


class Session:
    """Records what the adapters hand it; answers scripted rows."""

    def __init__(self, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self.rows = rows or []
        self.scalar_value = scalar
        self.added: list[Any] = []
        self.statements: list[str] = []
        self.flushes = 0

    def add(self, row: Any) -> None:
        self.added.append(row)

    def add_all(self, rows: list[Any]) -> None:
        self.added.extend(rows)

    def flush(self) -> None:
        self.flushes += 1

    def get(self, _model: Any, _id: Any, **_options: Any) -> Any:
        return self.rows[0] if self.rows else None

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))

    def scalar(self, statement: Any) -> Any:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return self.scalar_value

    def scalars(self, statement: Any) -> Any:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        rows = self.rows

        class Scalars:
            def all(self) -> list[Any]:
                return rows

            def first(self) -> Any:
                return rows[0] if rows else None

        return Scalars()


def an_origin() -> Origin:
    return Origin(
        project_id=new_id(),
        run_id=RUN,
        template_name="t",
        template_version=1,
        harness="claude",
        origin_model_na="spans_models",
        origin_repository=".",
        branch="b",
        commit_na="commit_missing",
        base_commit="x",
    )


def a_value(version_id: UUID, **over: Any) -> StoredMetricValue:
    fields: dict[str, Any] = {
        "id": new_id(),
        "version_id": version_id,
        "metric_id": "cost.total",
        "method_id": "cost.total@1",
        "scope_type": "run",
        "scope_key": "run",
        "value_num": Decimal("1.5"),
        "unit": "usd",
        "origin": an_origin(),
    }
    return StoredMetricValue(**{**fields, **over})


def a_version() -> ResultVersion:
    return ResultVersion(
        id=new_id(),
        run_id=RUN,
        n=1,
        calculated_at=NOW,
        entry_point=("at_attempt_end", "workflow_step"),
        methods=("cost.total@1",),
        fact_set_ids=(new_id(),),
    )


def a_calculation(**over: Any) -> MetricCalculation:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": RUN,
        "target_n": 2,
        "state": "queued",
        "entry_point": ("manual",),
        "queued_at": NOW,
    }
    return MetricCalculation(**{**fields, **over})


def test_the_tables_and_their_nullable_columns() -> None:
    tables = Base.metadata.tables
    assert {c.name for c in tables["metric_calculation"].columns if c.nullable} == {
        "started_at",
        "ended_at",
    }
    assert {c.name for c in tables["result_version"].columns if c.nullable} == {
        "toolset_fingerprint"
    }
    nullable = {c.name for c in tables["metric_value"].columns if c.nullable}
    assert {"value_num", "missing", "carried_from", "harness_na", "commit_na"} <= nullable
    assert not nullable & {"metric_id", "method_id", "scope_type", "scope_key", "unit", "run_id"}


def test_the_figure_or_word_check_and_the_unique_pair_are_declared() -> None:
    names = {c.name for t in Base.metadata.tables.values() for c in t.constraints}
    assert {"ck_metric_value_figure_or_word", "uq_result_version_run_n"} <= names
    assert "ck_metric_calculation_state" in names
    ddl = str(CreateTable(MetricValueRow.__table__).compile(dialect=postgresql.dialect()))  # type: ignore[arg-type]
    assert "value_num IS NULL OR missing IS NULL OR missing = 'partial'" in ddl


def test_a_version_and_its_values_have_no_update_or_delete_anywhere() -> None:
    for kind in (
        ResultVersionRepository,
        FakeResultVersionRepository,
        SQLAlchemyResultVersionRepository,
    ):
        names = {n for n in dir(kind) if not n.startswith("_")}
        assert not {n for n in names if n.startswith(("update", "delete", "remove", "set"))}
    assert "set" in dir(MetricCalculationRepository)
    assert not {n for n in dir(SQLAlchemyMetricCalculationRepository) if n.startswith("delete")}


def test_a_version_is_inserted_with_its_values_in_the_callers_session() -> None:
    session = Session()
    version = a_version()
    values = [a_value(version.id), a_value(version.id, value_num=None, missing="not recorded")]

    SQLAlchemyResultVersionRepository(session).add(version, values)  # type: ignore[arg-type]

    head, *rows = session.added
    assert isinstance(head, ResultVersionRow)
    assert head.entry_point == ["at_attempt_end", "workflow_step"]
    assert head.fact_set_ids == [str(version.fact_set_ids[0])]
    assert all(isinstance(row, MetricValueRow) for row in rows)
    assert (rows[0].harness, rows[0].origin_model_na, rows[0].commit_na) == (
        "claude",
        "spans_models",
        "commit_missing",
    )
    assert session.flushes == TWO


def test_a_version_row_reads_back_as_the_entity_and_its_values_too() -> None:
    version = a_version()
    row = ResultVersionRow(
        id=version.id,
        run_id=RUN,
        n=1,
        calculated_at=NOW,
        entry_point=["at_attempt_end", "workflow_step"],
        methods=["cost.total@1"],
        fact_set_ids=[str(version.fact_set_ids[0])],
        toolset_fingerprint=None,
    )
    value = a_value(version.id)
    value_row = module._value_row(value)
    repository = SQLAlchemyResultVersionRepository(Session([row]))  # type: ignore[arg-type]

    assert repository.get(RUN, 1) == version
    assert repository.latest(RUN) == version
    assert repository.list_for_run(RUN) == [version]
    assert module._value(value_row) == value
    assert SQLAlchemyResultVersionRepository(Session([value_row])).values(version.id) == [value]  # type: ignore[arg-type]


def test_next_n_is_the_highest_plus_one() -> None:
    assert SQLAlchemyResultVersionRepository(Session(scalar=None)).next_n(RUN) == 1  # type: ignore[arg-type]
    assert SQLAlchemyResultVersionRepository(Session(scalar=3)).next_n(RUN) == FOUR  # type: ignore[arg-type]


def test_an_absent_version_is_none() -> None:
    repository = SQLAlchemyResultVersionRepository(Session())  # type: ignore[arg-type]

    assert repository.get(RUN, 1) is None
    assert repository.latest(RUN) is None


def test_a_calculation_round_trips_and_set_updates_four_columns_only() -> None:
    calculation = a_calculation()
    session = Session()
    repository = SQLAlchemyMetricCalculationRepository(session)  # type: ignore[arg-type]

    repository.add(calculation)
    row = session.added[0]
    assert row.entry_point == ["manual"]

    repository.set(calculation.model_copy(update={"state": "failed", "output": "boom"}))
    update = session.statements[0]
    assert update.startswith("UPDATE metric_calculation SET state=")
    assert "started_at=" in update and "ended_at=" in update and "output=" in update
    assert "run_id=" not in update and "target_n=" not in update

    readable = SQLAlchemyMetricCalculationRepository(Session([row]))  # type: ignore[arg-type]
    assert readable.get(calculation.id) == calculation
    assert readable.active_for_run(RUN) == calculation
    assert readable.newest_for_n(RUN, 2) == calculation
    assert readable.list_by_state("queued") == [calculation]


def test_absent_calculations_read_as_none() -> None:
    repository = SQLAlchemyMetricCalculationRepository(Session())  # type: ignore[arg-type]

    assert repository.get(new_id()) is None
    assert repository.active_for_run(RUN) is None
    assert repository.newest_for_n(RUN, 1) is None
    assert repository.list_by_state("running") == []
