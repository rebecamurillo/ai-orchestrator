"""`git.worktree` with `mode: attach`: the one checkout that is not given a fresh branch.

AD-7 allocates every declared branch the first free ordinal of it, so two Runs of one
Template never meet on one branch. A merge Run has to meet them: it works *on* a
repository's shared integration branch, by its exact name, at its origin head (spine AD-7
and AD-14, amended 2026-09-23 by the multi-repository initiative). This module is that
exemption, from the two sides that decide it — what the validator accepts, and what the
planner does with what it accepted.

The Templates here are the tests' own fixtures, written for the rule. They are never the
shipped `templates/*.yaml`, which are exemplars and evolve freely (hard rule 6).
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.templates.model import ParsedTemplate, ValidationError
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: The shared integration branch an attach checkout names, and the branch a callee of the
#: mixed Template declares for itself — which is still allocated an ordinal.
INTEGRATION = "feat/integration"
WORKED = "feat/work"
FIRST_ORDINAL = f"{WORKED}-1"

BASE_BRANCH = fixtures.BASE_BRANCH
REF = fixtures.BASE_SHA
HEAD_SHA = fixtures.WORK_SHA

HEADER = """name: {name}
version: 1
inputs:
  project:     {{ type: project,    required: true }}
  repository:  {{ type: repository, required: true }}
  base_branch: {{ type: string,     required: true }}
  branch:      {{ type: string,     required: true }}
steps:
"""

#: The rule's own Template: a checkout that attaches, and a push naming the same branch.
ATTACHING = (
    HEADER.format(name="attaching")
    + """  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}", mode: attach }
    gate: deterministic
  - id: push
    uses: git.push
    with: { branch: "{{branch}}" }
    gate: deterministic
"""
)

#: The same file without the mode: the ordinary allocation, for the contrast.
ALLOCATING = ATTACHING.replace(", mode: attach }", " }").replace("attaching", "allocating")

#: A `mode` that is not the one token. The validator checks `with` **keys**, not their
#: values, so this file is valid and the planner is what decides it is not an attach.
OTHER_MODE = ATTACHING.replace("mode: attach", "mode: detach").replace("attaching", "other-mode")

#: An attach checkout that names no branch at all: nothing to attach to, nothing to record.
NAMELESS = (
    HEADER.format(name="nameless")
    + """  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", mode: attach }
    gate: deterministic
"""
)

#: A `with` key no kind accepts, to prove the acceptance of `mode` is narrow.
UNKNOWN_WITH = ATTACHING.replace("mode: attach", "mood: attach").replace("attaching", "unknown")

#: The callee of `MIXED`: an ordinary checkout, allocated an ordinal as any other is.
WORKER = (
    HEADER.format(name="worker")
    + """  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic
"""
)

#: One plan holding both: the root attaches to the integration branch and the callee is
#: given a fresh name of its own.
MIXED = (
    HEADER.format(name="mixed")
    + """  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}", mode: attach }
    gate: deterministic
  - id: sub
    uses: template
    with:
      name: worker
      version: 1
      inputs:
        project: "{{project}}"
        repository: "{{repository}}"
        base_branch: "{{base_branch}}"
        branch: "WORKED_BRANCH"
