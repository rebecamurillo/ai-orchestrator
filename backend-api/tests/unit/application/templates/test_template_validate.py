"""`validate()` — the one entry point, and the rejection suite the story's matrix names.

Each row of the matrix is a fixture file under `fixtures/`, named by the reason it must
produce, so the table and the suite are the same list read twice. What is asserted for each
is the reason and the line, because an error that does not say where is barely an error.

The four properties that hold whatever the input is are asserted separately at the end:
one pass, sorted output, no exception, and no tree when there is an error.
"""

from __future__ import annotations

import pytest

from orchestrator.application.templates.model import (
    BAD_DEFAULT,
    BAD_REDISPATCH,
    CALL_CYCLE,
    CALL_DEPTH,
    CALL_TIMING,
    CALLEE_INPUT_MISMATCH,
    CALLEE_NOT_FOUND,
    DUPLICATE_STEP_ID,
    EMPTY_STEPS,
    EXPRESSION_SYNTAX,
    INVALID_GATE,
    INVALID_INPUT_TYPE,
    INVALID_ON_FAIL,
    INVALID_SLUG,
    INVALID_STATUS_TOKEN,
    INVALID_TIMEOUT,
    INVALID_YAML,
    MISSING_KEY,
    NESTED_FOR_EACH,
    NON_LITERAL_VERSION,
    PARALLEL_RESERVED,
    SECOND_FOR_EACH,
    UNBOUND_VARIABLE,
    UNKNOWN_FIELD,
    UNKNOWN_KEY,
    UNKNOWN_KIND,
    USES_AND_RUN,
    ValidationResult,
)
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import fixture
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: Every rejection of the story's matrix: the fixture, the reason, and the offending line.
REJECTIONS = [
    ("unknown-key", UNKNOWN_KEY, 3),
    ("non-literal-version-string", NON_LITERAL_VERSION, 2),
    ("non-literal-version-expression", NON_LITERAL_VERSION, 2),
    ("uses-and-run-on-the-same-step", USES_AND_RUN, 6),
    ("unknown-kind", UNKNOWN_KIND, 5),
    ("unknown-kind-planner-only", UNKNOWN_KIND, 5),
    ("unbound-variable", UNBOUND_VARIABLE, 7),
    ("unknown-field", UNKNOWN_FIELD, 11),
    ("expression-syntax", EXPRESSION_SYNTAX, 11),
    ("second-for-each", SECOND_FOR_EACH, 15),
    ("nested-for-each", NESTED_FOR_EACH, 12),
    ("parallel-is-reserved", PARALLEL_RESERVED, 11),
    ("timeout-min-on-a-template-call", CALL_TIMING, 6),
    ("on-fail-on-a-template-call", CALL_TIMING, 6),
    ("callee-not-found", CALLEE_NOT_FOUND, 4),
    ("callee-input-mismatch-name", CALLEE_INPUT_MISMATCH, 11),
    ("callee-input-mismatch-type", CALLEE_INPUT_MISMATCH, 14),
    ("callee-input-mismatch-required", CALLEE_INPUT_MISMATCH, 4),
    ("call-depth-over-3", CALL_DEPTH, 4),
    ("call-cycle", CALL_CYCLE, 4),
    ("duplicate-step-id", DUPLICATE_STEP_ID, 7),
    ("redispatch-target-not-an-earlier-agent-step", BAD_REDISPATCH, 8),
    ("invalid-gate", INVALID_GATE, 8),
    ("empty-steps", EMPTY_STEPS, 3),
    ("missing-key", MISSING_KEY, 1),
    ("invalid-slug", INVALID_SLUG, 1),
    ("invalid-input-type", INVALID_INPUT_TYPE, 5),
    ("default-does-not-match-type", BAD_DEFAULT, 6),
    ("invalid-timeout-min", INVALID_TIMEOUT, 8),
    ("invalid-status-in-token", INVALID_STATUS_TOKEN, 10),
    ("invalid-on-fail", INVALID_ON_FAIL, 8),
]

