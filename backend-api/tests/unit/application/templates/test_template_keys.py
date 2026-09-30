"""The key table: `keys.py` over `table.py` and `inputs.py`.

Each test names one row of the table and the one reason that row produces. The checker is
read directly rather than through `validate()` so that a rule and its line are asserted
without the sort and the stamping in between; `test_template_validate.py` is where the
whole rejection suite runs over the fixture files.
"""

from __future__ import annotations

import pytest

from orchestrator.application.templates.agent import RETRY_SHAPES, check_agent_extras
from orchestrator.application.templates.inputs import declared_inputs, declared_types
from orchestrator.application.templates.keys import check_keys
from orchestrator.application.templates.model import (
    BAD_DEFAULT,
    BAD_REDISPATCH,
    CALL_TIMING,
    CONFLICTING_ROUTE,
    DISPATCH_PROMPT_REQUIRED,
    DUPLICATE_STEP_ID,
    EMPTY_STEPS,
    HALT_PROMPT_REQUIRED,
    INVALID_DISPATCH_FORM,
    INVALID_GATE,
    INVALID_INPUT_TYPE,
    INVALID_ON_FAIL,
    INVALID_SLUG,
    INVALID_STATUS_TOKEN,
    INVALID_TIMEOUT,
    INVALID_VALUE,
    MISSING_KEY,
    NESTED_FOR_EACH,
    NON_LITERAL_VERSION,
    PARALLEL_RESERVED,
    RENDERED_PROMPT_REQUIRED,
    RETRY_PROMPT_REQUIRED,
    SECOND_FOR_EACH,
    UNKNOWN_KEY,
    UNKNOWN_KIND,
    USES_AND_RUN,
)
from orchestrator.application.templates.table import is_count, is_slug, unknown_keys
from tests.unit.application.templates import parsed, reasons

HEAD = "name: story\nversion: 1\n"
SHELL = "steps:\n  - id: verify\n    uses: shell\n    with:\n      command: make test\n"
GATED = SHELL + "    gate: deterministic\n"

EXPECTED_ID_LINE = 3
AGENT = "steps:\n  - id: build\n    uses: agent\n    gate: liveness\n"


def check(text: str) -> tuple[list[str], list[str]]:
    errors, unvalidated = check_keys(parsed(text))
    return reasons(errors), unvalidated


def lines(text: str) -> list[int]:
    errors, _ = check_keys(parsed(text))
    return [record.line for record in errors]


# --- the template level ---------------------------------------------------------------------


def test_a_minimal_file_has_nothing_to_report() -> None:
    assert check(HEAD + GATED) == ([], [])


def test_a_key_the_template_level_does_not_accept_is_unknown() -> None:
    found, _ = check(HEAD + "schedule: nightly\n" + GATED)

    assert found == [UNKNOWN_KEY]


def test_an_unknown_key_is_reported_at_its_own_line() -> None:
    assert lines(HEAD + "schedule: nightly\n" + GATED) == [EXPECTED_ID_LINE]


def test_a_file_with_no_name_is_missing_a_key() -> None:
    assert check("version: 1\n" + GATED)[0] == [MISSING_KEY]


def test_a_name_that_is_not_a_slug_is_refused() -> None:
    assert check("name: Story_One\nversion: 1\n" + GATED)[0] == [INVALID_SLUG]


def test_a_file_with_no_version_is_missing_a_key() -> None:
    assert check("name: story\n" + GATED)[0] == [MISSING_KEY]


@pytest.mark.parametrize("written", ['"1"', '"{{v}}"', "0", "true"])
def test_a_version_that_is_not_a_positive_integer_literal_is_refused(written: str) -> None:
    assert check(f"name: story\nversion: {written}\n" + GATED)[0] == [NON_LITERAL_VERSION]


def test_a_file_with_no_steps_has_no_steps() -> None:
    assert check(HEAD)[0] == [EMPTY_STEPS]


def test_a_steps_list_with_nothing_in_it_has_no_steps() -> None:
    assert check(HEAD + "steps: []\n")[0] == [EMPTY_STEPS]


def test_a_steps_key_that_is_not_a_list_has_no_steps_either() -> None:
    assert check(HEAD + "steps: everything\n")[0] == [EMPTY_STEPS]


# --- inputs -----------------------------------------------------------------------------


def test_a_file_with_no_inputs_declares_nothing_and_reports_nothing() -> None:
    assert declared_inputs(parsed(HEAD + GATED)) == {}
    assert check(HEAD + GATED)[0] == []


