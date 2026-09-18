"""`fixtures/gates-repo/`: the committed repository Epic 6's scenarios are driven against.

Asserted here rather than only in the e2e suite for the reason
`test_readiness_fixture_script.py` exists: these files are *input* to a gate that takes
minutes and needs Docker, so a typo in a scenario would otherwise surface as an unexplained
timeout in `make e2e` instead of as a failed unit test naming the file.

What is checked is the contract the e2e depends on and nothing about the prose: the three
stories and their checkpoint flags, the baseline the quality gate needs in order to pass on
an untouched clone, and that every scenario parses into the shape
`infrastructure/harness/fake/scenario.py` reads — including the two that make story `1`
block and then finish, which is FR-18's whole acceptance criterion.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from orchestrator.infrastructure.harness.fake import scenario as scenarios
from tests.unit.conftest import REPO_ROOT

FIXTURE = REPO_ROOT / "fixtures" / "gates-repo"
SPEC_FOLDER = "specs/gates"
SCENARIOS = sorted((FIXTURE / ".fake-harness").rglob("*.yaml"))


def test_the_fixture_carries_the_files_a_run_against_it_needs() -> None:
    for name in ("README.md", "check.sh", "GATE_OK", f"{SPEC_FOLDER}/SPEC.md"):
        assert (FIXTURE / name).is_file(), name


def test_the_quality_gate_passes_on_an_untouched_clone() -> None:
    """`epic@1`'s `baseline` row runs the gate before the first story, with `on_fail: fail`."""
    assert (FIXTURE / "GATE_OK").read_text().strip() == "1"
    assert "GATE_OK" in (FIXTURE / "check.sh").read_text()


def test_the_three_stories_carry_the_checkpoints_this_epic_stops_at() -> None:
    stories = yaml.safe_load((FIXTURE / SPEC_FOLDER / "stories.yaml").read_text())

    assert [story["id"] for story in stories] == ["1", "2", "3"]
    assert "spec_checkpoint" not in stories[0]
    assert stories[1]["spec_checkpoint"] is True
    assert stories[2]["done_checkpoint"] is True


def test_there_is_a_scenario_directory_for_every_story() -> None:
    stories = yaml.safe_load((FIXTURE / SPEC_FOLDER / "stories.yaml").read_text())

    for story in stories:
        assert (FIXTURE / ".fake-harness" / story["id"]).is_dir(), story["id"]


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_scenario_parses_into_something_the_harness_would_act_on(path: Path) -> None:
    """`scenario.parse` never raises, so a file that failed to load would silently do
    nothing at all; a scenario that writes no file is the one shape this fixture never wants.

    Revised for stories 4-4..4-7 (2026-09-18): the root `default.yaml` serves the epic
    tail's no-story dispatches (spec-gate/gen-e2e/retro) and writes plain `files:` rather
    than a Story file — it must still write *something*, asserted the same way."""
    parsed = scenarios.load(path)

    assert parsed != scenarios.Scenario(), path.name
    if path.parent.name == ".fake-harness":
        assert parsed.files, path.name
    else:
        assert parsed.story_file is not None, path.name


def test_story_ones_two_scenarios_are_the_block_then_the_answer() -> None:
    """FR-18's acceptance criterion, in the fixture: attempt 1 blocks with a condition the
    Answer's prompt clause quotes back, attempt 2 finishes and echoes what it was asked."""
    first = scenarios.load(FIXTURE / ".fake-harness" / "1" / "attempt-1.yaml")
    second = scenarios.load(FIXTURE / ".fake-harness" / "1" / "attempt-2.yaml")

    assert first.story_file is not None
    assert "status: blocked" in first.story_file.content
    assert "Blocking condition: intent gap" in first.story_file.content
    assert first.commit is False

    assert second.story_file is not None
    assert "status: done" in second.story_file.content
    assert second.commit is True
    assert second.echo_prompt is True
    assert [spec.path for spec in second.files] == ["NOTIFY.md"]


def test_the_story_file_slugs_are_stable_so_a_test_can_name_the_path() -> None:
    # the root default.yaml (no-story dispatches, stories 4-4..4-7) carries no Story file
    slugs = {
        path.parent.name: (scenarios.load(path).story_file or scenarios.StoryFileSpec("")).slug
        for path in SCENARIOS
        if path.parent.name != ".fake-harness"
    }

    assert slugs == {"1": "notify", "2": "plan", "3": "ship"}
