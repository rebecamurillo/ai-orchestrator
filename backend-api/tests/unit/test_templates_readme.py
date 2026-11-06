"""`templates/README.md`'s three examples are real templates (story 8, 2026-11-06, BR-16, AC-13).

The README is documentation the owner copies into the operator folder, so the examples must
validate and plan over the repository's own list-file fixtures. Expected counts come from
those fixture files, never from numbers written here.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from orchestrator.application.templates.model import ParsedTemplate
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.conftest import REPO_ROOT
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

README = REPO_ROOT / "templates" / "README.md"
FIXTURES = REPO_ROOT / "fixtures"
READINESS_STORIES = "specs/readiness/stories.yaml"
HUB_FOLDER = "initiatives/demo"
EXAMPLE_COUNT = 3
NAMES = ("example-depth-0", "example-depth-1", "example-depth-2")
BRANCH = "example/check"


def yaml_fences() -> list[str]:
    fences = re.findall(r"^```(\w*)\n(.*?)^```", README.read_text(), re.M | re.S)
    return [body for language, body in fences if language == "yaml"]


def examples() -> dict[str, str]:
    return {yaml.safe_load(body)["name"]: body for body in yaml_fences()}


def depth(steps: list[dict[str, Any]]) -> int:
    inner = [depth(step["steps"]) + 1 for step in steps if "for_each" in step]
    return max(inner, default=0)


def parsed(name: str) -> ParsedTemplate:
    result = validate(examples()[name], templates=FakeTemplateVersionRepository())
    assert result.template is not None, result.errors
    return result.template


def agent_rows(name: str, remote: FakeGit, values: dict[str, str]):
    plan = plan_run(
        ResolvedTree(root=parsed(name)),
        fixtures.inputs(values=values),
        git=remote,
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    return [row for row in plan.rows if row.kind == "agent"]


def remote(files: dict[str, str]) -> FakeGit:
    return FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA},
        files={(fixtures.BASE_SHA, path): text for path, text in files.items()},
        listings={},
    )


def fixture_text(relative: str) -> str:
    return (FIXTURES / relative).read_text()


def test_the_readme_holds_exactly_the_three_examples() -> None:
    assert len(yaml_fences()) == EXAMPLE_COUNT
    assert sorted(examples()) == sorted(NAMES)
    assert all("uses: template" not in body for body in yaml_fences())


@pytest.mark.parametrize("name", NAMES)
def test_each_example_validates(name: str) -> None:
    result = validate(examples()[name], templates=FakeTemplateVersionRepository())
    assert not result.errors
    assert result.template is not None


def test_the_examples_nest_zero_one_and_two_loops() -> None:
    depths = {name: depth(yaml.safe_load(examples()[name])["steps"]) for name in NAMES}
    assert depths == {"example-depth-0": 0, "example-depth-1": 1, "example-depth-2": 2}


def test_the_declared_inputs_loop_ids_and_bind() -> None:
    documents = {name: yaml.safe_load(examples()[name]) for name in NAMES}
    assert "spec_folder" in documents["example-depth-0"]["inputs"]
    assert "spec_folder" in documents["example-depth-1"]["inputs"]
    deep = documents["example-depth-2"]
    assert "initiative_folder" in deep["inputs"]
    outer = next(step for step in deep["steps"] if "for_each" in step)
    assert outer["id"] == "epics"
    assert outer["steps"][0]["id"] == "stories"
    assert outer["bind"] == {"spec_folder": "{{initiative_folder}}/{{epic.spec_folder}}"}


def test_depth_zero_plans_its_agent_row_with_the_spec_folder() -> None:
    rows = agent_rows(
        "example-depth-0",
        remote({READINESS_STORIES: fixture_text(f"readiness-repo/{READINESS_STORIES}")}),
        {"spec_folder": "specs/readiness", "branch": BRANCH},
    )
    assert rows
    assert all(row.with_resolved["spec_folder"] == "specs/readiness" for row in rows)


def test_depth_one_plans_one_agent_row_per_story() -> None:
    text = fixture_text(f"readiness-repo/{READINESS_STORIES}")
    rows = agent_rows(
        "example-depth-1",
        remote({READINESS_STORIES: text}),
        {"spec_folder": "specs/readiness", "branch": BRANCH},
    )
    stories = yaml.safe_load(text)
    assert [row.with_resolved["story_id"] for row in rows] == [str(s["id"]) for s in stories]
    assert all(row.with_resolved["spec_folder"] == "specs/readiness" for row in rows)


def test_depth_two_plans_one_agent_row_per_epic_story_pair() -> None:
    files = {f"{HUB_FOLDER}/epics.yaml": fixture_text("hub-repo/initiatives/demo/epics.yaml")}
    expected: list[tuple[str, str]] = []
    for epic in yaml.safe_load(files[f"{HUB_FOLDER}/epics.yaml"]):
        folder = f"{HUB_FOLDER}/{epic['spec_folder']}"
        text = fixture_text(f"hub-repo/{folder}/stories.yaml")
        files[f"{folder}/stories.yaml"] = text
        expected += [(folder, str(story["id"])) for story in yaml.safe_load(text)]

    rows = agent_rows(
        "example-depth-2", remote(files), {"initiative_folder": HUB_FOLDER, "branch": BRANCH}
    )

    assert [
        (row.with_resolved["spec_folder"], row.with_resolved["story_id"]) for row in rows
    ] == expected
