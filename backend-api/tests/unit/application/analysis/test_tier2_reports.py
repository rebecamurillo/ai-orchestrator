"""Tier 2 parsers on inline fixture texts (epic 6 story 1)."""

from __future__ import annotations

import pytest

from orchestrator.application.analysis.tier2_reports import (
    Case,
    CoverageLines,
    Diagnostic,
    ReportUnreadable,
    coverage_of,
    is_import_error,
    new_diagnostics,
    parse_coverage,
    parse_diagnostics,
    parse_junit,
)

FOUR = 4
COBERTURA = """<coverage><packages><package><classes>
<class filename="src/a.py"><lines><line number="1" hits="2"/>
<line number="2" hits="0"/></lines></class>
<class filename="src/a.py"><lines><line number="2" hits="1"/></lines></class>
</classes></package></packages></coverage>"""
JACOCO = """<report><package name="com/x"><sourcefile name="A.java">
<line nr="3" mi="0" ci="2"/><line nr="4" mi="1" ci="0"/></sourcefile></package></report>"""


def test_a_ruff_line_with_a_column() -> None:
    assert parse_diagnostics("src/a.py:3:1: E1 unused", "/r") == [
        Diagnostic("src/a.py", "E1 unused")
    ]


def test_a_mypy_line_without_a_column_and_its_note_skipped() -> None:
    out = "src/a.py:3: error: bad\nsrc/a.py:3: note: see\nnoise\n"
    assert parse_diagnostics(out, "/r") == [Diagnostic("src/a.py", "error: bad")]


def test_a_tsc_line() -> None:
    out = "src/x.ts(3,5): error TS2322: nope"
    assert parse_diagnostics(out, "/r") == [Diagnostic("src/x.ts", "error TS2322: nope")]


def test_an_absolute_path_is_stripped_of_the_checkout_root() -> None:
    out = "/w/base/src/a.py:1:1: m\n./b.py:2:2: n"
    assert parse_diagnostics(out, "/w/base") == [
        Diagnostic("src/a.py", "m"),
        Diagnostic("b.py", "n"),
    ]


def test_new_diagnostics_is_a_multiset_difference_through_renames() -> None:
    base = [Diagnostic("src/a.py", "E1"), Diagnostic("src/b.py", "W2")]
    head = [
        Diagnostic("src/c.py", "E1"),
        Diagnostic("src/b.py", "W2"),
        Diagnostic("src/b.py", "W3"),
    ]
    assert new_diagnostics(base, head, {"src/a.py": "src/c.py"}) == 1
    assert new_diagnostics(base, base, {}) == 0
    assert new_diagnostics([], head + head[:1], {}) == FOUR


def test_cobertura_lines_are_merged_per_file() -> None:
    assert parse_coverage(COBERTURA).lines == {"src/a.py": {1: True, 2: True}}


def test_jacoco_lines() -> None:
    assert parse_coverage(JACOCO).lines == {"com/x/A.java": {3: True, 4: False}}


@pytest.mark.parametrize(
    "text",
    [
        "<!DOCTYPE x><coverage/>",
        "<!ENTITY a 'b'>",
        "<coverage",
        "<other/>",
        '<coverage><class><line number="1" hits="1"/></class></coverage>',
        '<coverage><class filename="a"><line number="x" hits="1"/></class></coverage>',
    ],
)
def test_unreadable_coverage_is_refused(text: str) -> None:
    with pytest.raises(ReportUnreadable):
        parse_coverage(text)


def test_coverage_of_matches_by_suffix_and_counts_missing_files() -> None:
    report = CoverageLines({"a.py": {1: True, 2: False}})
    added = {"src/a.py": frozenset({1, 2, 3}), "src/b.py": frozenset({1, 2})}
    assert coverage_of(report, added) == (1, 2, 2)
    assert coverage_of(CoverageLines({"src/a.py": {1: True}}), {"src/a.py": frozenset({1})}) == (
        1,
        1,
        0,
    )


def test_junit_with_testsuites_file_on_case_and_on_suite() -> None:
    text = """<testsuites><testsuite file="s.py">
<testcase classname="c" name="a" file="t.py"/>
<testcase classname="c" name="b"><failure message="boom"/></testcase>
<testcase classname="c" name="c"><error>ModuleNotFoundError: x
more</error></testcase>
<testcase classname="c" name="d"><skipped/></testcase>
</testsuite></testsuites>"""
    cases = parse_junit(text)
    assert cases == [
        Case("t.py", "c", "a", "passed", ""),
        Case("s.py", "c", "b", "failed", "boom"),
        Case("s.py", "c", "c", "error", "ModuleNotFoundError: x"),
        Case("s.py", "c", "d", "skipped", "skipped"),
    ]
    assert [is_import_error(c) for c in cases] == [False, False, True, False]


def test_junit_ignores_children_that_are_not_outcomes() -> None:
    text = "<testsuite><testcase name='a'><system-out>x</system-out></testcase></testsuite>"
    assert parse_junit(text)[0].outcome == "passed"


def test_junit_single_testsuite_without_attributes() -> None:
    assert parse_junit("<testsuite><testcase/></testsuite>") == [Case(None, "", "", "passed", "")]


def test_a_pytest_collection_error_is_an_import_error() -> None:
    text = (
        '<testsuite><testcase name="t"><error message="collection failure"/></testcase></testsuite>'
    )
    assert is_import_error(parse_junit(text)[0])


def test_junit_with_a_doctype_is_refused() -> None:
    with pytest.raises(ReportUnreadable):
        parse_junit("<!DOCTYPE a><testsuite/>")
