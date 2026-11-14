"""The class of a changed path (ARCHITECTURE §7.8).

First match wins, in `PRECEDENCE` order: the declaration's globs, then `generated_or_artefact`,
`test_e2e`, `test_unit`, `test_unclassified`, `docs`, `configuration`, else `production`.
The pattern lists, their order and the lock-file list are method parameters of the catalogue
entries; a change to any of them is a new method version.

Matching rule. A convention pattern with no `/` matches the basename. A convention pattern
with a `/` matches the path or any suffix of it that starts at a segment, so `tests/e2e/**`
matches `web-client/tests/e2e/a.spec.ts`. `HUB_PATTERNS` and the declaration's globs match
the whole repository-relative path only.
"""

from __future__ import annotations

from collections.abc import Iterable
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from typing import Literal

from orchestrator.application.analysis.declaration import Declaration

FileClass = Literal[
    "test_e2e",
    "test_unit",
    "generated_or_artefact",
    "test_unclassified",
    "docs",
    "configuration",
    "production",
]

#: The conventions in the order they are tried, after the declaration's own globs.
PRECEDENCE: tuple[FileClass, ...] = (
    "generated_or_artefact",
    "test_e2e",
    "test_unit",
    "test_unclassified",
    "docs",
    "configuration",
    "production",
)
LOCK_FILES = ("*.lock", "package-lock.json", "pnpm-lock.yaml", "npm-shrinkwrap.json", "go.sum")
GENERATED_PATTERNS = (
    "_bmad-output/**",
    "dist/**",
    "build/**",
    "*.min.js",
    "**/schema.d.ts",
    "contracts/openapi.json",
    *LOCK_FILES,
)
HUB_PATTERNS = ("initiatives/**", "planning/**")
E2E_PATTERNS = ("tests/e2e/**", "e2e/**", "*.e2e.*", "playwright/**")
UNIT_PATTERNS = ("*.test.*", "*.spec.*", "test_*.py", "*_test.py", "*_test.go", "tests/unit/**")
UNCLASSIFIED_PATTERNS = ("tests/**", "test/**")
DOCS_PATTERNS = ("*.md", "docs/**")
CONFIGURATION_PATTERNS = (
    "*.json",
    "*.yaml",
    "*.yml",
    "*.toml",
    "*.ini",
    ".env*",
    "Dockerfile*",
    "Makefile",
)


def _whole(path: str, patterns: Iterable[str]) -> bool:
    posix = PurePosixPath(path)
    return any(posix.full_match(pattern) for pattern in patterns)


def _convention(path: str, patterns: Iterable[str]) -> bool:
    segments = PurePosixPath(path).parts
    suffixes = [PurePosixPath(*segments[start:]) for start in range(len(segments))]
    for pattern in patterns:
        if "/" not in pattern:
            if fnmatchcase(segments[-1], pattern):
                return True
        elif any(suffix.full_match(pattern) for suffix in suffixes):
            return True
    return False


#: After the declaration and the hub rule: each class with its convention patterns, in order.
CONVENTIONS: tuple[tuple[FileClass, tuple[str, ...]], ...] = (
    ("generated_or_artefact", GENERATED_PATTERNS),
    ("test_e2e", E2E_PATTERNS),
    ("test_unit", UNIT_PATTERNS),
    ("test_unclassified", UNCLASSIFIED_PATTERNS),
    ("docs", DOCS_PATTERNS),
    ("configuration", CONFIGURATION_PATTERNS),
)


def _declared(path: str, declaration: Declaration) -> FileClass | None:
    if _whole(path, declaration.tests_e2e):
        return "test_e2e"
    return "test_unit" if _whole(path, declaration.tests_unit) else None


def classify(path: str, declaration: Declaration, *, hub: bool) -> FileClass:
    declared = _declared(path, declaration)
    if declared is not None:
        return declared
    if hub and _whole(path, HUB_PATTERNS):
        return "generated_or_artefact"
    for file_class, patterns in CONVENTIONS:
        if _convention(path, patterns):
            return file_class
    return "production"
