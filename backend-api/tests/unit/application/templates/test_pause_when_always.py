"""story 4-9 (2026-09-17): pause_when: always — ALWAYS_LITERAL constant is an
architectural anchor; used in task@1 to encode an unconditional plan gate"""

from __future__ import annotations

# ALWAYS_LITERAL import is the hard TDD gate: fails if expressions.py lacks the constant
from orchestrator.application.templates.expressions import ALWAYS_LITERAL
from orchestrator.application.templates.substitute import paused
from orchestrator.application.templates.validate import validate
from tests.unit.fakes.templates import FakeTemplateVersionRepository

_MINIMAL_WITH_ALWAYS = """\
name: probe
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
steps:
  - id: build
    uses: agent
    with:
      skill: bmad-build-auto
    pause_when: always
    gate: liveness
"""


def test_pause_when_always_passes_condition_check() -> None:
    """validate() on a top-level agent step with pause_when: always returns no EXPRESSION_SYNTAX."""
    result = validate(_MINIMAL_WITH_ALWAYS, templates=FakeTemplateVersionRepository())
    syntax_errors = [e for e in result.errors if e.reason == "expression syntax"]
    assert syntax_errors == [], f"Unexpected EXPRESSION_SYNTAX errors: {syntax_errors}"


def test_paused_returns_true_for_always() -> None:
    assert paused(ALWAYS_LITERAL, {}) is True


def test_paused_returns_true_regardless_of_scope() -> None:
    assert paused(ALWAYS_LITERAL, {"story": {"spec_checkpoint": False}}) is True


def test_paused_returns_false_for_none() -> None:
    assert paused(None, {}) is False


def test_bare_field_still_works_regression() -> None:
    assert paused("story.spec_checkpoint", {"story": {"spec_checkpoint": True}}) is True
