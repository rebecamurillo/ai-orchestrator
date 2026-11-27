"""The `git.branch_delete` kind as the registry's consumers see it (epic 3 story 4, AC1-AC2).

The Template is this test's own fixture, never a shipped `templates/*.yaml` (hard rule 6).
"""

from __future__ import annotations

from orchestrator.application.graph import build_template_graph
from orchestrator.application.steps import KIND_META, KindMeta
from orchestrator.application.steps.git_branch_delete import GitBranchDeleteExecutor
from orchestrator.application.steps.registry import executor_for
from orchestrator.application.templates.validate import validate
from tests.unit.fakes.templates import FakeTemplateVersionRepository

KIND = "git.branch_delete"

DELETING = """name: deleting
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{base_branch}}", mode: attach }
    gate: deterministic
  - id: delete
    uses: git.branch_delete
    with: { branch: "spec/demo" }
    gate: deterministic
"""

UNKNOWN_WITH = DELETING.replace('{ branch: "spec/demo" }', '{ ref: "spec/demo" }')


def check(text: str):  # type: ignore[no-untyped-def]
    return validate(text, templates=FakeTemplateVersionRepository([]))


def test_the_registry_row() -> None:
    assert KIND_META[KIND] == KindMeta("deterministic", 5, frozenset({"branch"}))
    assert isinstance(executor_for(KIND), GitBranchDeleteExecutor)


def test_a_template_naming_the_kind_validates_clean() -> None:
    result = check(DELETING)

    assert list(result.errors) == []
    assert result.unvalidated == ()


def test_an_unknown_with_key_is_rejected() -> None:
    assert [record.reason for record in check(UNKNOWN_WITH).errors] == ["unknown key"]


def test_the_graph_holds_one_deterministic_node() -> None:
    template = check(DELETING).template
    assert template is not None

    graph = build_template_graph(template)
    nodes = [node for node in graph.nodes if node.id == "delete"]

    assert len(nodes) == 1
    assert nodes[0].gate == "deterministic"
    assert nodes[0].agent is False
    assert nodes[0].human is False