def test_an_inputs_block_that_is_not_a_map_is_missing_a_key() -> None:
    assert check(HEAD + "inputs: branch\n" + GATED)[0] == [MISSING_KEY]


def test_an_input_that_is_not_a_map_is_missing_a_key() -> None:
    assert check(HEAD + "inputs:\n  branch: string\n" + GATED)[0] == [MISSING_KEY]


def test_an_input_with_no_type_is_missing_a_key() -> None:
    assert check(HEAD + "inputs:\n  branch:\n    required: true\n" + GATED)[0] == [MISSING_KEY]


def test_a_type_the_table_does_not_list_is_an_invalid_input_type() -> None:
    assert check(HEAD + "inputs:\n  branch:\n    type: colour\n" + GATED)[0] == [INVALID_INPUT_TYPE]


def test_an_input_key_the_table_does_not_accept_is_unknown() -> None:
    text = HEAD + "inputs:\n  branch:\n    type: string\n    secret: true\n" + GATED

    assert check(text)[0] == [UNKNOWN_KEY]


def test_values_belongs_to_an_enum_and_to_nothing_else() -> None:
    text = HEAD + "inputs:\n  branch:\n    type: string\n    values: [a]\n" + GATED

    assert check(text)[0] == [UNKNOWN_KEY]


def test_an_enum_with_no_values_is_missing_a_key() -> None:
    assert check(HEAD + "inputs:\n  h:\n    type: enum\n" + GATED)[0] == [MISSING_KEY]


def test_an_enum_whose_values_are_not_a_list_is_missing_a_key() -> None:
    text = HEAD + "inputs:\n  h:\n    type: enum\n    values: claude\n" + GATED

    assert check(text)[0] == [MISSING_KEY]


def test_an_enum_with_values_is_accepted() -> None:
    text = HEAD + "inputs:\n  h:\n    type: enum\n    values: [claude]\n" + GATED

    assert check(text)[0] == []


@pytest.mark.parametrize(
    ("declared", "default"),
    [
        ("string", "main"),
        ("path", "docs/spec"),
        ("number", "2"),
        ("number", "1.5"),
        ("enum", "claude"),
    ],
)
def test_a_default_of_the_declared_type_is_accepted(declared: str, default: str) -> None:
    text = (
        HEAD
        + f"inputs:\n  v:\n    type: {declared}\n    values: [claude]\n    default: {default}\n"
        + GATED
    )
    expected = [] if declared == "enum" else [UNKNOWN_KEY]

    assert check(text)[0] == expected


@pytest.mark.parametrize(
    ("declared", "default"),
    [("string", "3"), ("number", "often"), ("number", "true"), ("project", "a-project")],
)
def test_a_default_of_another_type_does_not_match(declared: str, default: str) -> None:
    text = HEAD + f"inputs:\n  v:\n    type: {declared}\n    default: {default}\n" + GATED

    assert check(text)[0] == [BAD_DEFAULT]


def test_a_default_outside_an_enums_values_does_not_match() -> None:
    text = HEAD + "inputs:\n  h:\n    type: enum\n    values: [claude]\n    default: codex\n"

    assert check(text + GATED)[0] == [BAD_DEFAULT]


def test_the_declared_types_are_read_for_the_scope_an_expression_resolves_in() -> None:
    text = HEAD + "inputs:\n  branch:\n    type: string\n  broken: 3\n  untyped:\n    x: 1\n"

    assert declared_types(parsed(text + GATED)) == {"branch": "string"}


def test_requiredness_is_read_alongside_the_type() -> None:
    text = HEAD + "inputs:\n  a:\n    type: string\n    required: true\n  b:\n    type: path\n"

    assert declared_inputs(parsed(text + GATED)) == {"a": ("string", True), "b": ("path", False)}


# --- steps ------------------------------------------------------------------------------


def test_a_step_with_no_id_is_missing_a_key() -> None:
    assert MISSING_KEY in check(HEAD + "steps:\n  - uses: git.sync\n")[0]


def test_a_step_id_that_is_not_a_slug_is_refused() -> None:
    assert INVALID_SLUG in check(HEAD + "steps:\n  - id: Sync_It\n    uses: git.sync\n")[0]


