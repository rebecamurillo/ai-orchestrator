"""A skipped shell row says which command is missing, not that one is (AD-7, FR-8).

`skipped · no command` tells an Operator that something is unset. `skipped · no
unit_test_command` tells them which box to fill in — and once a Repository states three
commands, the difference is two thirds of the Operators who read the reason.

The reason is decided by the *expression* a Template wrote, never by the value it resolved
to: both resolve to nothing, and only the expression knows whether it asked a Repository
for anything. These tests drive `empty_command_reason` with declared text for that reason.
"""

from __future__ import annotations

import pytest

from orchestrator.application.templates.expressions import ENTITY_FIELDS
from orchestrator.application.templates.plan_model import (
    REASON_NO_COMMAND,
    names_a_field,
    reason_no_field,
)
from orchestrator.application.templates.skip_reason import (
    COMMAND_ENTITY,
    QUALITY_GATE_FIELD,
    empty_command_reason,
)

#: Every command a Repository states. Read off the validator's own allowlist rather than
#: retyped, so a fourth command added there fails here until it is considered.
COMMANDS = tuple(
    sorted(field for field in ENTITY_FIELDS[COMMAND_ENTITY] if field.endswith("_command"))
)


def test_the_three_repository_commands_are_the_validators_own() -> None:
    """The set these rules cover is not a local copy of the allowlist."""
    assert COMMANDS == ("install_command", "quality_gate_command", "unit_test_command")


@pytest.mark.parametrize("field", COMMANDS)
def test_a_row_that_asked_for_a_repository_command_names_it(field: str) -> None:
    assert empty_command_reason(f"{{{{repository.{field}}}}}") == f"no {field}"


@pytest.mark.parametrize("field", COMMANDS)
def test_the_reason_is_the_one_the_readiness_line_recognises(field: str) -> None:
    """`harness_readiness_evaluate._verify_line` tests the shape, not one literal."""
    assert names_a_field(empty_command_reason(f"{{{{repository.{field}}}}}"))


def test_the_quality_gate_is_no_longer_the_only_field_a_reason_can_name() -> None:
    """The defect this module exists to close: the reason used to be welded to one field."""
    quality_gate = empty_command_reason(f"{{{{repository.{QUALITY_GATE_FIELD}}}}}")
    unit_tests = empty_command_reason("{{repository.unit_test_command}}")

    assert quality_gate == reason_no_field(QUALITY_GATE_FIELD)
    assert unit_tests == reason_no_field("unit_test_command")
    assert quality_gate != unit_tests


def test_a_command_that_named_no_entity_field_is_a_bare_no_command() -> None:
    assert empty_command_reason("make check") == REASON_NO_COMMAND
    assert empty_command_reason("") == REASON_NO_COMMAND


def test_a_field_of_another_entity_is_not_a_repositorys_missing_command() -> None:
    """Both halves are matched: a Project states no commands, so this asks for nothing."""
    assert empty_command_reason("{{project.quality_gate_command}}") == REASON_NO_COMMAND


def test_a_field_the_entity_does_not_expose_is_not_named_back_at_the_operator() -> None:
    """A reason may only name a box that exists to be filled in."""
    assert empty_command_reason("{{repository.made_up_command}}") == REASON_NO_COMMAND


def test_a_command_that_is_not_text_asks_for_nothing() -> None:
    """`params` holds whatever the Template wrote; a `run:` that is not a string is not one."""
    assert empty_command_reason(None) == REASON_NO_COMMAND
    assert empty_command_reason(7) == REASON_NO_COMMAND


def test_the_bare_reason_is_not_mistaken_for_one_that_names_a_field() -> None:
    """`no command` shares `names_a_field`'s prefix and must still answer False."""
    assert not names_a_field(REASON_NO_COMMAND)
    assert not names_a_field("already done")
