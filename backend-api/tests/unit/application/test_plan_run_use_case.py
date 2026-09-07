"""Resolving the pinned tree out of storage, and handing it to the pure planner.

`plan_run` takes a `ResolvedTree` rather than a repository, because a planner that could
look a Template up could also look one up twice and plan from two different versions of it
(AD-7). This use case is the seam that does the looking up: it walks the call tree once,
through the one validator there is, and everything after it is pure.

A callee the store does not hold, and a stored version that no longer validates, are the
same outcome to an Operator — the plan cannot be built — so both are one `PlanError`
naming the version at fault.
"""

from __future__ import annotations

import pytest

from orchestrator.application.templates.plan_model import CALLEE_NOT_RESOLVED, PlanError
from orchestrator.application.use_cases.plan_run import PlanPorts, plan_for, resolve_tree
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

EPIC = TemplateRef(name="epic", version=1)
INITIATIVE = TemplateRef(name="initiative", version=1)


def stored() -> FakeTemplateVersionRepository:
    return fixtures.repository_of_versions()


def ports(templates: FakeTemplateVersionRepository, git: FakeGit) -> PlanPorts:
    return PlanPorts(templates=templates, git=git)


# --- resolving the tree -------------------------------------------------------------------


def test_a_root_that_calls_nothing_resolves_to_itself_alone() -> None:
    tree = resolve_tree(stored(), TemplateRef(name="repo-init", version=1))

    assert tree.root.name == "repo-init"
    assert tree.callees == ()


def test_a_root_resolves_every_callee_it_reaches_transitively() -> None:
    tree = resolve_tree(stored(), INITIATIVE)

    assert [callee.name for callee in tree.callees] == ["epic", "story"]


def test_a_callee_reached_twice_is_resolved_once() -> None:
    """Two callers of `story@1` are one pin, not two: `pinned_versions` is a set of pins."""
    versions = stored()
    versions.add(
        TemplateVersion(
            name="twice",
            version=1,
            yaml=TWICE,
            hash="sha",
            calls=(TemplateRef(name="story", version=1),),
        )
    )

    tree = resolve_tree(versions, TemplateRef(name="twice", version=1))

    assert [callee.name for callee in tree.callees] == ["story"]


def test_a_root_the_store_does_not_hold_is_a_plan_error() -> None:
    with pytest.raises(PlanError) as raised:
        resolve_tree(stored(), TemplateRef(name="epic", version=9))

    assert raised.value.reason == CALLEE_NOT_RESOLVED
    assert raised.value.item == "epic@9"


def test_a_caller_whose_callee_the_store_does_not_hold_no_longer_validates() -> None:
    """`validate()` resolves a call against the store, so the caller is what refuses."""
    versions = FakeTemplateVersionRepository(
        [
            TemplateVersion(
                name="epic",
                version=1,
                yaml=fixtures.TEXTS["epic"],
                hash="sha",
                calls=(TemplateRef(name="story", version=1),),
            )
        ]
    )

    with pytest.raises(PlanError) as raised:
        resolve_tree(versions, EPIC)

    assert (raised.value.reason, raised.value.item) == (CALLEE_NOT_RESOLVED, "epic@1")
    assert raised.value.line is not None


def test_a_stored_version_that_no_longer_validates_is_a_plan_error() -> None:
    versions = FakeTemplateVersionRepository(
        [TemplateVersion(name="broken", version=1, yaml="not: a template\n", hash="sha")]
    )

    with pytest.raises(PlanError) as raised:
        resolve_tree(versions, TemplateRef(name="broken", version=1))

    assert raised.value.reason == CALLEE_NOT_RESOLVED
    assert raised.value.line is not None


# --- planning through the ports -----------------------------------------------------------


def test_planning_an_epic_through_the_ports_gives_the_same_rows_as_the_pure_planner() -> None:
    result = plan_for(
        ports(stored(), fixtures.epic_git()),
        EPIC,
        fixtures.epic_inputs(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    assert result.plan_ref == fixtures.WORK_SHA
    assert result.rows[0].path == "plan"
    assert result.rows[-1].path == "link"


def test_the_ports_are_frozen() -> None:
    built = ports(stored(), FakeGit())

    with pytest.raises(AttributeError):
        built.git = FakeGit()  # type: ignore[misc]


TWICE = """name: twice
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  story:       { type: item,       required: true }
steps:
  - id: first
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
  - id: second
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
"""
