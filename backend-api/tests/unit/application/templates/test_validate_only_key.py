"""Tests for validate.py acceptance and expression check of `only:` on for_each.

story 4-8 (2026-09-17): validate.py accepts only: on for_each — outer scope, not item scope
"""

from __future__ import annotations

from orchestrator.application.templates.model import UNBOUND_VARIABLE, UNKNOWN_KEY
from orchestrator.application.templates.validate import validate
from tests.unit.fakes.templates import FakeTemplateVersionRepository

# A template with only: bound to a declared input (story_id in outer scope)
TEMPLATE_WITH_ONLY = """
name: with-only
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  story_id:    { type: string,     required: true }
steps:
  - id: stories
    for_each: "{{spec_folder}}/stories.yaml"
    as: story
    only: "{{story_id}}"
    steps:
      - id: sync
        uses: git.sync
        gate: deterministic
"""

# A template with only: bound to an undeclared variable
TEMPLATE_ONLY_UNBOUND = """
name: with-only-unbound
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  spec_folder: { type: path,       required: true }
steps:
  - id: stories
    for_each: "{{spec_folder}}/stories.yaml"
    as: story
    only: "{{undeclared}}"
    steps:
      - id: sync
        uses: git.sync
        gate: deterministic
"""


def test_for_each_with_only_passes_validation() -> None:
    """story 4-8 (2026-09-17): for_each with only: bound to declared input passes."""
    templates = FakeTemplateVersionRepository()
    result = validate(TEMPLATE_WITH_ONLY, templates=templates)
    reasons = [e.reason for e in result.errors]
    assert UNKNOWN_KEY not in reasons
    assert UNBOUND_VARIABLE not in reasons
    assert result.template is not None


def test_for_each_with_only_rejects_unknown_expression() -> None:
    """story 4-8 (2026-09-17): for_each with only: bound to undeclared variable fails."""
    templates = FakeTemplateVersionRepository()
    result = validate(TEMPLATE_ONLY_UNBOUND, templates=templates)
    reasons = [e.reason for e in result.errors]
    assert UNBOUND_VARIABLE in reasons
