"""The top-level `type` key: `interactive | auto`, default `auto` (story 1, epic 3, 2026-11-23)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.application.format_schemas import workflow_schema
from orchestrator.application.templates.keys import check_keys
from orchestrator.application.templates.model import INVALID_VALUE
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.application.templates import parsed, reasons
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HEAD = "name: story\nversion: 1\n"
SHELL = (
    "steps:\n  - id: verify\n    uses: shell\n    with:\n      command: make test\n"
    "    gate: deterministic\n"
)
TEMPLATES_DIR = Path(__file__).resolve().parents[5] / "templates"
TYPE_LINE = 3


def run(text: str):  # type: ignore[no-untyped-def]
    return validate(text, templates=FakeTemplateVersionRepository())


def test_interactive_is_accepted_and_parsed() -> None:
    result = run(HEAD + "type: interactive\n" + SHELL)
    assert result.errors == ()
    assert result.template is not None
    assert result.template.type == "interactive"


@pytest.mark.parametrize(("line", "expected"), [("", "auto"), ("type: auto\n", "auto")])
def test_absent_or_auto_is_auto(line: str, expected: str) -> None:
    result = run(HEAD + line + SHELL)
    assert result.errors == ()
    assert result.template is not None
    assert result.template.type == expected


def test_unknown_value_is_refused_at_the_type_line() -> None:
    text = HEAD + "type: manual\n" + SHELL
    result = run(text)
    assert result.template is None
    assert len(result.errors) == 1
    record = result.errors[0]
    assert record.reason == INVALID_VALUE
    assert text.splitlines()[record.line - 1] == "type: manual"


@pytest.mark.parametrize("value", ["[auto]", "1", "null"])
def test_non_text_value_is_refused_without_raising(value: str) -> None:
    errors, _ = check_keys(parsed(HEAD + f"type: {value}\n" + SHELL))
    assert reasons(errors) == [INVALID_VALUE]
    assert errors[0].line == TYPE_LINE


def test_every_file_in_the_templates_folder_is_auto() -> None:
    repo = FakeTemplateVersionRepository()
    texts = {path.stem: path.read_text() for path in sorted(TEMPLATES_DIR.glob("*.yaml"))}
    assert texts
    clock = FakeClock()
    for number, (name, text) in enumerate(texts.items()):
        repo.add(
            TemplateVersion(
                name=name, version=1, yaml=text, hash=f"sha-{number}", created_at=clock.now()
            )
        )
    for name, text in texts.items():
        result = validate(text, templates=repo)
        assert result.errors == (), name
        assert result.template is not None
        assert result.template.type == "auto", name


def test_schema_admits_type_and_does_not_require_it() -> None:
    schema = workflow_schema()
    assert schema["properties"]["type"] == {"enum": ["auto", "interactive"]}
    assert "type" not in schema["required"]
