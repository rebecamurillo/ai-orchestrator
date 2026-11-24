"""`create_run` stores the bound `initiative_folder` and refuses an outside one (story 2 of
epic 6, AC5/AC6)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.create_run import CreateRunRequest
from tests.unit.application import test_create_run_use_case as base
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_preflight_initiative_folder import FOLDER, initiatives_git
from tests.unit.fakes.projects import FakeRepositoryRepository


def harness(at: str = FOLDER) -> base.Harness:
    git = initiatives_git(at)
    git.files = {
        **(git.files or {}),
        (fixtures.BASE_SHA, f"{at}/epic-1/SPEC.md"): "# spec",
        (fixtures.BASE_SHA, f"{at}/epic-2/SPEC.md"): "# spec",
    }
    made = base.Harness(git=git)
    stored = replace(made.ports.preflight, repositories=FakeRepositoryRepository([folder_repo()]))
    made.ports = replace(made.ports, preflight=stored)
    return made


def folder_repo() -> Any:
    return base.repository().model_copy(update={"initiative_folder": FOLDER})


def request(**inputs: object) -> CreateRunRequest:
    return base.base_request(template_name="initiative", inputs=dict(inputs))


@pytest.mark.parametrize("given", [{}, {"initiative_folder": None}])
def test_an_omitted_folder_is_stored_bound(given: dict[str, object]) -> None:
    made = harness()

    result = made.create(request(**given))

    assert result.run.inputs["initiative_folder"] == FOLDER
    assert made.runs.runs[result.run.id].inputs["initiative_folder"] == FOLDER


@pytest.mark.parametrize("value", ["initiatives/snake", "initiatives"])
def test_a_value_equal_or_under_is_kept(value: str) -> None:
    result = harness(value).create(request(initiative_folder=value))

    assert result.run.inputs["initiative_folder"] == value


@pytest.mark.parametrize("value", ["docs/initiative", "initiatives/../x", "initiatives//a", 3])
def test_an_outside_value_raises_and_stores_nothing(value: object) -> None:
    made = harness()

    with pytest.raises(PlanError) as refusal:
        made.create(request(initiative_folder=value))

    assert f"initiative_folder {value}" in refusal.value.reason
    assert made.runs.runs == {}
    assert made.steps.steps == {}
    assert made.engine.calls == []


def test_a_template_without_the_input_stores_inputs_as_before() -> None:
    made = base.Harness(git=fixtures.repo_init_git())

    result = made.create(base.base_request(inputs={"initiative_folder": "elsewhere"}))

    assert result.run.inputs["initiative_folder"] == "elsewhere"