def test_two_steps_with_one_id_are_a_duplicate() -> None:
    text = HEAD + "steps:\n  - id: a\n    uses: git.sync\n  - id: a\n    uses: git.sync\n"

    assert DUPLICATE_STEP_ID in check(text)[0]


def test_a_step_with_neither_uses_nor_run_is_missing_a_key() -> None:
    assert check(HEAD + "steps:\n  - id: a\n    gate: deterministic\n")[0] == [MISSING_KEY]


def test_a_step_with_both_uses_and_run_says_so() -> None:
    text = HEAD + "steps:\n  - id: a\n    uses: shell\n    run: make test\n"

    assert check(text)[0] == [USES_AND_RUN]


def test_run_is_sugar_and_needs_no_with_of_its_own() -> None:
    assert check(HEAD + "steps:\n  - id: a\n    run: make test\n    gate: deterministic\n") == (
        [],
        [],
    )


def test_a_with_beside_run_is_a_key_that_belongs_to_the_other_spelling() -> None:
    text = HEAD + "steps:\n  - id: a\n    run: make test\n    with:\n      command: x\n"

    assert check(text)[0] == [UNKNOWN_KEY]


def test_a_kind_the_registry_does_not_hold_is_unknown() -> None:
    assert check(HEAD + "steps:\n  - id: a\n    uses: rocket\n")[0] == [UNKNOWN_KIND]


def test_a_planner_only_kind_may_not_be_written_in_a_file() -> None:
    assert check(HEAD + "steps:\n  - id: a\n    uses: plan.check\n")[0] == [UNKNOWN_KIND]


def test_a_with_key_the_kind_does_not_take_is_unknown() -> None:
    text = HEAD + "steps:\n  - id: a\n    uses: git.sync\n    with:\n      branch: main\n"

    assert check(text)[0] == [UNKNOWN_KEY]


def test_a_with_that_is_not_a_map_is_missing_a_key() -> None:
    text = HEAD + "steps:\n  - id: a\n    uses: shell\n    with: make test\n"

    assert check(text)[0] == [MISSING_KEY]


def test_a_step_key_the_table_does_not_accept_is_unknown() -> None:
    text = HEAD + "steps:\n  - id: a\n    uses: git.sync\n    unless: friday\n"

    assert UNKNOWN_KEY in check(text)[0]


# --- gate, timing and on_fail ---------------------------------------------------------------


def test_a_gate_outside_the_three_tokens_is_invalid() -> None:
    assert check(HEAD + SHELL + "    gate: green\n")[0] == [INVALID_GATE]


def test_a_step_with_no_gate_is_reported_as_unvalidated_and_not_as_an_error() -> None:
    assert check(HEAD + SHELL) == ([], ["verify"])


def test_a_step_inside_a_loop_is_reported_under_the_loops_id() -> None:
    text = (
        HEAD
        + "steps:\n  - id: stories\n    for_each: '{{f}}'\n    as: story\n"
        + "    steps:\n      - id: build\n        uses: git.sync\n"
    )
    _, unvalidated = check(text)

    assert unvalidated == ["stories.build"]


def test_a_step_whose_id_is_not_a_name_has_no_path_at_all() -> None:
    """These are the node ids 3.4 joins on; an empty segment would be junk at that seam."""
    _, unvalidated = check(HEAD + "steps:\n  - id: 3\n    uses: git.sync\n")

    assert unvalidated == []


def test_a_step_inside_a_loop_whose_id_is_not_a_name_has_no_path_either() -> None:
    text = (
        HEAD
        + "steps:\n  - id: 3\n    for_each: '{{f}}'\n    as: story\n"
        + "    steps:\n      - id: build\n        uses: git.sync\n"
    )
    _, unvalidated = check(text)

    assert unvalidated == []


def test_the_same_path_is_never_reported_twice() -> None:
    text = HEAD + "steps:\n  - id: dup\n    uses: git.sync\n  - id: dup\n    uses: git.sync\n"
    _, unvalidated = check(text)

    assert unvalidated == ["dup"]


# --- what would otherwise reach a pydantic model unchecked ---------------------------------


def test_an_entry_of_steps_that_is_not_a_mapping_is_a_step_that_would_vanish() -> None:
    assert check(HEAD + "steps:\n  - just-a-string\n")[0] == [MISSING_KEY]


def test_an_entry_of_a_loops_steps_that_is_not_a_mapping_is_reported_too() -> None:
    text = HEAD + "steps:\n  - id: l\n    for_each: '{{f}}'\n    as: s\n    steps:\n      - x\n"

    assert MISSING_KEY in check(text)[0]


