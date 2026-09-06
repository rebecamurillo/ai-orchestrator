"""The expression grammar: what may stand between `{{` and `}}`, and what a name may mean.

Substitution, not evaluation — so the tests here are mostly about what is refused. The
three scopes (declared inputs, the loop's item inside its own steps, and `output.status` in
`escalate_when`) are each proved to bind and to stop binding where they should.
"""

from __future__ import annotations

import pytest

from orchestrator.application.templates.expressions import check_expressions
from orchestrator.application.templates.model import (
    EXPRESSION_SYNTAX,
    INVALID_STATUS_TOKEN,
    UNBOUND_VARIABLE,
    UNKNOWN_FIELD,
)
from tests.unit.application.templates import parsed, reasons

HEAD = "name: story\nversion: 1\n"
INPUTS = (
    "inputs:\n"
    "  branch:\n    type: string\n"
    "  project:\n    type: project\n"
    "  repository:\n    type: repository\n"
    "  story:\n    type: item\n"
)


def check(text: str) -> list[str]:
    return reasons(check_expressions(parsed(text)))


def command(written: str) -> str:
    return f"steps:\n  - id: verify\n    uses: shell\n    with:\n      command: {written}\n"


# --- the grammar --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "written",
    ["'{{branch}}'", "'{{ branch }}'", "'{{story.title}}'", "'a/{{branch}}/b'", "make test"],
)
def test_a_name_or_a_name_and_one_field_is_the_whole_grammar(written: str) -> None:
    assert check(HEAD + INPUTS + command(written)) == []


@pytest.mark.parametrize(
    "written",
    ["'{{story.title | upper}}'", "'{{story.a.b}}'", "'{{}}'", "'{{1}}'", "'{{a + b}}'"],
)
def test_anything_else_between_the_braces_is_a_syntax_error(written: str) -> None:
    assert check(HEAD + INPUTS + command(written)) == [EXPRESSION_SYNTAX]


def test_a_name_nothing_declared_is_unbound() -> None:
    assert check(HEAD + INPUTS + command("'{{missing}}'")) == [UNBOUND_VARIABLE]


def test_every_expression_in_one_value_is_read() -> None:
    assert check(HEAD + INPUTS + command("'{{missing}}/{{gone}}'")) == [
        UNBOUND_VARIABLE,
        UNBOUND_VARIABLE,
    ]


# --- the entity whitelist -------------------------------------------------------------------


@pytest.mark.parametrize(
    "written",
    [
        "{{project.name}}",
        "{{repository.url}}",
        "{{repository.default_branch}}",
        "{{repository.install_command}}",
        "{{repository.quality_gate_command}}",
        "{{repository.unit_test_command}}",
    ],
)
def test_the_fields_an_entity_exposes_are_accepted(written: str) -> None:
    assert check(HEAD + INPUTS + command(f"'{written}'")) == []


@pytest.mark.parametrize("written", ["{{repository.secret}}", "{{project.token}}"])
def test_a_field_outside_the_whitelist_is_unknown(written: str) -> None:
    assert check(HEAD + INPUTS + command(f"'{written}'")) == [UNKNOWN_FIELD]


def test_a_field_of_a_scalar_input_is_unknown_too() -> None:
    assert check(HEAD + INPUTS + command("'{{branch.name}}'")) == [UNKNOWN_FIELD]


def test_the_fields_of_an_item_are_not_checked_because_a_list_file_decides_them() -> None:
    assert check(HEAD + INPUTS + command("'{{story.whatever}}'")) == []


# --- nested values ---------------------------------------------------------------------------


def test_an_expression_nested_in_a_map_under_with_is_read() -> None:
    text = (
        HEAD
        + INPUTS
        + "steps:\n  - id: build\n    uses: agent\n    with:\n      args:\n"
        + "        folder: '{{missing}}'\n"
    )

    assert check(text) == [UNBOUND_VARIABLE]


def test_an_expression_nested_in_a_list_is_read() -> None:
    text = (
        HEAD
        + INPUTS
        + "steps:\n  - id: build\n    uses: agent\n    expect:\n      files: ['{{missing}}']\n"
    )

    assert check(text) == [UNBOUND_VARIABLE]


def test_a_value_that_is_neither_text_nor_a_container_holds_no_expression() -> None:
    text = HEAD + INPUTS + "steps:\n  - id: verify\n    uses: shell\n    timeout_min: 30\n"

    assert check(text) == []


# --- the loop --------------------------------------------------------------------------------


LOOP_HEAD = "steps:\n  - id: stories\n    for_each: '{{branch}}/stories.yaml'\n    as: story\n"
LOOP_STEP = "    steps:\n      - id: build\n        uses: git.commit\n"


def test_the_item_binds_inside_the_loops_steps() -> None:
    text = HEAD + INPUTS + LOOP_HEAD + LOOP_STEP + "        with:\n          message: '{{story}}'\n"

    assert check(text) == []


def test_the_item_does_not_bind_outside_the_loop() -> None:
    text = (
        HEAD
        + "inputs:\n  branch:\n    type: string\n"
        + LOOP_HEAD
        + LOOP_STEP
        + "  - id: after\n    uses: git.commit\n    with:\n      message: '{{story}}'\n"
    )

    assert check(text) == [UNBOUND_VARIABLE]


def test_the_list_expression_reads_the_outer_scope() -> None:
    text = HEAD + INPUTS + LOOP_HEAD.replace("{{branch}}", "{{missing}}") + LOOP_STEP

    assert check(text) == [UNBOUND_VARIABLE]


