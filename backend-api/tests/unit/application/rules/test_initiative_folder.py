"""`bind_initiative_folder` (story 2 of epic 6): the Run input read from the repository."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.rules.initiative_folder import bind_initiative_folder
from orchestrator.application.templates.plan_model import PlanError

FOLDER = "initiatives"


def bind(inputs: dict[str, Any], declared: bool = True) -> dict[str, Any]:
    return bind_initiative_folder(declared=declared, folder=FOLDER, inputs=inputs)


def test_an_undeclared_input_passes_through_even_when_outside() -> None:
    inputs = {"initiative_folder": "docs/x"}

    result = bind(inputs, declared=False)

    assert result == inputs
    assert result is not inputs


@pytest.mark.parametrize("inputs", [{}, {"initiative_folder": None}])
def test_an_absent_or_none_value_is_bound(inputs: dict[str, Any]) -> None:
    assert bind(inputs) == {"initiative_folder": FOLDER}


@pytest.mark.parametrize("value", ["initiatives", "initiatives/snake", "initiatives/a/b"])
def test_the_folder_and_what_lies_under_it_are_kept(value: str) -> None:
    assert bind({"initiative_folder": value, "x": 1}) == {"initiative_folder": value, "x": 1}


@pytest.mark.parametrize(
    "value", ["docs/initiative", "initiatives/../x", "initiatives//a", "initiativesx", 3]
)
def test_anything_else_is_refused_naming_the_value_and_the_folder(value: object) -> None:
    with pytest.raises(PlanError) as refusal:
        bind({"initiative_folder": value})

    assert refusal.value.reason == (
        f"initiative_folder {value} is not under the repository's initiative folder {FOLDER}"
    )


def test_the_input_mapping_is_not_mutated() -> None:
    inputs: dict[str, Any] = {}

    bind(inputs)

    assert inputs == {}
