"""PyYAML fails with more than `YAMLError` on ordinary typos; the loaders answer "no
document" and `validate()` reports `invalid yaml` at line 1 (story 4, AD-26, D13)."""

from __future__ import annotations

import pytest

from orchestrator.application.templates.lines import load_sequence, load_with_lines
from orchestrator.application.templates.validate import validate
from tests.unit.fakes.templates import FakeTemplateVersionRepository

TYPO_TEXTS = [
    "[" * 5000,
    "x: 2026-02-30",
    "x: !!int 0x",
    "x: !!int",
    "x: !!float",
    "x: !!bool",
    "x: !!bool maybe",
    "x: !!timestamp",
    "x: !!timestamp foo",
]


@pytest.mark.parametrize("text", TYPO_TEXTS, ids=lambda t: t[:18])
def test_the_document_loader_reports_no_document_at_line_one(text: str) -> None:
    loaded = load_with_lines(text)

    assert loaded.root is None
    assert loaded.line == 1


@pytest.mark.parametrize("text", TYPO_TEXTS, ids=lambda t: t[:18])
def test_validate_returns_invalid_yaml_instead_of_raising(text: str) -> None:
    result = validate(text, templates=FakeTemplateVersionRepository())

    assert [(e.line, e.reason) for e in result.errors] == [(1, "invalid yaml")]


def test_the_sequence_loader_reads_such_a_list_as_no_list() -> None:
    assert load_sequence("- x: 2026-02-30") is None
    assert load_sequence("- x: 1") is not None