""".replace("WORKED_BRANCH", WORKED)
)


def errors(text: str) -> list[ValidationError]:
    result = validate(text, templates=_stored())
    return list(result.errors)


def parsed(text: str) -> ParsedTemplate:
    result = validate(text, templates=_stored())
    assert result.template is not None, result.errors
    return result.template


def _stored() -> FakeTemplateVersionRepository:
    """The one callee `MIXED` pins, as saving it would have recorded it (AD-15)."""
    return FakeTemplateVersionRepository(
        [TemplateVersion(name="worker", version=1, yaml=WORKER, hash="sha", calls=())]
    )


def planned(
    text: str,
    *,
    callees: tuple[ParsedTemplate, ...] = (),
    git: FakeGit | None = None,
    branch: str = INTEGRATION,
) -> Plan:
    """One plan of a fixture Template, over a remote holding only what the test said."""
    tree = ResolvedTree(root=parsed(text), callees=callees)
    return plan_run(
        tree,
        fixtures.inputs(values={"branch": branch}),
        git=git or FakeGit(refs={BASE_BRANCH: REF}, files={}, listings={}),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def row(plan: Plan, path: str) -> Any:
    return next(entry for entry in plan.rows if entry.path == path)


def holding_the_branch() -> FakeGit:
    """A remote that already holds the integration branch, at its own head."""
    return FakeGit(refs={BASE_BRANCH: REF, INTEGRATION: HEAD_SHA}, files={}, listings={})


# --- what the validator accepts ---------------------------------------------------------------


def test_mode_is_accepted_on_a_worktree_step() -> None:
    assert errors(ATTACHING) == []


def test_an_unknown_with_key_on_a_worktree_step_is_still_rejected() -> None:
    """The acceptance is one key wide: `mood` is not `mode`."""
    assert [record.reason for record in errors(UNKNOWN_WITH)] == ["unknown key"]


def test_the_value_of_mode_is_free_form_at_validation_time() -> None:
    """`keys.py` checks `with` keys, not their values, for every kind but a `template` call."""
    assert errors(OTHER_MODE) == []


# --- what the planner does with it --------------------------------------------------------------


def test_an_attach_checkout_keeps_the_branch_the_template_declared() -> None:
    plan = planned(ATTACHING, git=holding_the_branch())

    assert row(plan, "checkout").with_resolved["branch"] == INTEGRATION


def test_the_same_template_without_the_mode_is_given_a_fresh_ordinal() -> None:
    """The contrast: allocation is still the rule, and attach is still the exception."""
    plan = planned(ALLOCATING, git=holding_the_branch())

    assert row(plan, "checkout").with_resolved["branch"] == f"{INTEGRATION}-1"


def test_a_mode_that_is_not_the_token_allocates_like_any_other_checkout() -> None:
    plan = planned(OTHER_MODE, git=holding_the_branch())

    assert row(plan, "checkout").with_resolved["branch"] == f"{INTEGRATION}-1"


def test_the_plan_maps_an_attach_branch_to_itself() -> None:
    """`Plan.branches` is where pre-flight (AD-14) and the partition key (AD-12) read the
    declared name back, so an attach branch has to be in it — as its own name."""
    assert planned(ATTACHING, git=holding_the_branch()).branches == {INTEGRATION: INTEGRATION}


def test_the_origin_is_never_asked_for_an_ordinal_of_an_attach_branch() -> None:
    """The allocator is bypassed, not merely overruled: no candidate is looked up."""
    git = holding_the_branch()

    planned(ATTACHING, git=git)

    assert all(ref != f"{INTEGRATION}-1" for _, ref in git.called("ls_remote"))


def test_an_attach_row_keeps_the_base_the_template_wrote_when_the_origin_holds_it() -> None:
    """There is no fresh branch to start somewhere else: the executor checks the declared
    branch out, so the row's `base` is left as written (AD-7)."""
    plan = planned(ATTACHING, git=holding_the_branch())

    assert row(plan, "checkout").with_resolved["base"] == BASE_BRANCH


def test_an_attach_branch_the_origin_does_not_hold_yet_is_planned_from_the_base() -> None:
    """Dispatch normally pre-creates the integration branch; a planner that needed it to
    exist would refuse a Run the Operator could still start."""
    plan = planned(ATTACHING)

    assert plan.plan_ref == REF
    assert row(plan, "checkout").with_resolved == {
        "base": BASE_BRANCH,
        "branch": INTEGRATION,
        "mode": "attach",
        "timeout_min": 5,
    }


def test_a_push_row_of_an_attach_frame_pushes_the_declared_branch() -> None:
    plan = planned(ATTACHING, git=holding_the_branch())

    assert row(plan, "push").with_resolved["branch"] == INTEGRATION


def test_an_attach_checkout_that_names_no_branch_records_nothing() -> None:
    """A checkout with nothing to attach to: no name to carry and no branch to map."""
    plan = planned(NAMELESS)

    assert plan.branches == {}
    assert row(plan, "checkout").with_resolved["base"] == BASE_BRANCH


# --- one plan holding both ----------------------------------------------------------------------


def test_a_frame_that_does_not_attach_still_gets_an_ordinal_in_the_same_plan() -> None:
    plan = planned(MIXED, callees=(parsed(WORKER),), git=holding_the_branch())

    assert row(plan, "checkout").with_resolved["branch"] == INTEGRATION
    assert row(plan, "sub.checkout").with_resolved["branch"] == FIRST_ORDINAL


def test_both_branches_reach_preflight_under_the_names_their_templates_declared() -> None:
    plan = planned(MIXED, callees=(parsed(WORKER),), git=holding_the_branch())

    assert plan.branches == {INTEGRATION: INTEGRATION, WORKED: FIRST_ORDINAL}


def test_the_attach_branch_is_the_partition_key_the_run_is_enqueued_on() -> None:
    """AD-12 takes the first declared branch, which is what serializes the sharers."""
    plan = planned(MIXED, callees=(parsed(WORKER),), git=holding_the_branch())

    assert next(iter(plan.branches)) == INTEGRATION
