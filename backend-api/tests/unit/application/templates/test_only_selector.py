"""Tests for the `only:` filter in `expand_loop`.

story 4-8 (2026-09-17): only: selector in expand_loop — ONLY_NOT_IN_LIST constant is an
architectural anchor
"""

from __future__ import annotations

import pytest

from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import (
    ONLY_NOT_IN_LIST,
    PlanError,
    ResolvedTree,
)
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.templates import FakeTemplateVersionRepository

# A minimal template that exercises only: with a for_each loop.
# Includes a git.worktree step so plan_ref resolves to the epic branch sha,
# which is where epic_git() stores the stories.yaml.
HEADER = """
name: only-test
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  story_id:    { type: string,     required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic
  - id: stories
    for_each: "{{spec_folder}}/stories.yaml"
    as: story
    only: "{{story_id}}"
    steps:
      - id: sync
        uses: git.sync
        gate: deterministic
"""

#: Number of entries in plan_fixtures.EPIC_STORIES.
EPIC_STORY_COUNT = 3

HEADER_NO_ONLY = """
name: only-test-no-only
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  story_id:    { type: string,     required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic
  - id: stories
    for_each: "{{spec_folder}}/stories.yaml"
    as: story
    steps:
      - id: sync
        uses: git.sync
        gate: deterministic
"""


def make_tree(yaml_text: str) -> ResolvedTree:
    """Parse and validate inline template, return a resolved tree."""
    templates = FakeTemplateVersionRepository()
    result = validate(yaml_text, templates=templates)
    assert result.template is not None, result.errors
    return ResolvedTree(root=result.template)


def plan(tree: ResolvedTree, story_id: str) -> object:
    run_inputs = fixtures.inputs(
        values={
            "branch": fixtures.EPIC_BRANCH,
            "spec_folder": fixtures.SPEC_FOLDER,
            "story_id": story_id,
        }
    )
    return plan_run(
        tree,
        run_inputs,
        git=fixtures.epic_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def test_only_selector_plans_single_matching_frame() -> None:
    """story 4-8 (2026-09-17): only: selector plans a single matching frame."""
    tree = make_tree(HEADER)
    result = plan(tree, "2")
    story_ids = {r.story_id for r in result.rows if r.story_id is not None}  # type: ignore[union-attr]
    assert story_ids == {"2"}


def test_only_selector_raises_plan_error_on_no_match() -> None:
    """story 4-8 (2026-09-17): only: selector raises PlanError when no entry matches."""
    tree = make_tree(HEADER)
    with pytest.raises(PlanError) as raised:
        plan(tree, "99")
    assert raised.value.reason == ONLY_NOT_IN_LIST


def test_for_each_without_only_plans_all_frames() -> None:
    """story 4-8 (2026-09-17): for_each without only: still plans all frames (regression)."""
    tree = make_tree(HEADER_NO_ONLY)
    result = plan(tree, "2")
    story_ids = {r.story_id for r in result.rows if r.story_id is not None}  # type: ignore[union-attr]
    assert len(story_ids) == EPIC_STORY_COUNT
