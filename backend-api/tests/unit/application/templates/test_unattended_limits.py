"""Per-initiative stall and wall-clock limits: story O-7 of
_bmad-output/specs/unattended-hub-run/PLAN.md.

`timeout_min` and `stall_min` take a positive integer or one `{{ }}`; the planner binds an
input's literal `default` when a Run or a caller leaves the input absent or empty. Every
Template here is a fixture this module owns.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.templates.defaults import with_defaults
from orchestrator.application.templates.minutes import step_minutes
from orchestrator.application.templates.model import INVALID_TIMEOUT, UNBOUND_VARIABLE, Step
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import BAD_MINUTES, PlanError, ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.templates import FakeTemplateVersionRepository

AGENT_STALL_DEFAULT = 30

ROOT_HEADER = """name: initiative
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  harness:     { type: enum, values: [claude, codex, local], default: claude }
  stall_min:   { type: number, required: false, default: 90 }
  label:       { type: string, required: false }
steps:
"""

CALL = """  - id: work
    uses: template
    with:
      name: leaf
      version: 1
      inputs:
        harness: "{{harness}}"
        stall_min: "{{stall_min}}"
"""

LEAF = """name: leaf
version: 1
inputs:
  harness:   { type: enum, values: [claude, codex, local], default: claude }
  stall_min: { type: number, required: false }
steps:
  - id: build
    uses: agent
    with: { harness: "{{harness}}" }
    stall_min: "{{stall_min}}"
    gate: liveness
"""


def _tree(root_text: str, leaf_text: str = LEAF) -> ResolvedTree:
    leaf = validate(leaf_text, templates=FakeTemplateVersionRepository([]))
    assert leaf.template is not None, leaf.errors
    repo = FakeTemplateVersionRepository(
        [TemplateVersion(name="leaf", version=1, yaml=leaf_text, hash="sha")]
    )
    root = validate(root_text, templates=repo)
    assert root.template is not None, root.errors
    return ResolvedTree(root=root.template, callees=(leaf.template,))


def _stall(values: dict[str, Any], root_text: str = ROOT_HEADER + CALL) -> Any:
    plan = plan_run(
        _tree(root_text),
        fixtures.inputs(values=values),
        git=fixtures.repo_init_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    row = next(row for row in plan.rows if row.path == "work.build")
    return row.with_resolved["stall_min"]


def test_an_unbound_input_takes_its_declared_literal_default_down_the_call() -> None:
    assert _stall({}) == 90  # noqa: PLR2004


def test_a_bound_value_wins_over_the_default() -> None:
    assert _stall({"stall_min": 120}) == 120  # noqa: PLR2004


def test_a_string_of_digits_is_a_count() -> None:
    assert _stall({"stall_min": " 45 "}) == 45  # noqa: PLR2004


def test_the_empty_string_gets_the_default_and_without_one_the_kind_default() -> None:
    assert _stall({"stall_min": ""}) == 90  # noqa: PLR2004
    no_default = (ROOT_HEADER + CALL).replace(", default: 90", "")
    assert _stall({"stall_min": ""}, no_default) == AGENT_STALL_DEFAULT
    assert _stall({}, no_default) == AGENT_STALL_DEFAULT


@pytest.mark.parametrize("bad", ["abc", "0", 0, -5, True, 1.5, "1.5"])
def test_a_value_that_is_not_a_positive_integer_refuses_the_plan(bad: object) -> None:
    with pytest.raises(PlanError) as refused:
        _stall({"stall_min": bad})

    assert refused.value.reason == BAD_MINUTES


def test_a_callees_own_literal_default_applies_when_the_caller_binds_nothing() -> None:
    leaf = LEAF.replace("required: false }", "required: false, default: 45 }")
    root = (
        (ROOT_HEADER + CALL)
        .replace('        stall_min: "{{stall_min}}"\n', "")
        .replace(", default: 90", "")
    )
    plan = plan_run(
        _tree(root, leaf),
        fixtures.inputs(),
        git=fixtures.repo_init_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    assert plan.rows[1].with_resolved["stall_min"] == 45  # noqa: PLR2004


# --- the validator -------------------------------------------------------------------------

LOOP_FIELD = (
    ROOT_HEADER.replace("steps:\n", "  folder: { type: path, required: true }\nsteps:\n")
    + """  - id: things
    for_each: "{{folder}}/things.yaml"
    as: thing
    steps:
      - id: work
        uses: agent
        with: { harness: "{{harness}}" }
        timeout_min: "{{thing.limit}}"
        stall_min: "{{thing.stall_min}}"
        gate: liveness
