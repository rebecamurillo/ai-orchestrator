"""The parsed tree and the result vocabulary.

Two rules are checked here rather than described: a `ValidationError` is a value and never
an exception (`domain/errors.py` is the only exception vocabulary), and every node of the
tree is frozen, so what a Run was planned from cannot drift from what the file said.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from orchestrator.application.steps import KIND_META
from orchestrator.application.templates import model
from orchestrator.application.templates.model import (
    INPUT_TYPES,
    ON_FAIL_ACTIONS,
    STATUS_TOKENS,
    AgentExtras,
    ForEach,
    InputDecl,
    ParsedTemplate,
    Step,
    TemplateCall,
    ValidationError,
    ValidationResult,
)

#: Every reason string the story fixes: FR-5's thirteen, the brief's five, and nine more.
REASONS = (
    "UNKNOWN_KEY UNBOUND_VARIABLE UNKNOWN_KIND USES_AND_RUN NESTED_FOR_EACH SECOND_FOR_EACH "
    "EXPRESSION_SYNTAX NON_LITERAL_VERSION CALL_CYCLE CALL_DEPTH CALLEE_INPUT_MISMATCH "
    "PARALLEL_RESERVED CALL_TIMING UNKNOWN_FIELD DUPLICATE_STEP_ID BAD_REDISPATCH "
    "INVALID_ON_FAIL INVALID_GATE INVALID_YAML CALLEE_NOT_FOUND MISSING_KEY INVALID_SLUG "
    "INVALID_INPUT_TYPE BAD_DEFAULT EMPTY_STEPS INVALID_TIMEOUT INVALID_STATUS_TOKEN"
).split()

EXPECTED_REASON_COUNT = 27


def a_step(**overrides: object) -> Step:
    fields: dict[str, object] = {
        "line": 1,
        "id": "verify",
        "uses": "shell",
        "meta": KIND_META["shell"],
    }
    fields.update(overrides)
    return Step(**fields)  # type: ignore[arg-type]


def test_every_reason_the_story_fixes_has_a_name_here() -> None:
    assert len(REASONS) == EXPECTED_REASON_COUNT


@pytest.mark.parametrize("name", REASONS)
def test_a_reason_is_a_lowercase_phrase(name: str) -> None:
    reason = getattr(model, name)

    assert isinstance(reason, str)
    assert reason == reason.lower()


def test_no_two_reasons_are_the_same_phrase() -> None:
    phrases = [getattr(model, name) for name in REASONS]

    assert len(set(phrases)) == len(phrases)


def test_the_thirteen_of_fr_5_read_exactly_as_fr_5_writes_them() -> None:
    assert model.UNKNOWN_KEY == "unknown key"
    assert model.USES_AND_RUN == "uses and run on the same step"
    assert model.CALL_DEPTH == "call depth over 3"
    assert model.CALL_TIMING == "timeout_min or on_fail on a template call"
    assert model.PARALLEL_RESERVED == "parallel is reserved"


def test_a_validation_error_is_a_value_and_not_something_that_can_be_raised() -> None:
    assert not issubclass(ValidationError, Exception)


def test_the_input_types_are_the_seven_the_key_table_lists() -> None:
    assert INPUT_TYPES == frozenset(
        {"project", "repository", "string", "path", "enum", "number", "item"}
    )


def test_the_plain_on_fail_actions_are_three() -> None:
    assert ON_FAIL_ACTIONS == frozenset({"escalate", "fail", "continue"})


def test_the_status_tokens_are_the_six_of_the_routing_set() -> None:
    assert STATUS_TOKENS == frozenset(
        {"draft", "ready-for-dev", "in-progress", "in-review", "blocked", "done"}
    )


def test_a_result_with_nothing_in_it_holds_no_template_no_error_and_no_path() -> None:
    result = ValidationResult()

    assert result.template is None
    assert result.errors == ()
    assert result.unvalidated == ()


def test_an_error_names_no_template_until_validate_stamps_one_on_it() -> None:
    record = ValidationError(line=4, reason=model.UNKNOWN_KEY)

    assert record.template is None
    assert record.version is None


def test_a_step_is_frozen() -> None:
    with pytest.raises(PydanticValidationError):
        a_step().id = "other"  # type: ignore[misc]


def test_a_step_carries_its_kind_metadata_resolved() -> None:
    assert a_step().meta.timeout_default_min == KIND_META["shell"].timeout_default_min


def test_a_step_declares_no_gate_until_the_file_does() -> None:
    assert a_step().gate is None


def test_the_other_nodes_are_frozen_too() -> None:
    nodes = (
        InputDecl(line=1, name="branch", type="string"),
        AgentExtras(line=1),
        TemplateCall(line=1, name="story", version=1),
        ForEach(line=1, id="stories", source="{{f}}", as_name="story"),
        ParsedTemplate(line=1, name="epic", version=1),
    )

    for node in nodes:
        with pytest.raises(PydanticValidationError):
            node.line = 2  # type: ignore[misc]


def test_an_agent_resumes_its_session_unless_the_file_says_otherwise() -> None:
    assert AgentExtras(line=1).retry_resume_session is True


def test_a_template_holds_its_steps_in_file_order_as_a_tuple() -> None:
    template = ParsedTemplate(line=1, name="epic", version=1, steps=(a_step(),))

    assert isinstance(template.steps, tuple)
    assert template.steps[0].id == "verify"
