"""`plan_check_row`'s own row: what `plan.check` needs, copied into `with_resolved` at plan
time (4.7, AD-7).

`plan_run` runs first, so its own `Run.plan_refs`/`plan_ref`/`base_branch` are exactly what
this row carries — proven here over the four shipped Templates, on the same fixture
repository `tests/unit/application/templates/test_plan_rows.py` and `test_plan_shipped.py`
use, because a plan check's own inputs are a property of the planner, not of a story's own
fixture.
"""

from __future__ import annotations

from orchestrator.application.steps.plan_check import (
    BASE_BRANCH_KEY,
    BASE_DIR_KEY,
    LIST_BRANCHES_KEY,
    PLAN_REFS_KEY,
    URL_KEY,
)
from orchestrator.application.templates.plan import plan_run
from tests.unit.application.templates import plan_fixtures as fixtures


def test_repo_init_has_no_list_files_to_check() -> None:
    """`repo-init@1` has no `for_each`: nothing for `plan.check` to re-read (AD-7)."""
    plan = plan_run(
        fixtures.tree("repo-init"),
        fixtures.inputs(),
        git=fixtures.repo_init_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    resolved = plan.rows[0].with_resolved
    assert resolved[PLAN_REFS_KEY] == {}
    assert resolved[LIST_BRANCHES_KEY] == {}
    assert resolved[BASE_DIR_KEY] == str(fixtures.BASE)
    assert resolved[URL_KEY] == fixtures.REPOSITORY.url
    assert resolved[BASE_BRANCH_KEY] == fixtures.BASE_BRANCH


def test_epic_records_its_one_list_file_on_its_own_branch() -> None:
    plan = plan_run(
        fixtures.tree("epic"),
        fixtures.epic_inputs(),
        git=fixtures.epic_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    resolved = plan.rows[0].with_resolved
    stories_path = f"{fixtures.SPEC_FOLDER}/stories.yaml"
    assert resolved[PLAN_REFS_KEY] == {stories_path: fixtures.WORK_SHA}
    assert resolved[LIST_BRANCHES_KEY] == {stories_path: fixtures.EPIC_BRANCH}


def test_initiative_records_epics_yaml_with_no_branch_and_each_stories_yaml_with_its_epics() -> (
    None
):
    """`epics.yaml` reads off the root frame, which names no branch (AD-7); each epic's
    `stories.yaml` reads off the epic frame, which does — the Initiative case the module
    docstring on `PlanReader.record` names."""
    plan = plan_run(
        fixtures.tree("initiative"),
        fixtures.initiative_inputs(),
        git=fixtures.initiative_git(stories_at=fixtures.WORK_SHA),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    resolved = plan.rows[0].with_resolved
    epics_path = f"{fixtures.INITIATIVE_FOLDER}/epics.yaml"
    epic_1_stories = f"{fixtures.INITIATIVE_FOLDER}/epic-1/stories.yaml"
    epic_2_stories = f"{fixtures.INITIATIVE_FOLDER}/epic-2/stories.yaml"

    assert resolved[PLAN_REFS_KEY] == {
        epics_path: fixtures.BASE_SHA,
        epic_1_stories: fixtures.WORK_SHA,
        epic_2_stories: fixtures.WORK_SHA,
    }
    assert resolved[LIST_BRANCHES_KEY] == {
        epics_path: None,
        epic_1_stories: fixtures.INITIATIVE_BRANCH,
        epic_2_stories: fixtures.INITIATIVE_BRANCH,
    }


def test_the_row_carries_its_own_copy_the_same_plan_refs_the_run_gets() -> None:
    """`Plan.plan_refs` (`Run.plan_refs`) and the row's own copy never disagree."""
    plan = plan_run(
        fixtures.tree("epic"),
        fixtures.epic_inputs(),
        git=fixtures.epic_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    assert plan.rows[0].with_resolved[PLAN_REFS_KEY] == plan.plan_refs
