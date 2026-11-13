"""The five `run` spend-figure columns round trip and are `NOT NULL` with server defaults
(story 5, owner decision T4, 2026-11-12). Pattern of `test_run_repository_adapter.py`."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import Boolean, Numeric

from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.run import RunRow
from orchestrator.infrastructure.db.repositories import runs as runs_module

MONEY = ("gateway_spend_usd", "harness_spend_usd", "gate_spend_usd")
FLAGS = ("gateway_reported", "harness_reported")


def a_run(**over: object) -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=None,
        created_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
        **over,  # type: ignore[arg-type]
    )


def test_the_five_figures_survive_a_round_trip() -> None:
    run = a_run(
        gateway_spend_usd=Decimal("1.250000"),
        harness_spend_usd=Decimal("3.300000"),
        gate_spend_usd=Decimal("3.300000"),
        gateway_reported=True,
        harness_reported=True,
    )

    back = runs_module.to_entity(RunRow(**runs_module.row_values(run)))

    for name in (*MONEY, *FLAGS):
        assert getattr(back, name) == getattr(run, name)


def test_a_row_the_database_has_not_defaulted_reads_as_zero_and_false() -> None:
    values = runs_module.row_values(a_run())
    for name in (*MONEY, *FLAGS):
        del values[name]

    back = runs_module.to_entity(RunRow(**values))

    assert (back.gateway_spend_usd, back.harness_spend_usd, back.gate_spend_usd) == (0, 0, 0)
    assert (back.gateway_reported, back.harness_reported) == (False, False)


@pytest.mark.parametrize("name", [*MONEY, *FLAGS])
def test_each_column_is_not_null_with_its_server_default(name: str) -> None:
    column = RunRow.__table__.c[name]

    assert column.nullable is False
    assert column.server_default is not None
    expected = "0" if name in MONEY else "FALSE"
    assert str(column.server_default.arg).upper() == expected  # type: ignore[attr-defined]
    assert isinstance(column.type, Numeric if name in MONEY else Boolean)
