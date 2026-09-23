"""The `git.merge` kind as the registry's consumers see it: validate, plan, graph (AD-9).

`KIND_META` is the one enumeration of kinds there is, and the validator, the planner and the
graph all read it rather than listing kinds of their own — so a new row is supposed to flow
through all three without any of them naming it. This module is that claim, checked: a
Template carrying a `git.merge` step validates with nothing unvalidated, plans into a row
whose `from` is resolved and whose timeout is the kind's own, and builds a graph node.

The Templates here are the tests' own fixtures, written for the rule. They are never the
shipped `templates/*.yaml`, which are exemplars and evolve freely (hard rule 6).
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.graph import build_template_graph
from orchestrator.application.steps import KIND_META
from orchestrator.application.templates.model import ParsedTemplate, ValidationError
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

KIND = "git.merge"
INTEGRATION = "develop"
FROM_BRANCH = "feat/epic-1"
BASE_BRANCH = fixtures.BASE_BRANCH
REF = fixtures.BASE_SHA

MERGING = """name: merging
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  from_branch: { type: string,     required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}", mode: attach }
    gate: deterministic
  - id: merge
    uses: git.merge
    with: { from: "{{from_branch}}" }
    gate: deterministic
  - id: push
    uses: git.push
    with: { branch: "{{branch}}" }
    gate: deterministic
"""

#: The same file with a `with` key the kind does not admit.
UNKNOWN_WITH = MERGING.replace("{ from:", "{ into:")

#: The same file with no `gate` on the merge row — which must stay reported (NFR-2).
GATELESS = MERGING.replace(
    """  - id: merge
    uses: git.merge
    with: { from: "{{from_branch}}" }
    gate: deterministic
""",
    """  - id: merge
    uses: git.merge
    with: { from: "{{from_branch}}" }
""",
)


def _stored() -> FakeTemplateVersionRepository:
    return FakeTemplateVersionRepository([])


def errors(text: str) -> list[ValidationError]:
    return list(validate(text, templates=_stored()).errors)


def parsed(text: str) -> ParsedTemplate:
    result = validate(text, templates=_stored())
    assert result.template is not None, result.errors
    return result.template


def planned(text: str) -> Plan:
    return plan_run(
        ResolvedTree(root=parsed(text), callees=()),
        fixtures.inputs(values={"branch": INTEGRATION, "from_branch": FROM_BRANCH}),
        git=FakeGit(refs={BASE_BRANCH: REF, INTEGRATION: REF}, files={}, listings={}),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def row(plan: Plan, path: str) -> Any:
    return next(entry for entry in plan.rows if entry.path == path)


# --- the registry row itself ------------------------------------------------------------


def test_the_kind_is_a_template_writable_deterministic_row() -> None:
    meta = KIND_META[KIND]

    assert meta.gate_default == "deterministic"
    assert meta.planner_only is False
    assert meta.with_keys == frozenset({"from"})


# --- what the validator accepts ---------------------------------------------------------


def test_a_template_naming_the_kind_validates_clean() -> None:
    assert errors(MERGING) == []


def test_nothing_of_a_declared_merge_row_is_left_unvalidated() -> None:
    assert validate(MERGING, templates=_stored()).unvalidated == ()


def test_a_merge_row_with_no_gate_is_still_reported() -> None:
    """NFR-2: a kind's `gate_default` is never a fallback for a gate a Template omitted."""
    assert validate(GATELESS, templates=_stored()).unvalidated == ("merge",)


def test_a_with_key_the_kind_does_not_admit_is_rejected() -> None:
    assert [record.reason for record in errors(UNKNOWN_WITH)] == ["unknown key"]


# --- what the planner does with it ------------------------------------------------------


def test_the_row_carries_the_resolved_source_branch_and_the_kinds_own_timeout() -> None:
    merge = row(planned(MERGING), "merge")

    assert merge.kind == KIND
    assert merge.with_resolved == {
        "from": FROM_BRANCH,
        "timeout_min": KIND_META[KIND].timeout_default_min,
    }


def test_the_row_is_planned_deterministic_and_queued_like_every_other_git_row() -> None:
    merge = row(planned(MERGING), "merge")

    assert merge.gate == "deterministic"
    assert merge.status == "planned"


def test_the_merge_row_sits_between_the_checkout_and_the_push() -> None:
    """Traversal order with a dense `seq` (AD-7) — the fixture's own order, not a shipped
    file's."""
    plan = planned(MERGING)

    assert [entry.path for entry in plan.rows if entry.kind != "plan.check"] == [
        "checkout",
        "merge",
        "push",
    ]


# --- what the graph does with it --------------------------------------------------------


def test_the_graph_holds_a_node_for_the_merge_row_wired_to_its_neighbours() -> None:
    graph = build_template_graph(parsed(MERGING))
    ids = {node.id for node in graph.nodes}

    assert "merge" in ids
    assert ("checkout", "merge") in {(edge.from_id, edge.to_id) for edge in graph.edges}
    assert ("merge", "push") in {(edge.from_id, edge.to_id) for edge in graph.edges}


def test_the_merge_node_is_not_unvalidated() -> None:
    graph = build_template_graph(parsed(MERGING))

    assert next(node for node in graph.nodes if node.id == "merge").gate == "deterministic"
