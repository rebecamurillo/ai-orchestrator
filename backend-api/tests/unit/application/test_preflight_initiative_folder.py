"""Pre-flight binds the Run's `initiative_folder` once (story 2 of epic 6, AC5-AC7)."""

from __future__ import annotations

import pytest

from orchestrator.application.preflight.model import CHECK_WHAT_WILL_RUN, PreflightRequest
from orchestrator.application.use_cases.preflight import preflight_and_plan
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_preflight_use_case import epic_request, line, ports, repository
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.projects import FakeRepositoryRepository

FOLDER = "initiatives"


def initiatives_git(at: str = FOLDER) -> FakeGit:
    """The `initiative` fixture's files, moved to `at`, which lies under the repository's folder."""
    moved = {
        (ref, path.replace(fixtures.INITIATIVE_FOLDER, at)): text
        for (ref, path), text in fixtures.initiative_files().items()
    }
    return FakeGit(
        refs={
            fixtures.BASE_BRANCH: fixtures.BASE_SHA,
            fixtures.INITIATIVE_BRANCH: fixtures.WORK_SHA,
        },
        files=moved,
        listings={},
    )


def initiative_request(**inputs: object) -> PreflightRequest:
    return PreflightRequest(
        template_name="initiative",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        inputs=dict(inputs),
    )


def pass_over(request: PreflightRequest, git: FakeGit | None = None):  # type: ignore[no-untyped-def]
    return preflight_and_plan(
        ports(
            git=git or initiatives_git(),
            repositories=FakeRepositoryRepository([repository(initiative_folder=FOLDER)]),
        ),
        request,
    )


@pytest.mark.parametrize("given", [{}, {"initiative_folder": None}])
def test_an_omitted_folder_is_bound_and_the_plan_is_built_with_it(given: dict[str, object]) -> None:
    preflighted = pass_over(initiative_request(**given))

    assert preflighted.inputs["initiative_folder"] == FOLDER
    assert preflighted.plan_error is None
    assert preflighted.plan is not None
    epics = line(preflighted.result, "epics.yaml")
    assert epics.status == "ok"


@pytest.mark.parametrize("value", ["initiatives", "initiatives/snake"])
def test_a_folder_equal_or_under_is_kept(value: str) -> None:
    preflighted = pass_over(initiative_request(initiative_folder=value), initiatives_git(value))

    assert preflighted.inputs["initiative_folder"] == value
    assert preflighted.plan_error is None


@pytest.mark.parametrize("value", ["docs/initiative", "initiatives/../x", "initiatives//a", 3])
def test_an_outside_value_is_every_plan_error(value: object) -> None:
    preflighted = pass_over(initiative_request(initiative_folder=value))

    assert preflighted.plan is None
    assert preflighted.plan_error is not None
    assert f"initiative_folder {value} is not under" in preflighted.plan_error.reason
    assert preflighted.result.plan_error == preflighted.plan_error
    assert preflighted.result.start_allowed is False
    assert preflighted.result.rows is None
    assert line(preflighted.result, CHECK_WHAT_WILL_RUN).status == "fail"


def test_a_template_without_the_input_passes_inputs_through_unchanged() -> None:
    request = epic_request(inputs={**epic_request().inputs, "initiative_folder": "elsewhere"})

    preflighted = pass_over(request, fixtures.epic_git())

    assert preflighted.inputs == request.inputs
    assert preflighted.plan_error is None