@pytest.mark.parametrize("written", ["[make, test]", "''", "3"])
def test_a_run_that_is_not_a_command_is_missing_a_key(written: str) -> None:
    assert check(HEAD + f"steps:\n  - id: s\n    run: {written}\n")[0] == [MISSING_KEY]


@pytest.mark.parametrize(
    "written",
    ["    retry:\n      max: two\n", "    retry:\n      max: true\n"],
)
def test_a_retry_count_that_is_not_an_integer_is_an_invalid_value(written: str) -> None:
    assert check(HEAD + AGENT + written)[0] == [INVALID_VALUE]


def test_a_retry_prompt_that_is_not_text_is_an_invalid_value() -> None:
    assert check(HEAD + AGENT + "    retry:\n      prompt: [a]\n")[0] == [INVALID_VALUE]


def test_a_retry_block_with_no_prompt_requires_a_prompt() -> None:
    assert check(HEAD + AGENT + "    retry:\n      max: 2\n")[0] == [RETRY_PROMPT_REQUIRED]


def test_a_retry_block_with_an_empty_prompt_is_invalid() -> None:
    assert check(HEAD + AGENT + "    retry:\n      prompt: ''\n")[0] == [RETRY_PROMPT_REQUIRED]


def test_a_resume_session_that_is_not_a_flag_is_an_invalid_value() -> None:
    assert check(HEAD + AGENT + "    retry:\n      resume_session: maybe\n")[0] == [INVALID_VALUE]


def test_a_retry_that_says_nothing_of_a_sub_key_leaves_it_alone() -> None:
    assert check(HEAD + AGENT + "    retry:\n      prompt: again\n")[0] == []


def test_an_expect_glob_that_is_not_text_is_an_invalid_value() -> None:
    assert check(HEAD + AGENT + "    expect:\n      files: [3]\n")[0] == [INVALID_VALUE]


def test_an_expect_files_that_is_not_a_list_is_left_to_the_shape_rules() -> None:
    assert check(HEAD + AGENT + "    expect:\n      files: one\n")[0] == []


# --- prompts (Operator decision, 2026-09-27: agent prose lives in the template) -----------


def test_a_prompts_block_with_the_four_clauses_is_accepted() -> None:
    text = (
        HEAD
        + AGENT
        + (
            "    prompts:\n"
            "      dispatch: Run the skill {skill}.\n"
            "      rendered: Read {path} first.\n"
            "      answer: 'Answer to \"{condition}\": {answer}'\n"
            "      halt: Halt after planning.\n"
        )
    )

    assert check(text)[0] == []


def test_a_prompts_sub_key_the_table_does_not_accept_is_unknown() -> None:
    assert check(HEAD + AGENT + "    prompts:\n      preamble: hi\n")[0] == [UNKNOWN_KEY]


def test_a_prompts_block_that_is_not_a_map_is_missing_a_key() -> None:
    assert check(HEAD + AGENT + "    prompts: go\n")[0] == [MISSING_KEY]


def test_a_prompt_clause_that_is_not_text_is_an_invalid_value() -> None:
    assert check(HEAD + AGENT + "    prompts:\n      dispatch: [a]\n")[0] == [INVALID_VALUE]


def test_a_prompts_block_with_a_redispatch_clause_is_accepted() -> None:
    text = HEAD + AGENT + "    prompts:\n      redispatch: 'Verify failed: {command}.'\n"

    assert check(text)[0] == []


def test_a_redispatch_clause_that_is_not_text_is_an_invalid_value() -> None:
    assert check(HEAD + AGENT + "    prompts:\n      redispatch: [a]\n")[0] == [INVALID_VALUE]


def test_prompts_on_a_step_of_any_other_kind_is_unknown() -> None:
    assert check(HEAD + GATED + "    prompts:\n      dispatch: go\n")[0] == [UNKNOWN_KEY]


# --- the routing lists (Operator decision, 2026-09-27: the result contract is declared) ---


def test_the_routing_lists_take_free_form_tokens() -> None:
    text = (
        HEAD
        + AGENT
        + (
            "    expect:\n"
            "      success: [shipped]\n"
            "      blocked: [stuck]\n"
            "      checkpoint: [plan-ready]\n"
            "      misconfigured_when: ['no workspace']\n"
        )
    )

    assert check(text)[0] == []


