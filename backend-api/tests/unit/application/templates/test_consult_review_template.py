"""An `agent` row's `consult.on` may name `protected_path` beside `blocked` (story 1-8, spine
AD-22, 2026-11-02); `budget` and every other token are still refused. Fixture templates only
(hard rule 6)."""

from __future__ import annotations

import pytest

from orchestrator.application.templates.model import INVALID_CONSULT_ON
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates.test_consult_template import (
    CONSULT,
    CONSULT_LINE,
    HEADER,
    errors_of,
    planned,
    work_row,
)
from tests.unit.fakes.templates import FakeTemplateVersionRepository

ON = "      on: [blocked]\n"


def with_on(stops: str) -> str:
    return HEADER + CONSULT.replace(ON, f"      on: {stops}\n")


@pytest.mark.parametrize("stops", ["[blocked, protected_path]", "[protected_path]"])
def test_a_protected_path_stop_is_valid(stops: str) -> None:
    result = validate(with_on(stops), templates=FakeTemplateVersionRepository([]))

    assert result.errors == ()
    agent = result.template.steps[0].agent  # type: ignore[union-attr]
    assert agent is not None
    assert agent.consult is not None
    assert "protected_path" in agent.consult.on


def test_the_planned_block_carries_both_stops() -> None:
    plan = planned(with_on("[blocked, protected_path]"), senior_model="senior")

    assert work_row(plan)["consult"]["on"] == ["blocked", "protected_path"]


@pytest.mark.parametrize(
    "stops", ["[blocked, protected_path, budget]", "[timeout]", "[verify_failed]"]
)
def test_every_other_stop_is_still_refused(stops: str) -> None:
    assert errors_of(with_on(stops)) == [(CONSULT_LINE + 3, INVALID_CONSULT_ON)]
