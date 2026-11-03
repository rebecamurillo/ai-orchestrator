"""`ia-agents-skills/senior-session/SKILL.md` (story 2-5, Decided 1, AD-23).

The first turn's prompt is `senior-session {scope} {spec_folder} {story_id} {frame}
{park_kind} {park_reason}` then the Operator's text, so every word the senior reads beyond
those values is this file's. It states the senior's role, what each position is, what each
scope reads, which trees it may edit, that anchors change only at the Operator's explicit
request and are confirmed at the close, and that the reply file is written every turn."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SKILL = Path(__file__).resolve().parents[3] / "ia-agents-skills" / "senior-session" / "SKILL.md"
README = SKILL.parents[1] / "README.md"

POSITIONS = ("scope", "spec_folder", "story_id", "frame", "park_kind", "park_reason")
SCOPES = ("`story`", "`epic`", "`run`")
OPENING = "senior-session {scope} {spec_folder} {story_id} {frame} {park_kind} {park_reason}"


def text() -> str:
    return SKILL.read_text()


def test_the_skill_is_named_after_its_directory_and_takes_no_args() -> None:
    _, block, _ = text().split("---\n", 2)
    front = yaml.safe_load(block)

    assert front["name"] == "senior-session"
    assert "args" not in front


def test_the_senior_works_with_the_operator_at_a_stop() -> None:
    assert "You are the senior engineer working with the Operator" in text()


def test_the_opening_line_names_its_positions_in_order() -> None:
    body = text()

    assert OPENING in body
    for position in POSITIONS:
        assert f"`{position}`" in body
    assert "`-`" in body


@pytest.mark.parametrize("scope", SCOPES)
def test_each_scope_states_what_it_reads(scope: str) -> None:
    assert f"- {scope}:" in text()


def test_the_senior_edits_only_the_tree_it_runs_in_and_the_hub_root() -> None:
    body = text()

    assert "Edit only files in the directory you run in" in body
    assert "the hub root" in body


def test_anchors_change_only_at_the_operators_explicit_request() -> None:
    body = text()

    assert "only when the Operator explicitly asks" in body
    assert "confirms each anchor edit when the session closes" in body
    for anchor in ("`SPEC.md`", "`stories.yaml`", "`epics.yaml`", "`AGENTS.md`"):
        assert anchor in body


def test_the_reply_file_is_written_every_turn() -> None:
    body = text()

    assert "`.orchestrator/session/reply.md`" in body
    assert "every turn" in body


def test_the_readme_lists_the_skill() -> None:
    assert "`senior-session`" in README.read_text()