def test_status_in_still_binds_to_the_six_tokens_while_success_does_not() -> None:
    """The legacy list keeps its vocabulary; the routing lists are the method's own."""
    text = HEAD + AGENT + "    expect:\n      status_in: [shipped]\n      success: [shipped]\n"

    assert check(text)[0] == [INVALID_STATUS_TOKEN]


@pytest.mark.parametrize("written", ["[3]", "['']"])
def test_a_routing_entry_that_is_not_non_empty_text_is_an_invalid_value(written: str) -> None:
    assert check(HEAD + AGENT + f"    expect:\n      success: {written}\n")[0] == [INVALID_VALUE]


def test_a_token_in_two_routing_lists_routes_twice() -> None:
    text = HEAD + AGENT + "    expect:\n      success: [done]\n      blocked: [done]\n"

    assert check(text)[0] == [CONFLICTING_ROUTE]


# --- the prose a dispatch owes (Operator decision, 2026-09-27) ----------------------------

SKILLED = (
    "steps:\n  - id: build\n    uses: agent\n    with:\n"
    "      skill: bmad-build-auto\n    gate: liveness\n"
)
CLAUSES = (
    "    prompts:\n      dispatch: Run the skill {skill}.\n      rendered: Read {path} first.\n"
)


def test_a_skill_form_with_both_owed_clauses_is_accepted() -> None:
    assert check(HEAD + SKILLED + CLAUSES)[0] == []


def test_a_skill_form_without_a_dispatch_clause_is_refused() -> None:
    text = HEAD + SKILLED + "    prompts:\n      rendered: Read {path} first.\n"

    assert check(text)[0] == [DISPATCH_PROMPT_REQUIRED]


def test_a_skill_form_without_a_rendered_clause_is_refused() -> None:
    text = HEAD + SKILLED + "    prompts:\n      dispatch: Run the skill {skill}.\n"

    assert check(text)[0] == [RENDERED_PROMPT_REQUIRED]


def test_a_bare_skill_form_is_refused_for_both() -> None:
    assert check(HEAD + SKILLED)[0] == [DISPATCH_PROMPT_REQUIRED, RENDERED_PROMPT_REQUIRED]


def test_a_pause_when_without_a_halt_clause_is_refused_whatever_the_form() -> None:
    text = HEAD + SKILLED + CLAUSES + "    pause_when: always\n"

    assert check(text)[0] == [HALT_PROMPT_REQUIRED]


def test_a_pause_when_with_a_halt_clause_is_accepted() -> None:
    text = HEAD + SKILLED + CLAUSES + "      halt: Halt after planning.\n    pause_when: always\n"

    assert check(text)[0] == []


def test_an_own_prompt_row_may_not_also_carry_a_dispatch_clause() -> None:
    text = (
        HEAD
        + "steps:\n  - id: build\n    uses: agent\n    with:\n      prompt: Do X.\n"
        + "    gate: liveness\n    prompts:\n      dispatch: Run the skill {skill}.\n"
    )

    assert check(text)[0] == [INVALID_DISPATCH_FORM]


def test_an_own_prompt_row_may_carry_the_answer_and_halt_clauses() -> None:
    text = (
        HEAD
        + "steps:\n  - id: build\n    uses: agent\n    with:\n      prompt: Do X.\n"
        + "    gate: liveness\n    prompts:\n      halt: Halt after planning.\n"
        + "    pause_when: always\n"
    )

    assert check(text)[0] == []


def test_a_bare_agent_with_neither_skill_nor_prompt_owes_no_clause() -> None:
    """A dispatch with no base text is prose-free by construction; requiring clauses of it
    would make every minimal fixture template invalid for nothing."""
    assert check(HEAD + AGENT)[0] == []


def test_the_same_condition_may_be_blocked_and_misconfigured_when() -> None:
    """`misconfigured_when` names blocking-condition sentences, not status tokens; the
    cross-list rule does not read it."""
    text = HEAD + AGENT + "    expect:\n      blocked: [stuck]\n      misconfigured_when: [stuck]\n"

    assert check(text)[0] == []


def test_an_enum_value_that_is_not_text_is_an_invalid_value() -> None:
    text = HEAD + "inputs:\n  h:\n    type: enum\n    values: [1, 2]\n" + GATED

    assert check(text)[0] == [INVALID_VALUE]