"""
)


def _errors(root_text: str) -> list[str]:
    result = validate(root_text, templates=FakeTemplateVersionRepository([]))
    return [error.reason for error in result.errors]


def _agent(extra: str) -> str:
    head = '  - id: work\n    uses: agent\n    with: { harness: "{{harness}}" }\n'
    return ROOT_HEADER + head + extra + "    gate: liveness\n"


def test_an_expression_over_a_number_or_string_input_is_valid() -> None:
    assert _errors(_agent('    stall_min: "{{stall_min}}"\n    timeout_min: "{{label}}"\n')) == []


def test_an_item_field_is_valid_because_item_fields_are_unchecked() -> None:
    assert _errors(LOOP_FIELD) == []


def test_an_unbound_name_is_reported_as_unbound() -> None:
    assert _errors(_agent('    stall_min: "{{nope}}"\n')) == [UNBOUND_VARIABLE]


@pytest.mark.parametrize("written", ["{{repository.url}}", "{{repository}}", "{{project}}"])
def test_an_entity_input_is_not_a_limit(written: str) -> None:
    assert INVALID_TIMEOUT in _errors(_agent(f'    timeout_min: "{written}"\n'))


def test_a_whole_item_without_a_field_is_not_a_limit() -> None:
    assert INVALID_TIMEOUT in _errors(LOOP_FIELD.replace("{{thing.limit}}", "{{thing}}"))


def test_a_literal_that_is_not_a_count_and_has_no_braces_is_still_refused() -> None:
    assert _errors(_agent("    stall_min: many\n")) == [INVALID_TIMEOUT]


# --- item field limits at plan time --------------------------------------------------------


def test_an_item_field_sets_the_limit_and_an_omitted_field_takes_the_kind_default() -> None:
    files = {(fixtures.BASE_SHA, "docs/things.yaml"): "- id: a\n  limit: 7\n- id: b\n"}
    result = validate(LOOP_FIELD, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None
    plan = plan_run(
        ResolvedTree(root=result.template),
        fixtures.inputs(values={"folder": "docs"}),
        git=fixtures.repo_init_git().__class__(
            refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA}, files=files, listings={}
        ),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    work = [row.with_resolved for row in plan.rows if row.path.endswith("work")]

    assert [(w.get("timeout_min"), w["stall_min"]) for w in work] == [
        (7, AGENT_STALL_DEFAULT),
        (None, AGENT_STALL_DEFAULT),
    ]


# --- the units -----------------------------------------------------------------------------


def _step() -> Step:
    result = validate(_agent(""), templates=FakeTemplateVersionRepository([]))
    assert result.template is not None
    return result.template.steps[0]  # type: ignore[return-value]


def test_step_minutes_literal_missing_and_empty() -> None:
    step = _step()

    assert step_minutes(None, 30, {}, step) == AGENT_STALL_DEFAULT
    assert step_minutes(None, None, {}, step) is None
    assert step_minutes(12, 30, {}, step) == 12  # noqa: PLR2004
    assert step_minutes("{{x}}", 30, {}, step) == AGENT_STALL_DEFAULT
    assert step_minutes("{{x}}", 30, {"x": None}, step) == AGENT_STALL_DEFAULT


def test_with_defaults_applies_literals_only() -> None:
    text = """name: d
version: 1
inputs:
  a: { type: number, default: 5 }
  b: { type: string, default: "{{a}}" }
  c: { type: string }
  d: { type: string, default: kept }
  e: { type: number, default: 0 }
steps:
  - id: s
    uses: git.sync
    gate: deterministic
"""
    result = validate(text, templates=FakeTemplateVersionRepository([]))
    assert result.template is not None

    assert with_defaults(result.template, {"d": "mine", "c": ""}) == {
        "a": 5,
        "d": "mine",
        "c": "",
        "e": 0,
    }