def test_a_list_that_bears_no_expression_at_all_is_a_syntax_error() -> None:
    bare = LOOP_HEAD.replace("'{{branch}}/stories.yaml'", "stories.yaml")
    text = HEAD + INPUTS + bare + LOOP_STEP

    assert check(text) == [EXPRESSION_SYNTAX]


def test_a_for_each_that_is_not_text_is_not_a_list_expression() -> None:
    """`parse()` builds `ForEach.source` from this, so it is checked before it gets there."""
    text = HEAD + INPUTS + LOOP_HEAD.replace("'{{branch}}/stories.yaml'", "[a]") + LOOP_STEP

    assert check(text) == [EXPRESSION_SYNTAX]


def test_a_loop_with_no_as_name_binds_no_item_to_its_pause_condition() -> None:
    text = (
        HEAD
        + INPUTS
        + LOOP_HEAD.replace("    as: story\n", "")
        + "    pause_after_item_when: 'gone.field'\n"
        + LOOP_STEP
    )

    assert check(text) == [UNBOUND_VARIABLE]


# --- the bare conditions -----------------------------------------------------------------------


def test_a_pause_condition_is_one_item_field_written_without_braces() -> None:
    text = HEAD + INPUTS + LOOP_HEAD + "    pause_before_item_when: 'story.spec_checkpoint'\n"

    assert check(text + LOOP_STEP) == []


def test_a_pause_condition_that_is_not_a_single_field_is_a_syntax_error() -> None:
    text = HEAD + INPUTS + LOOP_HEAD + "    pause_after_item_when: '{{story.a}}'\n"

    assert check(text + LOOP_STEP) == [EXPRESSION_SYNTAX]


def test_a_pause_condition_naming_nothing_bound_is_unbound() -> None:
    text = HEAD + INPUTS + LOOP_HEAD + "    pause_after_item_when: 'gone.field'\n"

    assert check(text + LOOP_STEP) == [UNBOUND_VARIABLE]


def test_a_pause_when_on_a_step_reads_the_scope_that_step_is_in() -> None:
    text = HEAD + INPUTS + "steps:\n  - id: build\n    uses: agent\n    pause_when: 'story.x'\n"

    assert check(text) == []


def test_a_pause_condition_that_is_not_text_is_left_to_the_shape_rules() -> None:
    text = HEAD + INPUTS + "steps:\n  - id: build\n    uses: agent\n    pause_when: [a]\n"

    assert check(text) == []


# --- escalate_when ----------------------------------------------------------------------------

AGENT = "steps:\n  - id: build\n    uses: agent\n"


def test_escalate_when_compares_the_output_status_to_a_token() -> None:
    text = HEAD + AGENT + "    escalate_when: 'output.status == blocked'\n"

    assert check(text) == []


def test_escalate_when_in_any_other_shape_is_a_syntax_error() -> None:
    text = HEAD + AGENT + "    escalate_when: '{{output.status}}'\n"

    assert check(text) == [EXPRESSION_SYNTAX]


def test_escalate_when_naming_a_status_outside_the_routing_set_is_an_invalid_token() -> None:
    text = HEAD + AGENT + "    escalate_when: 'output.status == shipped'\n"

    assert check(text) == [INVALID_STATUS_TOKEN]


def test_an_escalate_when_that_is_not_text_is_left_to_the_shape_rules() -> None:
    text = HEAD + AGENT + "    escalate_when: 3\n"

    assert check(text) == []


# --- braces that never close ---------------------------------------------------------------


@pytest.mark.parametrize("written", ["'{{b'", "'b}}'", "'{{a}} {{b'", "'{{{{a}}'"])
def test_an_unbalanced_brace_is_a_syntax_error(written: str) -> None:
    """Left alone it is not an expression at all: it reaches the harness as literal text."""
    assert EXPRESSION_SYNTAX in check(HEAD + INPUTS + command(written))


def test_a_balanced_pair_leaves_no_braces_behind() -> None:
    assert check(HEAD + INPUTS + command("'{{branch}}/{{story.id}}'")) == []


# --- input defaults ---------------------------------------------------------------------------


def test_an_unbound_name_in_an_input_default_is_reported() -> None:
    """A default is substituted into every Run that names no value of its own."""
    text = HEAD + "inputs:\n  b:\n    type: string\n    default: '{{missing}}'\n" + command("x")

    assert check(text) == [UNBOUND_VARIABLE]


def test_a_default_may_name_something_the_file_declares() -> None:
    text = HEAD + INPUTS + "  copy:\n    type: string\n    default: '{{branch}}'\n" + command("x")

    assert check(text) == []


def test_a_default_that_is_not_an_expression_is_read_and_left_alone() -> None:
    text = HEAD + "inputs:\n  b:\n    type: string\n    default: main\n" + command("x")

    assert check(text) == []


def test_an_input_with_no_default_and_one_that_is_not_a_map_are_both_skipped() -> None:
    text = HEAD + "inputs:\n  b:\n    type: string\n  broken: 3\n" + command("x")

    assert check(text) == []


def test_a_file_with_no_inputs_block_has_no_defaults_to_read() -> None:
    assert check(HEAD + command("x")) == []


def test_an_entity_field_in_a_default_is_checked_against_the_whitelist() -> None:
    text = (
        HEAD
        + INPUTS
        + "  copy:\n    type: string\n    default: '{{repository.secret}}'\n"
        + command("x")
    )

    assert check(text) == [UNKNOWN_FIELD]
