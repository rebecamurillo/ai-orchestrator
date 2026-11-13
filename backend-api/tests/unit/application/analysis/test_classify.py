"""File classes: precedence, patterns and the matching rule (story 5.1, AC8-AC13)."""

from __future__ import annotations

import pytest

from orchestrator.application.analysis.classify import (
    LOCK_FILES,
    PRECEDENCE,
    FileClass,
    classify,
)
from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION, Declaration


def declared(**over: object) -> Declaration:
    return Declaration(**{**DEFAULT_DECLARATION.__dict__, **over})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("web-client/tests/e2e/a.spec.ts", "test_e2e"),
        ("e2e/login.spec.ts", "test_e2e"),
        ("src/login.e2e.ts", "test_e2e"),
        ("playwright/a.ts", "test_e2e"),
        ("web-client/src/x.test.ts", "test_unit"),
        ("src/x.spec.tsx", "test_unit"),
        ("backend-api/tests/unit/test_x.py", "test_unit"),
        ("pkg/test_x.py", "test_unit"),
        ("pkg/x_test.py", "test_unit"),
        ("pkg/x_test.go", "test_unit"),
        ("tests/helpers.py", "test_unclassified"),
        ("test/helpers.py", "test_unclassified"),
        ("package-lock.json", "generated_or_artefact"),
        ("web-client/pnpm-lock.yaml", "generated_or_artefact"),
        ("backend-api/uv.lock", "generated_or_artefact"),
        ("go.sum", "generated_or_artefact"),
        ("npm-shrinkwrap.json", "generated_or_artefact"),
        ("contracts/openapi.json", "generated_or_artefact"),
        ("web-client/src/api/schema.d.ts", "generated_or_artefact"),
        ("app.min.js", "generated_or_artefact"),
        ("_bmad-output/x.md", "generated_or_artefact"),
        ("web/dist/a.js", "generated_or_artefact"),
        ("build/a.js", "generated_or_artefact"),
        ("web-client/tsconfig.json", "configuration"),
        ("Makefile", "configuration"),
        (".env.example", "configuration"),
        ("Dockerfile.prod", "configuration"),
        ("a/b.toml", "configuration"),
        ("README.md", "docs"),
        ("docs/setup.yaml", "docs"),
        ("src/app.py", "production"),
        ("initiatives/foo/SPEC.md", "docs"),
    ],
)
def test_a_path_has_its_class(path: str, expected: FileClass) -> None:
    assert classify(path, DEFAULT_DECLARATION, hub=False) == expected


def test_hub_folders_are_generated_only_in_a_hub() -> None:
    assert classify("initiatives/foo/SPEC.md", DEFAULT_DECLARATION, hub=True) == (
        "generated_or_artefact"
    )
    assert classify("planning/x.md", DEFAULT_DECLARATION, hub=True) == "generated_or_artefact"
    assert classify("sub/initiatives/x.md", DEFAULT_DECLARATION, hub=True) == "docs"


def test_the_declaration_beats_every_convention() -> None:
    unit = declared(tests_unit=("dist/**/*.js",))
    assert classify("dist/a.js", unit, hub=False) == "test_unit"
    e2e = declared(tests_e2e=("src/**/*.test.ts",), tests_unit=("src/**/*.ts",))
    assert classify("src/a/b.test.ts", e2e, hub=False) == "test_e2e"
    assert classify("src/a/c.ts", e2e, hub=False) == "test_unit"


def test_declared_globs_match_the_whole_path_only() -> None:
    unit = declared(tests_unit=("checks/*.py",))
    assert classify("checks/a.py", unit, hub=False) == "test_unit"
    assert classify("sub/checks/a.py", unit, hub=False) == "production"


def test_a_spec_file_under_e2e_is_e2e() -> None:
    assert classify("e2e/a.spec.ts", DEFAULT_DECLARATION, hub=False) == "test_e2e"


def test_a_pattern_without_a_slash_matches_the_basename_at_any_depth() -> None:
    assert classify("a/b/c/x.test.ts", DEFAULT_DECLARATION, hub=False) == "test_unit"


def test_the_precedence_and_lock_files_are_method_parameters() -> None:
    assert PRECEDENCE[0] == "generated_or_artefact"
    assert PRECEDENCE[-1] == "production"
    assert len(set(PRECEDENCE)) == len(PRECEDENCE) == 7  # noqa: PLR2004
    assert "go.sum" in LOCK_FILES and "*.lock" in LOCK_FILES
