"""`ia-agents-skills/staged-plan/SKILL.md` requires a test-impact search before the spec is
written (SPEC CAP-6, story 1-3): every test lane, the `test.fixme` and skipped e2e specs
included, and the existing tests the story contradicts recorded under `## Do not touch`.
Read the way `test_operator_skills_contract.py` reads skills. No shipped template is pinned."""

from __future__ import annotations

import re
from pathlib import Path

#: `tests/unit/test_staged_plan_test_impact.py` -> the repository root.
SKILL = Path(__file__).resolve().parents[3] / "ia-agents-skills" / "staged-plan" / "SKILL.md"

#: Where the planner finds a target repository's own lanes. The skill runs against other
#: repositories, so it must say how to find their lanes rather than name this one's.
LANE_SOURCES = ("agents.md", "config", "package scripts")

#: This repository's own layout, which a skill for other repositories must not assume.
THIS_REPOSITORYS_LANES = ("backend-api/tests", "web-client/tests")

#: Kinds of change the search must look for, named in the instruction.
CHANGE_KINDS = ("labels", "identifiers", "routes", "exports", "enum", "hidden")


def investigation() -> str:
    """Step 2, where the search lives: from its heading up to the spec-writing step."""
    body = SKILL.read_text()
    start = body.index("## 2. Investigate, narrowly")
    end = body.index("## 3. Write the spec")
    return body[start:end].lower()


def test_the_search_runs_in_step_two_before_the_spec_is_written() -> None:
    assert "test-impact search" in investigation()


def test_the_search_finds_every_lane_of_the_repository_it_plans_for() -> None:
    section = investigation()
    assert "every one this repository has" in section
    for source in LANE_SOURCES:
        assert source in section, source
    assert "e2e" in section


def test_the_search_assumes_no_layout_of_this_repository() -> None:
    section = investigation()
    for lane in THIS_REPOSITORYS_LANES:
        assert lane not in section, lane


def test_the_search_names_fixme_and_skipped_specs() -> None:
    section = investigation()
    assert "test.fixme" in section
    assert "test.skip" in section


def test_the_search_covers_what_the_story_changes() -> None:
    section = investigation()
    for kind in CHANGE_KINDS:
        assert kind in section, kind


def test_contradicted_tests_are_recorded_under_do_not_touch() -> None:
    section = investigation()
    assert "contradict" in section
    assert "## do not touch" in section


def test_the_plan_records_the_search_even_when_nothing_is_found() -> None:
    section = investigation()
    assert "none found" in section


def test_the_skill_adds_no_marker_status() -> None:
    statuses = set(re.findall(r"status: ([\w-]+)", SKILL.read_text()))
    assert statuses == {"done", "blocked", "ready-for-dev"}
