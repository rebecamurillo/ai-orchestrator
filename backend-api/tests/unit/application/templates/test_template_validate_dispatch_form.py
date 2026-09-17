"""`INVALID_DISPATCH_FORM` and `ALL_DIGIT_STEP_ID` validation rules.

Each fixture exercises one rejection; the test checks reason and line to prove both that the
rule fired and that the error points where the DSL author can find the problem.
"""

from __future__ import annotations

from orchestrator.application.templates.model import (
    ALL_DIGIT_STEP_ID,
    INVALID_DISPATCH_FORM,
    INVALID_SLUG,
    ValidationError,
)
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import fixture
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: Line of the step node in the `all-digit-step-id` fixture (name/version/steps/step).
ALL_DIGIT_STEP_LINE = 4


def read(name: str, templates: FakeTemplateVersionRepository) -> tuple[ValidationError, ...]:
    return validate(fixture(name), templates=templates).errors


# --- INVALID_DISPATCH_FORM -------------------------------------------------------------------


def test_all_three_dispatch_forms_reports_invalid_dispatch_form(
    templates: FakeTemplateVersionRepository,
) -> None:
    """skill + prompt + prompt_file together → exactly one INVALID_DISPATCH_FORM."""
    errors = read("invalid-dispatch-form-zero", templates)

    dispatch_errors = [e for e in errors if e.reason == INVALID_DISPATCH_FORM]
    assert len(dispatch_errors) == 1


def test_zero_dispatch_forms_produces_no_invalid_dispatch_form(
    templates: FakeTemplateVersionRepository,
) -> None:
    """Zero dispatch forms is valid: agent steps used for non-story dispatches carry only
    harness/model and must not be rejected."""
    text = (
        "name: a\nversion: 1\nsteps:\n"
        "  - id: b\n    uses: agent\n    with:\n"
        "      harness: claude\n      model: claude-opus-5\n"
        "    gate: liveness\n"
    )
    errors = validate(text, templates=templates).errors

    assert not any(e.reason == INVALID_DISPATCH_FORM for e in errors)


def test_skill_and_prompt_together_reports_invalid_dispatch_form(
    templates: FakeTemplateVersionRepository,
) -> None:
    """Two dispatch forms in the same with block → exactly one INVALID_DISPATCH_FORM."""
    errors = read("invalid-dispatch-form-multiple", templates)

    dispatch_errors = [e for e in errors if e.reason == INVALID_DISPATCH_FORM]
    assert len(dispatch_errors) == 1


def test_prompt_and_prompt_file_together_reports_invalid_dispatch_form(
    templates: FakeTemplateVersionRepository,
) -> None:
    """prompt + prompt_file is also two dispatch forms."""
    text = (
        "name: a\nversion: 1\nsteps:\n"
        "  - id: b\n    uses: agent\n    with:\n"
        "      harness: claude\n      prompt: Do X.\n      prompt_file: plan.md\n"
        "    gate: liveness\n"
    )
    errors = validate(text, templates=templates).errors

    dispatch_errors = [e for e in errors if e.reason == INVALID_DISPATCH_FORM]
    assert len(dispatch_errors) == 1


def test_skill_alone_produces_no_invalid_dispatch_form(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The positive case: skill alone is valid."""
    text = (
        "name: a\nversion: 1\nsteps:\n"
        "  - id: b\n    uses: agent\n    with:\n"
        "      harness: claude\n      skill: bmad-build-auto\n"
        "    gate: liveness\n"
    )
    errors = validate(text, templates=templates).errors

    assert not any(e.reason == INVALID_DISPATCH_FORM for e in errors)


def test_prompt_alone_produces_no_invalid_dispatch_form(
    templates: FakeTemplateVersionRepository,
) -> None:
    """prompt alone is valid."""
    text = (
        "name: a\nversion: 1\nsteps:\n"
        "  - id: b\n    uses: agent\n    with:\n"
        "      harness: claude\n      prompt: Do X.\n"
        "    gate: liveness\n"
    )
    errors = validate(text, templates=templates).errors

    assert not any(e.reason == INVALID_DISPATCH_FORM for e in errors)


def test_prompt_file_alone_produces_no_invalid_dispatch_form(
    templates: FakeTemplateVersionRepository,
) -> None:
    """prompt_file alone is valid."""
    text = (
        "name: a\nversion: 1\nsteps:\n"
        "  - id: b\n    uses: agent\n    with:\n"
        "      harness: claude\n      prompt_file: plan.md\n"
        "    gate: liveness\n"
    )
    errors = validate(text, templates=templates).errors

    assert not any(e.reason == INVALID_DISPATCH_FORM for e in errors)


# --- ALL_DIGIT_STEP_ID -----------------------------------------------------------------------


def test_all_digit_step_id_reports_the_dedicated_reason(
    templates: FakeTemplateVersionRepository,
) -> None:
    """An id like "1" triggers ALL_DIGIT_STEP_ID, not INVALID_SLUG."""
    errors = read("all-digit-step-id", templates)

    assert any(e.reason == ALL_DIGIT_STEP_ID for e in errors)


def test_all_digit_step_id_does_not_also_report_invalid_slug(
    templates: FakeTemplateVersionRepository,
) -> None:
    """The `continue` in _check_ids prevents both errors for the same id."""
    errors = read("all-digit-step-id", templates)

    digit_lines = {e.line for e in errors if e.reason == ALL_DIGIT_STEP_ID}
    slug_lines = {e.line for e in errors if e.reason == INVALID_SLUG}
    # no line carries both reasons
    assert not digit_lines & slug_lines


def test_all_digit_step_id_is_reported_at_line_4(
    templates: FakeTemplateVersionRepository,
) -> None:
    errors = read("all-digit-step-id", templates)

    digit_errors = [e for e in errors if e.reason == ALL_DIGIT_STEP_ID]
    assert len(digit_errors) == 1
    assert digit_errors[0].line == ALL_DIGIT_STEP_LINE


def test_integer_step_id_reports_invalid_slug(
    templates: FakeTemplateVersionRepository,
) -> None:
    """An unquoted integer id (YAML int, not str) is not a string: INVALID_SLUG fires."""
    text = (
        "name: a\nversion: 1\nsteps:\n"
        "  - id: 1\n    uses: shell\n    with:\n      command: make test\n"
        "    gate: green\n"
    )
    errors = validate(text, templates=templates).errors

    assert any(e.reason == INVALID_SLUG for e in errors)
    assert not any(e.reason == ALL_DIGIT_STEP_ID for e in errors)
