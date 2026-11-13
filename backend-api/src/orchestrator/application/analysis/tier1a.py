"""Tier 1a counts: offline signals read from the numstat, the name-status and the diff text.

Every pattern list is a parameter of its catalogue entry; a change to one is a new method
version. Literal patterns match as substrings of an added line, `TYPE_ESCAPE_PATTERNS` as
regular expressions. A line counts once per signal however many patterns it matches.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from typing import Literal

from orchestrator.application.analysis.classify import LOCK_FILES, PRECEDENCE, FileClass, classify
from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION, Declaration
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry

SUPPRESSION_PATTERNS = (
    "eslint-disable",
    "@ts-ignore",
    "@ts-nocheck",
    "# noqa",
    "# type: ignore",
    "//nolint",
    "@SuppressWarnings",
    "# pylint: disable",
    "#[allow(",
)
TYPE_ESCAPE_PATTERNS = (
    r": any\b",
    r"as any\b",
    r"<any>",
    r"as unknown as",
    r"@ts-expect-error",
    r"typing\.Any",
    r"cast\(Any",
    r"interface\{\}",
)
SKIP_FOCUS_PATTERNS = (
    ".skip(",
    ".only(",
    "xit(",
    "xdescribe(",
    "fit(",
    "fdescribe(",
    "@pytest.mark.skip",
    "@pytest.mark.xfail",
    "t.Skip(",
    "@Disabled",
    "@Ignore",
)
TEST_CASE_OPENERS = ("it(", "test(", "def test_", "async def test_", "func Test", "@Test")
MANIFEST_FILES = (
    "package.json",
    "pyproject.toml",
    "requirements*.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle*",
)

TEST_CLASSES: tuple[FileClass, ...] = ("test_unit", "test_e2e", "test_unclassified")
KINDS = ("added", "modified", "deleted")
_TYPE_ESCAPES = tuple(re.compile(pattern) for pattern in TYPE_ESCAPE_PATTERNS)
_HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
_ESCAPES = {"n": 10, "t": 9, "a": 7, "b": 8, "f": 12, "r": 13, "v": 11, '"': 34, "\\": 92}
_OCTAL = re.compile(r"[0-7]{3}")
_KIND_OF = {"A": "added", "C": "added", "M": "modified", "T": "modified", "R": "modified"}


@dataclass(frozen=True)
class Count:
    """One figure; `rate` names the class of added lines it is rated against, if any."""

    metric_id: str
    source: str | None
    value: int
    rate: Literal["production", "test"] | None
    combine: Literal["sum", "max"] = "sum"


def _unquote(text: str) -> str:
    """A C-quoted path as git prints one: escapes and octal bytes, decoded as UTF-8."""
    body = text[1:-1]
    out = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out += char.encode()
            index += 1
        elif _OCTAL.fullmatch(body[index + 1 : index + 4]):
            out.append(int(body[index + 1 : index + 4], 8))
            index += 4
        else:
            out.append(_ESCAPES.get(body[index + 1], ord(body[index + 1])))
            index += 2
    return out.decode(errors="replace")


def _head_path(header: str) -> str | None:
    """The path after `+++ `; `None` for `/dev/null`."""
    raw = header.removesuffix("\t")
    if raw == "/dev/null":
        return None
    path = _unquote(raw) if raw.startswith('"') else raw
    return path.removeprefix("b/")


def _hunk_lines(lines: list[str], start: int, old: int, new: int) -> tuple[list[str], int]:
    """The added lines of one hunk, read by the counts in its header, and the next index."""
    added: list[str] = []
    index = start
    while (old > 0 or new > 0) and index < len(lines):
        body = lines[index]
        index += 1
        if body.startswith("\\"):
            continue
        if body.startswith("-"):
            old -= 1
        elif body.startswith("+"):
            new -= 1
            added.append(body[1:])
        else:
            old -= 1
            new -= 1
    return added, index


def added_lines(diff_text: str) -> dict[str, tuple[str, ...]]:
    """Head path → the lines the diff adds there.

    Headers are read by state: a line inside a hunk is content whatever it starts with, so an
    added line that begins `++` is still a line. Deleted and binary files have no entry.
    """
    found: dict[str, list[str]] = {}
    lines = diff_text.split("\n")
    path: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if line.startswith("diff --git"):
            path = None
        elif line.startswith("+++ "):
            path = _head_path(line[4:])
        elif (hunk := _HUNK.match(line)) is not None:
            old, new = (int(g) if g is not None else 1 for g in hunk.groups())
            added, index = _hunk_lines(lines, index, old, new)
            if path is not None and added:
                found.setdefault(path, []).extend(added)
    return {key: tuple(value) for key, value in found.items()}


def _basename_matches(path: str, patterns: Sequence[str]) -> bool:
    name = PurePosixPath(path).name
    return any(fnmatchcase(name, pattern) for pattern in patterns)


def _is_test(file_class: FileClass) -> bool:
    return file_class in TEST_CLASSES


def _pattern_counts(
    added: dict[str, tuple[str, ...]], classify_path: dict[str, FileClass]
) -> dict[str, int]:
    totals = {"suppress": 0, "production": 0, "test": 0, "skip": 0, "cases": 0}
    for path, lines in added.items():
        file_class = classify_path[path]
        for line in lines:
            totals["suppress"] += any(p in line for p in SUPPRESSION_PATTERNS)
            totals["skip"] += any(p in line for p in SKIP_FOCUS_PATTERNS)
            totals["cases"] += line.lstrip().startswith(TEST_CASE_OPENERS)
            if any(p.search(line) for p in _TYPE_ESCAPES):
                if file_class == "production":
                    totals["production"] += 1
                elif _is_test(file_class):
                    totals["test"] += 1
    return totals


def count_tier1a(
    numstat: Sequence[NumstatEntry],
    name_status: Sequence[NameStatus],
    diff_text: str,
    declaration: Declaration,
    *,
    hub: bool,
) -> tuple[Count, ...]:
    """Every Tier 1a row, zeros included: a test signal on a diff with no tests is a figure 0."""

    def class_of(path: str) -> FileClass:
        return classify(path, declaration, hub=hub)

    lines_added = dict.fromkeys(PRECEDENCE, 0)
    lines_removed = dict.fromkeys(PRECEDENCE, 0)
    for entry in numstat:
        file_class = class_of(entry.path)
        lines_added[file_class] += entry.added
        lines_removed[file_class] += entry.removed

    touched = dict.fromkeys(KINDS, 0)
    test_files = {f"{c}:{k}": 0 for c in TEST_CLASSES for k in KINDS}
    changed = deleted = 0
    for item in name_status:
        kind = _KIND_OF.get(item.status, "deleted")
        touched[kind] += 1
        head_class = class_of(item.path)
        if _is_test(head_class):
            test_files[f"{head_class}:{kind}"] += 1
        base_path = item.old_path if item.status == "R" and item.old_path else item.path
        if item.status in ("M", "T", "R") and _is_test(class_of(base_path)):
            changed += 1
        if item.status == "D" and _is_test(head_class):
            deleted += 1

    added = added_lines(diff_text)
    patterns = _pattern_counts(added, {path: class_of(path) for path in added})
    manifests = sum(
        _basename_matches(item.path, (*MANIFEST_FILES, *LOCK_FILES)) for item in name_status
    )
    return (
        *(Count("code.lines_added", c, lines_added[c], None) for c in PRECEDENCE),
        *(Count("code.lines_removed", c, lines_removed[c], None) for c in PRECEDENCE),
        *(Count("code.files_touched", k, touched[k], None) for k in KINDS),
        Count("code.suppressions_added", None, patterns["suppress"], "production"),
        Count("code.type_escapes_added", "production", patterns["production"], "production"),
        Count("code.type_escapes_added", "test", patterns["test"], "test"),
        Count("code.skip_focus_markers_added", None, patterns["skip"], "production"),
        Count("code.preexisting_tests_changed", None, changed, "production"),
        Count("code.preexisting_tests_deleted", None, deleted, "production"),
        *(Count("code.test_files", k, v, "production") for k, v in test_files.items()),
        *(
            Count(
                "code.test_lines",
                f"{c}:{d}",
                (lines_added if d == "added" else lines_removed)[c],
                "production",
            )
            for c in TEST_CLASSES
            for d in ("added", "removed")
        ),
        Count("code.test_cases_static", None, patterns["cases"], "production"),
        Count("code.manifest_changes", None, manifests, "production"),
    )


#: Every raw row a repository holds, in order; a repository that did not run holds each as a word.
ROW_KEYS: tuple[tuple[str, str | None], ...] = (
    *((c.metric_id, c.source) for c in count_tier1a((), (), "", DEFAULT_DECLARATION, hub=False)),
    ("code.possible_secrets", None),
)
