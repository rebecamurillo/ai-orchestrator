"""Planning a loop inside a loop with `bind` (story 2, 2026-11-06, AD-15 amendment)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.templates.model import ParsedTemplate
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ONLY_NOT_IN_LIST, PlanError, ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NESTED = Path(__file__).resolve().parent / "fixtures" / "nested"
FOLDER = "initiatives/x"

EPICS = """
- id: e1
  title: First
  branch: feat/x
  spec_folder: e1
- id: e2
  title: Second
  branch: feat/x
  spec_folder: e2
"""

STORIES = """
- id: "1"
  title: One
  description: first
- id: "2"
  title: Two
  description: second
"""


def parsed(name: str) -> ParsedTemplate:
    result = validate(
        (NESTED / f"{name}.yaml").read_text(), templates=FakeTemplateVersionRepository()
    )
    assert result.template is not None, result.errors
    return result.template


def git(stories: dict[str, str] | None = None) -> FakeGit:
    files = {(fixtures.BASE_SHA, f"{FOLDER}/epics.yaml"): EPICS}
    for epic in ("e1", "e2"):
        text = (stories or {}).get(epic, STORIES)
        files[(fixtures.BASE_SHA, f"{FOLDER}/{epic}/stories.yaml")] = text
    return FakeGit(refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files=files, listings={})


def plan(name: str, remote: FakeGit, values: dict[str, str]):
    return plan_run(
        ResolvedTree(root=parsed(name)),
        fixtures.inputs(values=values),
        git=remote,
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def agent_rows(name: str, remote: FakeGit, values: dict[str, str]):
    return [row for row in plan(name, remote, values).rows if row.kind == "agent"]


def test_a_depth_two_plan_has_one_row_per_epic_story_step_in_list_order() -> None:
    rows = agent_rows("depth-2", git(), {"initiative_folder": FOLDER})

    assert [row.path for row in rows] == [
        "epics[0].stories[0].build",
        "epics[0].stories[1].build",
        "epics[1].stories[0].build",
        "epics[1].stories[1].build",
    ]
    assert rows[0].label == "epic 1 · story 1 · build"


def test_the_bound_spec_folder_is_resolved_per_epic_as_a_string() -> None:
    rows = agent_rows("depth-2", git(), {"initiative_folder": FOLDER})

    folders = [row.with_resolved["spec_folder"] for row in rows]
    assert folders == [f"{FOLDER}/e1"] * 2 + [f"{FOLDER}/e2"] * 2
    assert all(isinstance(folder, str) for folder in folders)


def test_a_depth_one_plan_still_plans() -> None:
    remote = FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA},
        files={(fixtures.BASE_SHA, f"{FOLDER}/stories.yaml"): STORIES},
        listings={},
    )

    rows = agent_rows("depth-1", remote, {"spec_folder": FOLDER})

    assert [row.path for row in rows] == ["stories[0].build", "stories[1].build"]


def test_a_depth_zero_plan_still_plans() -> None:
    rows = agent_rows("depth-0", git(), {})

    assert [row.path for row in rows] == ["build"]


def test_an_inner_only_that_one_outer_item_lacks_refuses_the_plan() -> None:
    text = (
        (NESTED / "depth-2.yaml")
        .read_text()
        .replace("        as: story\n", "        as: story\n        only: '2'\n")
    )
    result = validate(text, templates=FakeTemplateVersionRepository())
    assert result.template is not None, result.errors
    only_one = {"e2": '- id: "1"\n  title: One\n  description: first\n'}

    with pytest.raises(PlanError) as raised:
        plan_run(
            ResolvedTree(root=result.template),
            fixtures.inputs(values={"initiative_folder": FOLDER}),
            git=git(only_one),
            base_dir=fixtures.BASE,
            bmad_version=fixtures.BMAD_VERSION,
        )

    assert raised.value.reason == ONLY_NOT_IN_LIST