@pytest.mark.parametrize("written", ["0", "-1", "true", "many"])
def test_a_timeout_that_is_not_a_positive_integer_is_invalid(written: str) -> None:
    assert check(HEAD + GATED + f"    timeout_min: {written}\n")[0] == [INVALID_TIMEOUT]


def test_a_positive_timeout_is_accepted() -> None:
    assert check(HEAD + GATED + "    timeout_min: 30\n")[0] == []


@pytest.mark.parametrize("action", ["escalate", "fail", "continue"])
def test_the_three_plain_on_fail_actions_are_accepted(action: str) -> None:
    assert check(HEAD + GATED + f"    on_fail: {action}\n")[0] == []


def test_an_on_fail_word_the_table_does_not_list_is_invalid() -> None:
    assert check(HEAD + GATED + "    on_fail: retreat\n")[0] == [INVALID_ON_FAIL]


def test_an_on_fail_that_is_neither_a_word_nor_a_map_is_invalid() -> None:
    assert check(HEAD + GATED + "    on_fail: [fail]\n")[0] == [INVALID_ON_FAIL]


def test_a_redispatch_map_with_the_wrong_keys_is_invalid() -> None:
    assert check(HEAD + GATED + "    on_fail: { redispatch: build }\n")[0] == [INVALID_ON_FAIL]


def test_a_redispatch_count_below_one_is_invalid() -> None:
    text = HEAD + GATED + "    on_fail: { redispatch: build, max: 0 }\n"

    assert check(text)[0] == [INVALID_ON_FAIL]


def test_a_redispatch_to_something_that_is_not_an_earlier_agent_step_is_refused() -> None:
    text = HEAD + GATED + "    on_fail: { redispatch: build, max: 1 }\n"

    assert check(text)[0] == [BAD_REDISPATCH]


def test_a_redispatch_to_an_earlier_agent_step_is_accepted() -> None:
    text = (
        HEAD
        + "steps:\n  - id: build\n    uses: agent\n    gate: liveness\n"
        + "  - id: verify\n    uses: shell\n    gate: deterministic\n"
        + "    on_fail: { redispatch: build, max: 1 }\n"
    )

    assert check(text)[0] == []


# --- the loop construct -------------------------------------------------------------------


LOOP = (
    "steps:\n  - id: stories\n    for_each: '{{f}}'\n    as: story\n"
    "    steps:\n      - id: build\n        uses: git.sync\n        gate: deterministic\n"
)


def test_one_loop_with_an_as_name_and_steps_is_accepted() -> None:
    assert check(HEAD + LOOP)[0] == []


def test_a_second_loop_at_the_top_level_is_refused() -> None:
    second = "  - id: epics\n    for_each: '{{g}}'\n    as: epic\n" + (
        "    steps:\n      - id: sync\n        uses: git.sync\n        gate: deterministic\n"
    )

    assert check(HEAD + LOOP + second)[0] == [SECOND_FOR_EACH]


def test_a_loop_inside_another_loops_steps_is_refused() -> None:
    text = (
        HEAD
        + "steps:\n  - id: outer\n    for_each: '{{f}}'\n    as: one\n"
        + "    steps:\n      - id: inner\n        for_each: '{{g}}'\n        as: two\n"
        + "        steps:\n          - id: sync\n            uses: git.sync\n"
    )

    assert NESTED_FOR_EACH in check(text)[0]


def test_parallel_is_reserved() -> None:
    assert check(HEAD + LOOP.replace("    as: story\n", "    as: story\n    parallel: 2\n"))[0] == [
        PARALLEL_RESERVED
    ]


def test_a_loop_key_the_table_does_not_accept_is_unknown() -> None:
    text = HEAD + LOOP.replace("    as: story\n", "    as: story\n    uses: shell\n")

    assert check(text)[0] == [UNKNOWN_KEY]


def test_a_loop_with_no_as_name_is_missing_a_key() -> None:
    assert MISSING_KEY in check(HEAD + LOOP.replace("    as: story\n", ""))[0]


def test_a_loop_whose_as_name_is_not_a_slug_is_refused() -> None:
    assert INVALID_SLUG in check(HEAD + LOOP.replace("as: story", "as: Story_One"))[0]


def test_a_loop_with_no_steps_has_no_steps() -> None:
    text = HEAD + "steps:\n  - id: stories\n    for_each: '{{f}}'\n    as: story\n"

    assert EMPTY_STEPS in check(text)[0]


# --- the agent extras ---------------------------------------------------------------------


