"""The fact store and the Run spend figures as Postgres holds them (epic run-facts stories 2, 5).

`tests/unit/test_run_facts_migration.py` and `tests/unit/test_run_spend_figures_migration.py`
read the revisions; only a migrated database can settle that the one-parent check on
`usage_fact` is enforced and that money landed as `numeric`. Every write here happens inside a
transaction that is rolled back, and every write is one the database must refuse, so the
shared stack is left as it was found.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from orchestrator.infrastructure.db import create_engine_from
from orchestrator.infrastructure.settings import Settings

CHECK_VIOLATION = "23514"
FACT_TABLES = (
    "fact_set",
    "gateway_read",
    "usage_fact",
    "request_fact",
    "activity_fact",
    "gap_fact",
    "event_fact",
)
MONEY_COLUMNS = (
    ("gateway_read", "usd"),
    ("usage_fact", "usd"),
    ("run", "gateway_spend_usd"),
    ("run", "harness_spend_usd"),
    ("run", "gate_spend_usd"),
)
RUN_FIGURES = (
    "gateway_spend_usd",
    "harness_spend_usd",
    "gate_spend_usd",
    "gateway_reported",
    "harness_reported",
)
INSERT_USAGE = text(
    "insert into public.usage_fact (id, fact_set_id, gateway_read_id, source, class, tokens) "
    "values (:id, :fact_set_id, :gateway_read_id, 'harness', 'output', 1)"
)


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture
def connection(settings: Settings) -> Iterator[Connection]:
    engine = create_engine_from(settings)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _columns(connection: Connection, table: str) -> dict[str, tuple[str, str, str | None]]:
    rows = connection.execute(
        text(
            "select column_name, data_type, is_nullable, column_default "
            "from information_schema.columns "
            "where table_schema = 'public' and table_name = :table"
        ),
        {"table": table},
    )
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


def test_the_seven_fact_tables_live_in_the_application_schema(connection: Connection) -> None:
    rows = connection.execute(
        text(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' and table_name = any(:names)"
        ),
        {"names": list(FACT_TABLES)},
    )

    assert sorted(row[0] for row in rows) == sorted(FACT_TABLES)


def test_money_is_stored_as_numeric(connection: Connection) -> None:
    for table, column in MONEY_COLUMNS:
        assert _columns(connection, table)[column][0] == "numeric", (table, column)


def test_the_run_figures_are_not_null_with_a_zero_or_false_default(
    connection: Connection,
) -> None:
    columns = _columns(connection, "run")

    for name in RUN_FIGURES:
        _, nullable, default = columns[name]
        assert nullable == "NO", name
        assert default is not None and ("0" in default or "false" in default), (name, default)


@pytest.mark.parametrize(
    "parents",
    [
        pytest.param({"fact_set_id": None, "gateway_read_id": None}, id="neither"),
        pytest.param({"fact_set_id": uuid4(), "gateway_read_id": uuid4()}, id="both"),
    ],
)
def test_a_usage_fact_without_exactly_one_parent_is_refused(
    connection: Connection, parents: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError) as refused:
        connection.execute(INSERT_USAGE, {"id": uuid4(), **parents})

    assert getattr(refused.value.orig, "sqlstate", None) == CHECK_VIOLATION
    assert "one_parent" in str(refused.value.orig)
