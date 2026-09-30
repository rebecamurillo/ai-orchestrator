"""A root whose `only:`-filtered loop wraps a template call plans exactly one story frame.

story 4-8 (2026-09-17) landed this over the shipped `story-run@1`. Revised 2026-09-30
(Operator decision: the mono-repo `initiative` and `story-run` workflows are retired to
`templates/drafts/`, kept but not seeded) — the root is now `STORY_RUN`, a text this module
owns in the shape the retired file had, and its callee is the frozen exemplar `story@1` from
`plan_fixtures`, so no shipped file is pinned (hard rule 6). What is asserted is unchanged:
the root validates clean against its callee, and with `story_id="2"` the plan carries the
frames of story `2` and of no other entry in the list.

`test_only_selector.py` covers the `only:` filter over a leaf step; this module covers it
over a collapsed template call, which is the shape a one-story Run has.
"""

from __future__ import annotations

from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures

#: One story on its own branch: checkout, an `only:`-filtered loop calling `story@1`, push.
STORY_RUN = """
name: story-run-owned
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  story_id:    { type: string,     required: true }
  harness:     { type: enum, values: [claude, codex, local], default: claude }
  model:       { type: string,     required: false }
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
      - id: story
        uses: template
        with:
          name: story
          version: 1
          inputs:
            project: "{{project}}"
            repository: "{{repository}}"
            branch: "{{branch}}"
            spec_folder: "{{spec_folder}}"
            story: "{{story}}"
            harness: "{{harness}}"
            model: "{{model}}"
  - id: push
    uses: git.push
    with: { branch: "{{branch}}" }
    gate: deterministic
"""


def test_story_run_validates_clean() -> None:
    """The owned root validates without errors against the frozen `story@1` callee."""
    result = validate(STORY_RUN, templates=fixtures.repository_of_versions())

    assert result.template is not None, result.errors
    assert list(result.errors) == []
    assert list(result.unvalidated) == []


def test_story_run_plans_one_story_frame() -> None:
    """With `story_id="2"` the plan carries story `2` and no other entry of the list."""
    result_root = validate(STORY_RUN, templates=fixtures.repository_of_versions())
    assert result_root.template is not None, result_root.errors
    tree = ResolvedTree(root=result_root.template, callees=(fixtures.parsed("story"),))

    run_inputs = fixtures.inputs(
        values={
            "branch": fixtures.EPIC_BRANCH,
            "spec_folder": fixtures.SPEC_FOLDER,
            "story_id": "2",
        }
    )
    plan = plan_run(
        tree,
        run_inputs,
        git=fixtures.epic_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    story_ids = {row.story_id for row in plan.rows if row.story_id is not None}
    assert story_ids == {"2"}
    assert any(row.story_id == "2" for row in plan.rows)