def test_the_agent_extras_are_accepted_on_an_agent_step() -> None:
    text = (
        HEAD
        + AGENT
        + "    expect:\n      files: ['a']\n      status_in: [done]\n"
        + "    retry:\n      max: 2\n      prompt: again\n      resume_session: true\n"
        + "    escalate_when: 'output.status == blocked'\n"
    )

    assert check(text)[0] == []


def test_an_agent_extra_on_another_kind_is_an_unknown_key() -> None:
    text = HEAD + GATED + "    expect:\n      files: ['a']\n"

    assert check(text)[0] == [UNKNOWN_KEY]


def test_a_sub_key_expect_does_not_take_is_unknown() -> None:
    assert check(HEAD + AGENT + "    expect:\n      globs: ['a']\n")[0] == [UNKNOWN_KEY]


def test_a_sub_key_retry_does_not_take_is_unknown() -> None:
    assert check(HEAD + AGENT + "    retry:\n      forever: true\n")[0] == [UNKNOWN_KEY]


def test_an_expect_that_is_not_a_map_is_missing_a_key() -> None:
    assert check(HEAD + AGENT + "    expect: files\n")[0] == [MISSING_KEY]


def test_a_status_outside_the_routing_set_is_an_invalid_token() -> None:
    text = HEAD + AGENT + "    expect:\n      status_in: [shipped]\n"

    assert check(text)[0] == [INVALID_STATUS_TOKEN]


def test_a_status_in_that_is_not_a_list_is_left_to_the_shape_rules() -> None:
    assert check(HEAD + AGENT + "    expect:\n      status_in: done\n")[0] == []


def test_an_agent_with_no_extras_at_all_is_accepted() -> None:
    assert check(HEAD + AGENT)[0] == []


# --- the template call ---------------------------------------------------------------------


CALL = "steps:\n  - id: story\n    uses: template\n    with:\n      name: story\n      version: 1\n"


def test_a_call_naming_a_literal_name_and_version_is_accepted() -> None:
    assert check(HEAD + CALL) == ([], [])


def test_a_call_with_no_with_at_all_is_missing_a_key() -> None:
    assert check(HEAD + "steps:\n  - id: story\n    uses: template\n")[0] == [MISSING_KEY]


def test_a_call_with_no_name_is_missing_a_key() -> None:
    text = HEAD + "steps:\n  - id: story\n    uses: template\n    with:\n      version: 1\n"

    assert check(text)[0] == [MISSING_KEY]


def test_a_call_with_no_version_is_missing_a_key() -> None:
    text = HEAD + "steps:\n  - id: story\n    uses: template\n    with:\n      name: story\n"

    assert check(text)[0] == [MISSING_KEY]


def test_a_call_whose_version_is_not_a_literal_is_refused() -> None:
    assert check(HEAD + CALL.replace("version: 1", "version: '{{v}}'"))[0] == [NON_LITERAL_VERSION]


@pytest.mark.parametrize("key", ["timeout_min: 30", "on_fail: fail"])
def test_a_call_carries_neither_a_timeout_nor_an_on_fail(key: str) -> None:
    assert check(HEAD + CALL + f"    {key}\n")[0] == [CALL_TIMING]


def test_a_call_is_not_a_row_so_it_is_never_reported_as_unvalidated() -> None:
    assert check(HEAD + CALL)[1] == []


# --- the shared readers ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("story", True), ("git-sync", True), ("Story", False), ("2fast", False), (3, False)],
)
def test_a_slug_starts_lowercase_and_holds_letters_digits_and_hyphens(
    value: object, expected: bool
) -> None:
    assert is_slug(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, True), (30, True), (0, False), (-1, False), (True, False), ("2", False)],
)
def test_a_count_is_a_positive_integer_and_never_a_boolean(value: object, expected: bool) -> None:
    assert is_count(value) is expected


def test_the_unknown_key_reader_reports_one_record_per_key_the_level_refuses() -> None:
    found = unknown_keys(parsed("a: 1\nb: 2\nc: 3\n"), frozenset({"b"}))

    assert [record.line for record in found] == [1, 3]


def test_the_agent_extras_checker_is_the_one_place_their_shapes_are_decided() -> None:
    """`keys.py` delegates; the sub-key types live beside the model they are built for."""
    assert [key for key, _ in RETRY_SHAPES] == ["max", "prompt", "resume_session"]
    assert check_agent_extras(parsed("id: b\nuses: agent\n")) == []
