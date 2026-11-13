"""`orchestrator-analysis.yaml` parsing (story 5.1, AC5-AC7)."""

from __future__ import annotations

import hashlib

from orchestrator.application.analysis.declaration import (
    DECLARATION_FILE,
    DEFAULT_DECLARATION,
    parse_declaration,
)

FULL = """
tests:
  unit: ["a/**"]
  e2e: ["b/**"]
tier2: true
commands:
  install: make install
  lint: make lint
  typecheck: make types
  coverage: make cov
  coverage_report: cov.xml
  test_report: make report
  test_report_path: report.xml
sast:
  rules: p/default
registries:
  npm: https://registry.npmjs.org
"""


def test_the_file_name() -> None:
    assert DECLARATION_FILE == "orchestrator-analysis.yaml"


def test_an_absent_file_is_the_defaults_with_no_hash() -> None:
    parsed = parse_declaration(None)
    assert parsed.declaration == DEFAULT_DECLARATION
    assert parsed.hash is None
    assert parsed.problems == ()
    declaration = parsed.declaration
    assert declaration.tests_unit == () and declaration.tests_e2e == ()
    assert declaration.tier2 is False and declaration.sast_rules is None
    assert not declaration.commands and not declaration.registries


def test_a_full_file_is_parsed_and_hashed() -> None:
    parsed = parse_declaration(FULL)
    declaration = parsed.declaration
    assert parsed.problems == ()
    assert parsed.hash == hashlib.sha256(FULL.encode()).hexdigest()
    assert declaration.tests_unit == ("a/**",)
    assert declaration.tests_e2e == ("b/**",)
    assert declaration.tier2 is True
    assert declaration.commands["install"] == "make install"
    assert declaration.commands["test_report_path"] == "report.xml"
    assert len(declaration.commands) == 7  # noqa: PLR2004
    assert declaration.sast_rules == "p/default"
    assert declaration.registries == {"npm": "https://registry.npmjs.org"}


def test_unknown_keys_are_named_and_known_keys_still_apply() -> None:
    parsed = parse_declaration(
        "foo: 1\ntier2: true\ntests:\n  bar: []\n  unit: [x]\n"
        "commands:\n  foo: x\n  lint: l\nsast:\n  baz: 1\n"
    )
    assert parsed.problems == (
        "unknown key: foo",
        "unknown key: tests.bar",
        "unknown key: commands.foo",
        "unknown key: sast.baz",
    )
    assert parsed.declaration.tier2 is True
    assert parsed.declaration.tests_unit == ("x",)
    assert parsed.declaration.commands == {"lint": "l"}


def test_a_known_key_of_the_wrong_type_is_a_problem_and_its_default() -> None:
    parsed = parse_declaration(
        "tier2: yes please\ntests: [a]\ncommands: {lint: 3}\nsast: {rules: [x]}\nregistries: [a]\n"
    )
    assert parsed.problems == (
        "wrong type: tests",
        "wrong type: commands.lint",
        "wrong type: sast.rules",
        "wrong type: tier2",
        "wrong type: registries",
    )
    assert parsed.declaration == DEFAULT_DECLARATION
    assert parse_declaration("tests: {unit: x, e2e: [1]}\ncommands: []\nsast: x\n").problems == (
        "wrong type: tests.unit",
        "wrong type: tests.e2e",
        "wrong type: commands",
        "wrong type: sast",
    )


def test_unreadable_yaml_is_a_problem_and_the_defaults() -> None:
    parsed = parse_declaration("a: [unclosed")
    assert parsed.declaration == DEFAULT_DECLARATION
    assert parsed.problems[0].startswith("declaration unreadable: ")
    assert parsed.hash == hashlib.sha256(b"a: [unclosed").hexdigest()


def test_nesting_deep_enough_to_overflow_the_parser_is_unreadable() -> None:
    parsed = parse_declaration("[" * 5000)
    assert parsed.declaration == DEFAULT_DECLARATION
    assert parsed.problems[0].startswith("declaration unreadable: ")


def test_a_file_that_is_not_a_mapping_is_a_problem() -> None:
    assert parse_declaration("- a\n").problems == ("wrong type: <document>",)
    assert parse_declaration("").problems == ()
    assert parse_declaration("").declaration == DEFAULT_DECLARATION
