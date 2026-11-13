"""The seven fact tables as the models declare them (AGENTS.md "Data capture")."""

from __future__ import annotations

from sqlalchemy import ARRAY, CheckConstraint, Numeric, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models import facts  # noqa: F401

TABLES = (
    "fact_set",
    "gateway_read",
    "usage_fact",
    "request_fact",
    "activity_fact",
    "gap_fact",
    "event_fact",
)


def table(name: str):  # type: ignore[no-untyped-def]
    return Base.metadata.tables[name]


def test_the_seven_tables_exist() -> None:
    assert set(TABLES) <= set(Base.metadata.tables)


def test_money_is_numeric_twelve_six() -> None:
    for name, column in (("gateway_read", "usd"), ("usage_fact", "usd")):
        type_ = table(name).c[column].type
        assert isinstance(type_, Numeric)
        assert (type_.precision, type_.scale) == (12, 6)


def test_gaps_are_an_integer_array_and_not_null() -> None:
    column = table("gap_fact").c.gaps_s
    assert isinstance(column.type, ARRAY)
    assert not column.nullable


def test_nullability_follows_the_spec() -> None:
    nullable = {
        "fact_set": {"reason"},
        "gateway_read": {"rows", "calls", "prompt", "completion"},
        "usage_fact": {
            "fact_set_id",
            "gateway_read_id",
            "model",
            "conversation",
            "subagent_type",
            "tokens",
            "usd",
            "calls",
        },
        "request_fact": {"at"},
        "event_fact": {"path", "command", "exit_code"},
    }
    for name in TABLES:
        found = {c.name for c in table(name).columns if c.nullable and not c.primary_key}
        assert found == nullable.get(name, set()), name


def test_the_class_column_is_named_class() -> None:
    assert "class" in table("usage_fact").c
    assert not table("gateway_read").c.capped.nullable
    assert table("gateway_read").c.capped.server_default is not None


def test_a_usage_fact_has_exactly_one_parent_in_the_ddl() -> None:
    ddl = str(CreateTable(table("usage_fact")).compile(dialect=postgresql.dialect()))
    assert "CONSTRAINT ck_usage_fact_one_parent CHECK" in ddl
    assert "(fact_set_id IS NULL) <> (gateway_read_id IS NULL)" in ddl
    checks = [c for c in table("usage_fact").constraints if isinstance(c, CheckConstraint)]
    assert [c.name for c in checks] == ["ck_usage_fact_one_parent"]


def test_a_fact_set_is_unique_per_attempt_extractor_and_version() -> None:
    [unique] = [c for c in table("fact_set").constraints if isinstance(c, UniqueConstraint)]
    assert unique.name == "uq_fact_set_attempt_extractor_version"
    assert [c.name for c in unique.columns] == ["attempt_id", "extractor", "extractor_version"]
