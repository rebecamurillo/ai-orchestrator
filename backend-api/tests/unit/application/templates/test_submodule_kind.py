"""The `git.submodule` kind as the registry's consumers see it: validate, plan, graph (AD-9).

`KIND_META` is the one enumeration of kinds there is, and the validator, the planner and the
graph all read it rather than listing kinds of their own — so a new row flows through all
three without any of them naming it. This module is that claim, checked for the hub-Run
workflow's kind, plus the one thing the key table *does* say about it by name: the two forms
are told apart by their keys, and a `with` that is neither is a validation error (spine
"Template DSL v1 keys", ratified 2026-09-23).

The Templates here are the tests' own fixtures, written for the rule. They are never the
shipped `templates/*.yaml`, which are exemplars and evolve freely (hard rule 6).
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.graph import build_template_graph
from orchestrator.application.steps import KIND_META, SUBMODULE_CHECKOUT_KEYS
from orchestrator.application.templates.model import (
    INVALID_SUBMODULE_FORM,
    ParsedTemplate,
    ValidationError,
)
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

KIND = "git.submodule"
INTEGRATION = "integration"
WORKDIR = "repos/member"
MEMBER_BASE = "main"
BASE_BRANCH = fixtures.BASE_BRANCH
REF = fixtures.BASE_SHA

HUB = """name: hubbing
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  workdir:     { type: string,     required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}", mode: attach }
    gate: deterministic
  - id: members
    uses: git.submodule
    gate: deterministic
  - id: member-branch
    uses: git.submodule
    with: { workdir: "{{workdir}}", branch: "{{branch}}", base: "main" }
    gate: deterministic
  - id: push
    uses: git.push
    with: { branch: "{{branch}}" }
    gate: deterministic
"""

#: The same file with the update form written out rather than left bare.
EXPLICIT_UPDATE = HUB.replace(
    """  - id: members
    uses: git.submodule
    gate: deterministic
""",
    """  - id: members
    uses: git.submodule
    with: { update: true }
    gate: deterministic
""",
)

#: The same file without `mode: attach`, so the Run's own branch is allocated an ordinal and
#: the submodule row's exemption from that is visible (AD-7).
ALLOCATING = HUB.replace(", mode: attach }", " }")

#: The same file with a `with` key the kind does not admit.
UNKNOWN_WITH = HUB.replace("{ workdir:", "{ folder:")

#: The two shapes the key table rejects by name.
BOTH_FORMS = HUB.replace(
    """    with: { workdir: "{{workdir}}", branch: "{{branch}}", base: "main" }""",
    """    with: { update: true, workdir: "{{workdir}}", branch: "{{branch}}" }""",
)
WORKDIR_WITHOUT_BRANCH = HUB.replace(
    """    with: { workdir: "{{workdir}}", branch: "{{branch}}", base: "main" }""",
    """    with: { workdir: "{{workdir}}" }""",
)

#: The same file with no `gate` on the update row — which must stay reported (NFR-2).
GATELESS = HUB.replace(
    """  - id: members
    uses: git.submodule
    gate: deterministic
""",
    """  - id: members
    uses: git.submodule
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
        fixtures.inputs(values={"branch": INTEGRATION, "workdir": WORKDIR}),
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
    assert meta.with_keys == frozenset({"update", "workdir", "branch", "base"})


def test_the_two_forms_partition_the_kinds_with_keys() -> None:
    """Derived, not restated: the checkout form is everything the kind admits but `update`,
    so the key table and the form check cannot drift apart."""
    assert SUBMODULE_CHECKOUT_KEYS == KIND_META[KIND].with_keys - {"update"}


# --- what the validator accepts ---------------------------------------------------------


def test_a_template_naming_both_forms_of_the_kind_validates_clean() -> None:
    assert errors(HUB) == []


def test_the_explicit_update_key_validates_too() -> None:
    assert errors(EXPLICIT_UPDATE) == []


def test_nothing_of_a_declared_submodule_row_is_left_unvalidated() -> None:
    assert validate(HUB, templates=_stored()).unvalidated == ()


def test_a_submodule_row_with_no_gate_is_still_reported() -> None:
    """NFR-2: a kind's `gate_default` is never a fallback for a gate a Template omitted."""
    assert validate(GATELESS, templates=_stored()).unvalidated == ("members",)


def test_a_with_key_the_kind_does_not_admit_is_rejected() -> None:
    assert [record.reason for record in errors(UNKNOWN_WITH)] == ["unknown key"]


def test_the_keys_of_both_forms_together_are_a_validation_error() -> None:
    assert [record.reason for record in errors(BOTH_FORMS)] == [INVALID_SUBMODULE_FORM]


def test_a_workdir_without_a_branch_is_a_validation_error() -> None:
    assert [record.reason for record in errors(WORKDIR_WITHOUT_BRANCH)] == [INVALID_SUBMODULE_FORM]


# --- what the planner does with it ------------------------------------------------------


def test_the_update_row_carries_nothing_but_the_kinds_own_timeout() -> None:
    members = row(planned(HUB), "members")

    assert members.kind == KIND
    assert members.with_resolved == {"timeout_min": KIND_META[KIND].timeout_default_min}


def test_the_checkout_row_carries_the_resolved_workdir_branch_and_base() -> None:
    member = row(planned(HUB), "member-branch")

    assert member.with_resolved == {
        "workdir": WORKDIR,
        "branch": INTEGRATION,
        "base": MEMBER_BASE,
        "timeout_min": KIND_META[KIND].timeout_default_min,
    }


def test_the_branch_is_taken_by_its_exact_name_never_allocated() -> None:
    """AD-7 exempts a `git.submodule` branch from allocation: it lives in the submodule's own
    repository, which the allocator — which asks the *Run's* origin — cannot reason about.

    Asserted on the fixture whose `git.worktree` is *not* `mode: attach`, so the Run's own
    branch does get an ordinal and the exemption is a fact about the kind rather than about
    the frame: the push row takes `integration-1`, the submodule row keeps `integration`."""
    plan = planned(ALLOCATING)

    assert row(plan, "member-branch").with_resolved["branch"] == INTEGRATION
    assert row(plan, "push").with_resolved["branch"] != INTEGRATION


def test_both_rows_are_planned_deterministic_and_queued_like_every_other_git_row() -> None:
    plan = planned(HUB)

    for path in ("members", "member-branch"):
        assert row(plan, path).gate == "deterministic"
        assert row(plan, path).status == "planned"


def test_the_submodule_rows_sit_between_the_checkout_and_the_push() -> None:
    """Traversal order with a dense `seq` (AD-7) — the fixture's own order, not a shipped
    file's."""
    plan = planned(HUB)

    assert [entry.path for entry in plan.rows if entry.kind != "plan.check"] == [
        "checkout",
        "members",
        "member-branch",
        "push",
    ]


# --- what the graph does with it --------------------------------------------------------


def test_the_graph_holds_a_node_for_each_submodule_row_wired_to_its_neighbours() -> None:
    graph = build_template_graph(parsed(HUB))
    ids = {node.id for node in graph.nodes}
    edges = {(edge.from_id, edge.to_id) for edge in graph.edges}

    assert {"members", "member-branch"} <= ids
    assert ("checkout", "members") in edges
    assert ("members", "member-branch") in edges
    assert ("member-branch", "push") in edges


def test_the_submodule_nodes_are_not_unvalidated() -> None:
    graph = build_template_graph(parsed(HUB))
    gates = {node.id: node.gate for node in graph.nodes}

    assert gates["members"] == "deterministic"
    assert gates["member-branch"] == "deterministic"
