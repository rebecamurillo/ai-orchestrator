"""Tier 2 parsers: linter output, coverage and JUnit reports of the repository's own commands.

Report files are the measured repository's output and are untrusted: a document type
declaration is refused before parsing, so no entity is ever expanded.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

LINE_PATTERN = r"^(?P<path>[^\s:()][^:()]*?):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?P<message>.+)$"
TSC_PATTERN = r"^(?P<path>[^\s()]+)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<message>.+)$"
IMPORT_ERROR_PATTERN = (
    r"ImportError|ModuleNotFoundError|Cannot find module|Failed to (?:load|resolve)"
    r"|error collecting|collection failure"
)
LINE_RE = re.compile(LINE_PATTERN)
TSC_RE = re.compile(TSC_PATTERN)
IMPORT_ERROR = re.compile(IMPORT_ERROR_PATTERN)
FORBIDDEN_MARKUP = ("<!DOCTYPE", "<!ENTITY")
NOTE = "note:"

Outcome = Literal["passed", "failed", "error", "skipped"]
OUTCOME_TAGS: Mapping[str, Outcome] = {"failure": "failed", "error": "error", "skipped": "skipped"}


class ReportUnreadable(ValueError):
    """The report is not XML this module reads."""


@dataclass(frozen=True)
class Diagnostic:
    path: str
    message: str


def _relative(path: str, root: str) -> str:
    path = path.removeprefix(f"{root}/")
    return path.removeprefix("./")


def parse_diagnostics(output: str, root: str) -> list[Diagnostic]:
    """Each `path:line:col: message` or tsc `path(line,col): message` line; a `note:` is skipped."""
    found: list[Diagnostic] = []
    for text in output.splitlines():
        match = LINE_RE.match(text) or TSC_RE.match(text)
        if match is None or match["message"].startswith(NOTE):
            continue
        found.append(Diagnostic(_relative(match["path"], root), match["message"].strip()))
    return found


def new_diagnostics(
    base: list[Diagnostic], head: list[Diagnostic], renames: Mapping[str, str]
) -> int:
    """Head minus base on `(path after renames, message)`; line and column are ignored."""
    before = Counter((renames.get(d.path, d.path), d.message) for d in base)
    after = Counter((d.path, d.message) for d in head)
    return sum((after - before).values())


def _parse_xml(text: str) -> ET.Element:
    if any(marker in text for marker in FORBIDDEN_MARKUP):
        raise ReportUnreadable("document type declarations are refused")
    try:
        return ET.fromstring(text)
    except ET.ParseError as error:
        raise ReportUnreadable(str(error)) from error


@dataclass(frozen=True)
class CoverageLines:
    """Report path → line number → covered."""

    lines: Mapping[str, Mapping[int, bool]]


def _record(lines: dict[str, dict[int, bool]], path: str, number: str, covered: bool) -> None:
    per_file = lines.setdefault(path, {})
    per_file[int(number)] = per_file.get(int(number), False) or covered


def parse_coverage(text: str) -> CoverageLines:
    """A Cobertura (`coverage`) or JaCoCo (`report`) document."""
    root = _parse_xml(text)
    lines: dict[str, dict[int, bool]] = {}
    try:
        if root.tag == "coverage":
            for cls in root.iter("class"):
                for line in cls.iter("line"):
                    _record(
                        lines,
                        cls.attrib["filename"],
                        line.attrib["number"],
                        int(line.attrib["hits"]) > 0,
                    )
        elif root.tag == "report":
            for package in root.iter("package"):
                for source in package.iter("sourcefile"):
                    path = f"{package.attrib['name']}/{source.attrib['name']}"
                    for line in source.iter("line"):
                        _record(lines, path, line.attrib["nr"], int(line.attrib["ci"]) > 0)
        else:
            raise ReportUnreadable(f"not a coverage report: <{root.tag}>")
    except (KeyError, ValueError) as error:
        if isinstance(error, ReportUnreadable):
            raise
        raise ReportUnreadable(f"coverage report malformed: {error}") from error
    return CoverageLines(lines)


def coverage_of(report: CoverageLines, added: Mapping[str, frozenset[int]]) -> tuple[int, int, int]:
    """`(covered, instrumented, not_in_report)` over the added production lines."""
    covered = instrumented = missing = 0
    for path, numbers in added.items():
        match = next(
            (name for name in report.lines if path == name or path.endswith(f"/{name}")), None
        )
        if match is None:
            missing += len(numbers)
            continue
        listed = report.lines[match]
        for number in numbers:
            if number in listed:
                instrumented += 1
                covered += listed[number]
    return covered, instrumented, missing


@dataclass(frozen=True)
class Case:
    file: str | None
    classname: str
    name: str
    outcome: Outcome
    message: str


def _message(child: ET.Element) -> str:
    if child.attrib.get("message"):
        return child.attrib["message"]
    first = (child.text or "").strip().splitlines()[:1]
    return first[0] if first else child.tag


def parse_junit(text: str) -> list[Case]:
    """Every `testcase`; its file from itself or its enclosing `testsuite`."""
    root = _parse_xml(text)
    cases: list[Case] = []
    for suite in root.iter("testsuite"):
        for case in suite.findall("testcase"):
            outcome: Outcome = "passed"
            message = ""
            for child in case:
                if child.tag in OUTCOME_TAGS:
                    outcome, message = OUTCOME_TAGS[child.tag], _message(child)
                    break
            file = case.attrib.get("file") or suite.attrib.get("file")
            cases.append(
                Case(
                    file,
                    case.attrib.get("classname", ""),
                    case.attrib.get("name", ""),
                    outcome,
                    message,
                )
            )
    return cases


def is_import_error(case: Case) -> bool:
    return case.outcome in ("error", "failed") and IMPORT_ERROR.search(case.message) is not None
