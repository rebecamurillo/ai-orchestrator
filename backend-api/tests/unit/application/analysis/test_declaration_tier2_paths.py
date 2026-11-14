"""Declaration report paths (epic 6 story 1, AC8)."""

from __future__ import annotations

import pytest

from orchestrator.application.analysis.declaration import parse_declaration


def test_a_coverage_command_without_its_report_path_is_a_problem() -> None:
    parsed = parse_declaration("tier2: true\ncommands:\n  coverage: make cov\n")
    assert parsed.problems == ("missing key: commands.coverage_report",)
    assert parsed.declaration.commands == {"coverage": "make cov"}


def test_a_test_report_command_without_its_path_is_a_problem() -> None:
    parsed = parse_declaration("commands:\n  test_report: make junit\n")
    assert parsed.problems == ("missing key: commands.test_report_path",)


def test_a_path_without_its_command_is_not_a_problem() -> None:
    parsed = parse_declaration("commands:\n  coverage_report: cov.xml\n")
    assert parsed.problems == ()


def test_declared_pairs_are_clean() -> None:
    text = "commands:\n  coverage: c\n  coverage_report: out/cov.xml\n"
    text += "  test_report: t\n  test_report_path: out/junit.xml\n"
    parsed = parse_declaration(text)
    assert parsed.problems == ()
    assert parsed.declaration.commands["test_report_path"] == "out/junit.xml"


@pytest.mark.parametrize("value", ["/abs/cov.xml", "../cov.xml", "a/../../cov.xml"])
def test_a_path_that_is_not_repository_relative_is_dropped(value: str) -> None:
    text = f"commands:\n  coverage: c\n  coverage_report: {value}\n"
    parsed = parse_declaration(text)
    assert "not repository-relative: commands.coverage_report" in parsed.problems
    assert "missing key: commands.coverage_report" in parsed.problems
    assert "coverage_report" not in parsed.declaration.commands


def test_a_test_report_path_that_is_absolute_is_dropped() -> None:
    parsed = parse_declaration("commands:\n  test_report_path: /x.xml\n")
    assert parsed.problems == ("not repository-relative: commands.test_report_path",)
    assert parsed.declaration.commands == {}
