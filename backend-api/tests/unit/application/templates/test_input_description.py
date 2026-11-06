"""An input's optional `description` (story 3, 2026-11-06): a string, carried on `InputDecl`."""

from __future__ import annotations

import pytest

from orchestrator.application.templates.model import INVALID_VALUE, MISSING_KEY
from orchestrator.application.templates.validate import ValidationResult, validate
from tests.unit.fakes.templates import FakeTemplateVersionRepository

STEPS = (
    "steps:\n  - id: verify\n    uses: shell\n    with:\n      command: make test\n"
    "    gate: deterministic\n"
)
DESC_LINE = 6


def template(input_body: str) -> str:
    return f"name: story\nversion: 1\ninputs:\n  spec_folder:\n{input_body}{STEPS}"


def run(text: str) -> ValidationResult:
    return validate(text, templates=FakeTemplateVersionRepository())


def test_a_description_string_is_carried_on_the_input() -> None:
    result = run(template("    type: path\n    description: Folder holding SPEC.md\n"))

    assert result.errors == ()
    assert result.template is not None
    assert result.template.inputs[0].description == "Folder holding SPEC.md"


def test_an_input_without_a_description_reads_none() -> None:
    result = run(template("    type: path\n"))

    assert result.errors == ()
    assert result.template is not None
    assert result.template.inputs[0].description is None


def test_an_empty_description_validates() -> None:
    result = run(template('    type: path\n    description: ""\n'))

    assert result.errors == ()
    assert result.template is not None
    assert result.template.inputs[0].description == ""


@pytest.mark.parametrize("value", ["3", "[a]", "{a: b}", "null"])
def test_a_non_string_description_is_invalid_at_its_own_line(value: str) -> None:
    result = run(template(f"    type: path\n    description: {value}\n"))

    assert [(e.reason, e.line) for e in result.errors] == [(INVALID_VALUE, DESC_LINE)]


def test_the_check_runs_even_when_type_is_missing() -> None:
    result = run(template("    description: 3\n"))

    assert sorted(e.reason for e in result.errors) == sorted([INVALID_VALUE, MISSING_KEY])
