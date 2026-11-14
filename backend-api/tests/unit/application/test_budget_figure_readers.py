"""Every reader of spend against budget goes through `budget.figure` (story 5, owner decision
T4, 2026-11-12): `budget_raise` validation, `agent_env.remaining` and the session refusals."""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.rules.signals import validate
from orchestrator.application.rules.signals_table import BUDGET_KEY
from orchestrator.application.steps import agent_env
from orchestrator.application.use_cases.session_checks import NO_BUDGET
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal
from tests.unit.application.session_turn_fixtures import a_turn_world
from tests.unit.application.test_budget_figure import a_run as a_figure_run
from tests.unit.application.test_session_start import a_session_world, refused
from tests.unit.application.test_session_turn_message import refused as turn_refused
from tests.unit.application.test_signal_rules import a_row, parked


def raise_to(run: object, figure: str) -> object:
    return validate(
        run, a_row("agent", "blocked"), Signal(kind="budget_raise", payload={BUDGET_KEY: figure})
    )  # type: ignore[arg-type]


def test_a_budget_raise_is_checked_against_the_gate_figure() -> None:
    run = parked("budget", spend_usd=Decimal("3"), gate_spend_usd=Decimal("10.50"))

    assert raise_to(run, "12") is not None
    with pytest.raises(Conflict, match=r"spend \$10\.50"):
        raise_to(run, "10.00")


def test_the_remaining_budget_is_budget_less_the_gate_figure() -> None:
    run = a_figure_run(spend="9", gate="4", budget_usd="10")

    assert agent_env.remaining(run) == Decimal("6")


def test_a_session_start_with_the_gate_at_budget_is_refused_whatever_spend_says() -> None:
    session = a_session_world(
        budget_usd=Decimal("10"), spend_usd=Decimal("0"), gate_spend_usd=Decimal("10")
    )

    assert refused(session, Conflict) == NO_BUDGET


def test_a_session_message_with_the_gate_at_budget_is_refused() -> None:
    world = a_turn_world()
    run = world.session.world.stored_run()
    world.session.world.ports.runs.update(
        run.model_copy(
            update={
                "budget_usd": Decimal("10"),
                "spend_usd": Decimal("0"),
                "gate_spend_usd": Decimal("10"),
            }
        )
    )

    assert turn_refused(world, Conflict) == NO_BUDGET
