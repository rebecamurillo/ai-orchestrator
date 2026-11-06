"""Preflight finds an agent step, and an epics loop, at any loop depth (story 2, 2026-11-06)."""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.preflight import checks
from orchestrator.application.preflight.model import CHECK_HARNESS, PreflightRequest
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.preflight.test_harness_probe_line import ctx, repo
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NESTED = Path(__file__).resolve().parents[1] / "templates" / "fixtures" / "nested"

OUTER_OVER_OTHER_FILE = """name: outer
version: 1
inputs:
  folder: { type: path, required: true }
steps:
  - id: groups
    for_each: "{{folder}}/groups.yaml"
    as: group
    steps:
      - id: epics
        for_each: "{{folder}}/epics.yaml"
        as: epic
        steps:
          - id: sync
            uses: git.sync
            gate: deterministic
"""


def tree_of(text: str) -> ResolvedTree:
    result = validate(text, templates=FakeTemplateVersionRepository())
    assert result.template is not None, result.errors
    return ResolvedTree(root=result.template)


def test_the_harness_line_is_not_skipped_for_an_agent_step_two_loops_deep() -> None:
    tree = tree_of((NESTED / "depth-2.yaml").read_text())

    line = checks.harness_probe_line(
        ctx(req=PreflightRequest(harness="claude"), repository=repo(), tree=tree)
    )

    assert line.check == CHECK_HARNESS
    assert line.text != "no agent step"
    assert line.status == "fail"


def test_an_epics_loop_inside_another_loop_is_an_epics_list() -> None:
    context = ctx(tree=tree_of(OUTER_OVER_OTHER_FILE))

    assert context.reads_epics_list is True


def test_a_tree_without_an_epics_loop_reads_no_epics_list() -> None:
    context = ctx(tree=tree_of((NESTED / "depth-1.yaml").read_text()))

    assert context.reads_epics_list is False
