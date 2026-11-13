"""Pre-flight lines built from a refusal carry its code and guide (story 1, AC4/AC5)."""

from __future__ import annotations

from orchestrator.application.preflight.model import (
    CHECK_WHAT_WILL_RUN,
    PreflightRequest,
    finding_line,
)
from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.preflight import run_preflight
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_preflight_use_case import line, ports
from tests.unit.fakes.git import FakeGit

DUPLICATE_EPICS = (
    "- id: e1\n  title: A\n  branch: b\n  spec_folder: epic-1\n"
    "- id: e1\n  title: B\n  branch: b\n  spec_folder: epic-2\n"
)


def test_ac4_a_duplicate_epic_id_line_carries_its_code() -> None:
    files = fixtures.initiative_files()
    files[(fixtures.BASE_SHA, f"{fixtures.INITIATIVE_FOLDER}/epics.yaml")] = DUPLICATE_EPICS
    git = FakeGit(
        refs={
            fixtures.BASE_BRANCH: fixtures.BASE_SHA,
            fixtures.INITIATIVE_BRANCH: fixtures.WORK_SHA,
        },
        files=files,
        listings={},
    )
    req = PreflightRequest(
        template_name="initiative",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        inputs={"initiative_folder": fixtures.INITIATIVE_FOLDER},
    )

    result = run_preflight(ports(git=git), req)

    epics = line(result, "epics.yaml")
    assert epics.status == "fail"
    assert epics.code == "spec-duplicate-entry-id"
    assert epics.guide == "errors/spec-duplicate-entry-id"


def test_a_line_not_built_from_a_refusal_has_no_code() -> None:
    result = run_preflight(ports(git=FakeGit()), PreflightRequest())

    assert all(item.code is None and item.guide is None for item in result.lines)


def test_ac5_finding_line_with_an_uncoded_reason_has_no_code() -> None:
    built = finding_line(CHECK_WHAT_WILL_RUN, PlanError(reason="git said no", item="x"))

    assert built.status == "fail"
    assert built.code is None
    assert built.guide is None


def test_finding_line_with_a_known_reason_carries_both() -> None:
    built = finding_line(CHECK_WHAT_WILL_RUN, PlanError(reason="duplicate entry id", item="x"))

    assert built.code == "spec-duplicate-entry-id"
    assert built.guide == "errors/spec-duplicate-entry-id"