AGENT = "steps:\n  - id: b\n    uses: agent\n    gate: liveness\n"
ENUM_VALUES = (
    "inputs:\n  h:\n    type: enum\n    values: [1, 2]\nsteps:\n  - id: s\n    uses: git.sync\n"
)

EXPECTED_ERROR_COUNT = 3
FULL_STEP_COUNT = 6
FULL_INPUT_COUNT = 7
SHELL_TIMEOUT = 30
RETRY_MAX = 2
BOUND_ATTEMPTS = 3
LOOP_STEP_COUNT = 1

#: Text that is not one YAML mapping: nothing, a sequence, and a broken indent.
NOT_A_DOCUMENT = ["", "- one\n- two\n", "name: story\nsteps:\n  - id: a\n   b: c\n"]


def read(name: str, templates: FakeTemplateVersionRepository) -> ValidationResult:
    return validate(fixture(name), templates=templates)


# --- the accepted files ----------------------------------------------------------------------


def test_a_minimal_file_parses_with_nothing_left_unvalidated(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = read("minimal-valid", templates)

    assert result.errors == ()
    assert result.unvalidated == ()
    assert result.template is not None


def test_the_parsed_step_carries_the_metadata_of_its_kind(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("minimal-valid", templates).template

    assert template is not None
    assert template.steps[0].meta.gate_default == "deterministic"
    assert template.steps[0].meta.timeout_default_min == SHELL_TIMEOUT


def test_run_is_sugar_for_a_shell_step_with_a_command(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("run-sugar", templates).template

    assert template is not None
    assert template.steps[0].uses == "shell"
    assert template.steps[0].params == (("command", "make test"),)
    assert type(dict(template.steps[0].params)["command"]) is str


def test_a_step_with_no_gate_is_unvalidated_and_not_an_error(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = read("missing-gate", templates)

    assert result.errors == ()
    assert result.unvalidated == ("verify",)
    assert result.template is not None


def test_a_chain_of_three_templates_passes_and_reads_each_callee_through_the_port(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = read("initiative-chain", templates)

    assert result.errors == ()
    assert templates.get("epic", 1) is not None
    assert templates.get("story", 1) is not None


# --- the rejections --------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "reason", "line"), REJECTIONS, ids=[r[0] for r in REJECTIONS])
def test_a_rejected_file_reports_exactly_its_reason_at_the_offending_line(
    name: str, reason: str, line: int, templates: FakeTemplateVersionRepository
) -> None:
    result = read(name, templates)

    assert [(record.reason, record.line) for record in result.errors] == [(reason, line)]
    assert result.template is None


def test_a_rejected_file_says_which_template_and_version_it_is_about(
    templates: FakeTemplateVersionRepository,
) -> None:
    record = read("unknown-key", templates).errors[0]

    assert record.template == "extra"
    assert record.version == 1


def test_a_file_that_never_said_its_name_or_version_stamps_neither(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = validate("name: [a]\nversion: '1'\nsteps: []\n", templates=templates)

    assert {(record.template, record.version) for record in result.errors} == {(None, None)}


def test_three_independent_errors_all_come_back_sorted_by_line(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = read("three-independent-errors", templates)

    assert [record.line for record in result.errors] == [3, 6, 12]
    assert len(result.errors) == EXPECTED_ERROR_COUNT


# --- what is not a document ---------------------------------------------------------------------


@pytest.mark.parametrize("text", NOT_A_DOCUMENT)
def test_text_that_is_not_one_yaml_mapping_is_one_invalid_yaml_record(
    text: str, templates: FakeTemplateVersionRepository
) -> None:
    result = validate(text, templates=templates)

    assert [record.reason for record in result.errors] == [INVALID_YAML]
    assert result.template is None


def test_a_malformed_file_is_reported_at_the_line_the_loader_stopped_on(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = read("invalid-yaml", templates)

    assert [record.reason for record in result.errors] == [INVALID_YAML]
    assert result.errors[0].line > 1


# --- the whole tree ----------------------------------------------------------------------------


def test_a_rich_file_parses_into_the_tree_the_planner_will_read(
    templates: FakeTemplateVersionRepository,
) -> None:
    result = read("full-valid", templates)

    assert result.errors == ()
    assert result.template is not None
    assert result.template.description == "all stories of one epic on one branch"
    assert len(result.template.inputs) == FULL_INPUT_COUNT
    assert len(result.template.steps) == FULL_STEP_COUNT


def test_an_input_carries_its_type_its_requiredness_its_default_and_its_values(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("full-valid", templates).template

    assert template is not None
    declared = {decl.name: decl for decl in template.inputs}
    assert declared["branch"].type == "string"
    assert declared["branch"].required is True
    assert declared["harness"].values == ("claude", "codex")
    assert declared["harness"].default == "claude"
    assert declared["epic"].required is False
    assert declared["project"].values == ()


def test_a_plain_on_fail_and_a_redispatch_are_two_different_fields(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("full-valid", templates).template

    assert template is not None
    steps = {step.id: step for step in template.steps}
    assert steps["baseline"].on_fail == "fail"
    assert steps["verify"].on_fail is None
    assert steps["verify"].redispatch == "build"
    assert steps["verify"].redispatch_max == 1
    assert steps["checkout"].on_fail is None
    assert steps["checkout"].redispatch is None


def test_the_agent_extras_are_read_off_the_step(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("full-valid", templates).template

    assert template is not None
    build = next(step for step in template.steps if step.id == "build")
    assert build.agent is not None
    assert build.agent.expect_status_in == ("done", "blocked")
    assert build.agent.retry_max == RETRY_MAX
    assert build.agent.retry_resume_session is False
    assert build.agent.escalate_when == "output.status == blocked"
    assert build.agent.pause_when == "epic.spec_checkpoint"
    assert build.agent.prompt_dispatch == "Run the skill {skill} in folder {spec_folder}."
    assert build.agent.prompt_rendered == "The workflow is rendered at {path}."
    assert build.agent.prompt_answer == 'Answer to "{condition}": {answer}'
    assert build.agent.prompt_halt == "Halt after planning."


def test_an_agent_that_declares_no_extras_still_gets_the_defaults(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("agent-defaults", templates).template

    assert template is not None
    build = template.steps[0]
    assert build.agent is not None
    assert build.agent.expect_files == ()
    assert build.agent.expect_status_in == ()
    assert build.agent.retry_max is None
    assert build.agent.retry_resume_session is True
    assert build.agent.escalate_when is None
    assert build.agent.prompt_dispatch is None
    assert build.agent.prompt_rendered is None
    assert build.agent.prompt_answer is None
    assert build.agent.prompt_halt is None


def test_a_with_map_keeps_its_nested_maps_and_lists_without_the_line_bookkeeping(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("full-valid", templates).template

    assert template is not None
    build = next(step for step in template.steps if step.id == "build")
    params = dict(build.params)
    assert params["args"] == {"spec_folder": "{{spec_folder}}", "globs": ["tests", "docs"]}
    assert type(params["args"]) is dict
    assert type(params["args"]["globs"]) is list


def test_the_loop_carries_its_list_expression_its_item_name_and_its_own_steps(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("full-valid", templates).template

    assert template is not None
    stories = template.steps[4]
    assert stories.source == "{{spec_folder}}/stories.yaml"  # type: ignore[union-attr]
    assert stories.as_name == "story"  # type: ignore[union-attr]
    assert stories.pause_before_item_when is None  # type: ignore[union-attr]
    assert stories.pause_after_item_when == "story.done_checkpoint"  # type: ignore[union-attr]
    assert len(stories.steps) == LOOP_STEP_COUNT  # type: ignore[union-attr]


def test_a_call_carries_the_callee_it_names_and_the_bindings_it_passes(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("full-valid", templates).template

    assert template is not None
    story = template.steps[4].steps[0]  # type: ignore[union-attr]
    assert story.call is not None
    assert (story.call.name, story.call.version) == ("story", 2)
    assert dict(story.call.inputs)["attempts"] == BOUND_ATTEMPTS
    assert story.params == ()


def test_a_call_that_binds_nothing_holds_no_bindings(
    templates: FakeTemplateVersionRepository,
) -> None:
    template = read("call-without-inputs", templates).template

    assert template is not None
    assert template.steps[0].call is not None
    assert template.steps[0].call.inputs == ()


# --- the invariant: `validate()` returns, whatever it is given ----------------------------

#: Inputs whose values would reach a pydantic model of the tree if no checker had looked at
#: them first. Each is a shape the key table does not describe, and each must come back as a
#: record rather than as an exception out of `validate()`.
HOSTILE = [
    ("a for_each that is not text", "steps:\n  - id: l\n    for_each: [a, b]\n    as: x\n"),
    ("an expect glob that is not text", AGENT + "    expect:\n      files: [3]\n"),
    ("a retry count that is not an integer", AGENT + "    retry:\n      max: two\n"),
    ("a retry count that is a flag", AGENT + "    retry:\n      max: true\n"),
    ("a retry prompt that is not text", AGENT + "    retry:\n      prompt: [a]\n"),
    ("a resume flag that is not a flag", AGENT + "    retry:\n      resume_session: x\n"),
    ("an enum value that is not text", ENUM_VALUES),
    ("a run that is a list", "steps:\n  - id: s\n    run: [make, test]\n"),
    ("a run that is empty", "steps:\n  - id: s\n    run: ''\n"),
    ("a steps entry that is not a mapping", "steps:\n  - just-a-string\n"),
    ("a with that is not a mapping", "steps:\n  - id: s\n    uses: shell\n    with: x\n"),
    ("an inputs block that is not a mapping", "inputs: b\nsteps:\n  - id: s\n    uses: git.sync\n"),
    ("a default of the wrong type", "inputs:\n  b:\n    type: number\n    default: [1]\n"),
    ("a version that is a flag", "version: true\nsteps:\n  - id: s\n    uses: git.sync\n"),
    ("a name that is not text", "name: [a]\nsteps:\n  - id: s\n    uses: git.sync\n"),
]


@pytest.mark.parametrize(("label", "body"), HOSTILE, ids=[case[0] for case in HOSTILE])
def test_hostile_input_comes_back_as_a_result_and_never_as_an_exception(
    label: str, body: str, templates: FakeTemplateVersionRepository
) -> None:
    """`validate()` never raises: a shape the table does not describe is a record."""
    result = validate("name: t\nversion: 1\n" + body, templates=templates)

    assert isinstance(result, ValidationResult)
    assert result.errors, label
    assert result.template is None


def test_every_hostile_input_that_parses_as_yaml_names_a_line_inside_the_file(
    templates: FakeTemplateVersionRepository,
) -> None:
    for label, body in HOSTILE:
        text = "name: t\nversion: 1\n" + body
        for record in validate(text, templates=templates).errors:
            assert 1 <= record.line <= len(text.splitlines()), (label, record)


# --- the unvalidated list on the error branch ---------------------------------------------


def test_a_gateless_step_is_still_reported_when_the_file_also_has_an_error(
    templates: FakeTemplateVersionRepository,
) -> None:
    """`unvalidated` is a fact about the file, not a consequence of the rest of it."""
    result = read("unvalidated-with-error", templates)

    assert [(record.reason, record.line) for record in result.errors] == [(UNKNOWN_KEY, 3)]
    assert result.unvalidated == ("verify",)
    assert result.template is None
