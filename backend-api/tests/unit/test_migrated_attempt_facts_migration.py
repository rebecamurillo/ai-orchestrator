"""Revision 0035 copies the figures attempts already carry into `migrated` facts (story 6;
SPEC CAP-6; ARCHITECTURE.md §9.5) — the AST for its shape, the pure helpers for its rows."""

from __future__ import annotations

import ast
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from itertools import count
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0035_migrated_attempt_facts.py"
NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)
ENDED = datetime(2026, 11, 1, tzinfo=UTC)
RUN_ID = UUID(int=1)


def load() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0035", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ids() -> Any:
    counter = count(100)
    return lambda: UUID(int=next(counter))


def constant(name: str) -> object:
    for node in ast.parse(MIGRATION.read_text()).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign):
            target = node.targets[0]
        if getattr(target, "id", None) == name and node.value is not None:  # type: ignore[union-attr]
            return ast.literal_eval(node.value)
    raise AssertionError(name)


def function(name: str) -> ast.FunctionDef:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(name)


def attempt(**fields: object) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": UUID(int=2),
        "run_id": RUN_ID,
        "model": "claude-opus-5",
        "ended_at": ENDED,
        "cost_usd": Decimal("0.40"),
        "cost_provisional": False,
        "tokens_in": 1000,
        "tokens_out": 200,
    }
    row.update(fields)
    return row


def test_the_revision_follows_run_spend_figures() -> None:
    assert constant("revision") == "0035_migrated_attempt_facts"
    assert constant("down_revision") == "0034_run_spend_figures"
    assert constant("EXTRACTOR") == "migrated"
    assert constant("EXTRACTOR_VERSION") == 1
    assert constant("REASON") == "migrated from attempt record"


def test_the_upgrade_selects_only_attempts_without_a_migrated_fact_set() -> None:
    source = ast.unparse(function("upgrade"))

    assert "exists" in source.lower()
    assert "EXTRACTOR" in source
    assert "EXTRACTOR_VERSION" in source


def test_the_upgrade_rewrites_the_five_figure_columns() -> None:
    assert "_rewrite_run_totals(conn)" in ast.unparse(function("upgrade"))
    source = ast.unparse(function("_rewrite_run_totals"))

    for column in (
        "gateway_spend_usd",
        "harness_spend_usd",
        "gate_spend_usd",
        "gateway_reported",
        "harness_reported",
    ):
        assert column in source
    assert "run_totals" in source


def test_every_table_handle_is_still_a_table_once_the_module_is_loaded() -> None:
    """A function sharing a handle's name rebinds it, and the upgrade fails on every database."""
    module = load()

    for name in ("_attempt", "_fact_set", "_gateway_read", "_usage_fact", "_run"):
        assert isinstance(getattr(module, name), sa.TableClause), name


def test_the_downgrade_is_not_supported() -> None:
    with pytest.raises(NotImplementedError, match="downgrade is not supported"):
        load().downgrade()


def test_a_settled_attempt_yields_a_set_a_read_and_a_gateway_money_row() -> None:
    fact_set, read, usage = load().plan_attempt(attempt(), NOW, ids())

    assert (fact_set["extractor"], fact_set["extractor_version"], fact_set["status"]) == (
        "migrated",
        1,
        "partial",
    )
    assert fact_set["reason"] == "migrated from attempt record"
    assert (fact_set["attempt_id"], fact_set["run_id"], fact_set["read_at"]) == (
        UUID(int=2),
        RUN_ID,
        NOW,
    )
    assert read is not None
    assert read["trigger"] == "attempt_end"
    assert read["read_at"] == ENDED
    assert (read["usd"], read["prompt"], read["completion"]) == (Decimal("0.40"), 1000, 200)
    assert (read["rows"], read["calls"], read["provisional"], read["capped"]) == (
        None,
        None,
        False,
        False,
    )
    (row,) = usage
    assert (row["source"], row["class"], row["usd"], row["model"]) == (
        "gateway",
        "money",
        Decimal("0.40"),
        "claude-opus-5",
    )
    assert (row["gateway_read_id"], row["fact_set_id"]) == (read["id"], None)


def test_a_provisional_attempt_yields_a_set_and_a_harness_money_row() -> None:
    fact_set, read, usage = load().plan_attempt(
        attempt(cost_usd=Decimal("0.30"), cost_provisional=True), NOW, ids()
    )

    assert read is None
    (row,) = usage
    assert (row["source"], row["class"], row["usd"]) == ("harness", "money", Decimal("0.30"))
    assert (row["fact_set_id"], row["gateway_read_id"]) == (fact_set["id"], None)


def test_an_attempt_without_cost_yields_only_the_set() -> None:
    fact_set, read, usage = load().plan_attempt(attempt(cost_usd=None), NOW, ids())

    assert fact_set["extractor"] == "migrated"
    assert (read, usage) == (None, [])


def test_a_null_ended_at_reads_at_the_migration_time() -> None:
    _, read, _ = load().plan_attempt(attempt(ended_at=None), NOW, ids())

    assert read is not None and read["read_at"] == NOW


def figures_for(module: Any, rows: list[dict[str, Any]]) -> Any:
    planned = [module.plan_attempt(row, NOW, ids()) for row in rows]
    reads = [(r, row["id"]) for (_, r, _), row in zip(planned, rows, strict=True) if r]
    read_usage = {r["id"]: u for (_, r, u) in planned if r for u in [u]}
    fact_money = {
        row["id"]: [u for u in us if u["fact_set_id"] is not None]
        for (_, _, us), row in zip(planned, rows, strict=True)
    }
    return module.run_totals(
        [row["id"] for row in rows],
        [{**r, "attempt_id": aid} for r, aid in reads],
        read_usage,
        fact_money,
    )


def test_run_totals_for_a_settled_attempt() -> None:
    got = figures_for(load(), [attempt()])

    assert got.gateway_usd == Decimal("0.40")
    assert got.gateway_reported is True
    assert got.harness_reported is False


def test_run_totals_for_a_provisional_attempt_count_in_the_gate() -> None:
    got = figures_for(load(), [attempt(cost_usd=Decimal("0.30"), cost_provisional=True)])

    assert (got.gateway_usd, got.harness_usd, got.gate_usd) == (
        Decimal("0"),
        Decimal("0.30"),
        Decimal("0.30"),
    )
    assert got.harness_reported is True


def test_the_same_input_twice_gives_equal_totals() -> None:
    module = load()
    rows = [attempt(), attempt(id=UUID(int=3), cost_usd=Decimal("0.3"), cost_provisional=True)]

    assert figures_for(module, rows) == figures_for(module, rows)
