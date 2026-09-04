"""The Repository's own rules: the slug from its URL, the default test globs it always
protects, and the property that says whether anything verifies a Run's work in it.

The API restates the glob and package-manager shapes as pydantic validators, and the use
cases enforce the merge and the slug-collision rule again over stored state; this module
asserts the originals.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.domain.entities.repository import (
    DEFAULT_PACKAGE_MANAGER,
    DEFAULT_TEST_GLOBS,
    CloneCheck,
    Repository,
    merge_test_globs,
    repo_slug,
)
from orchestrator.domain.ids import new_id

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def a_repository(**overrides: object) -> Repository:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "slug": "my-repo",
        "url": "https://github.com/org/my-repo.git",
        "default_branch": "main",
        "install_command": "",
        "quality_gate_command": "",
        "unit_test_command": "",
        "test_globs": DEFAULT_TEST_GLOBS,
        "package_manager": DEFAULT_PACKAGE_MANAGER,
        "clone_check": CloneCheck.pending(),
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


# ── the slug ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/org/my-repo.git", "my-repo"),
        ("https://github.com/org/my-repo", "my-repo"),
        ("git@github.com:org/My Repo.git", "my-repo"),
        ("https://github.com/org/repo/", "repo"),
    ],
)
def test_the_slug_is_derived_from_the_urls_last_segment(url: str, expected: str) -> None:
    assert repo_slug(url) == expected


# ── the default test globs ────────────────────────────────────────────────────


def test_the_defaults_are_exactly_the_three_the_brief_states() -> None:
    assert DEFAULT_TEST_GLOBS == ("tests/**", "**/*.test.*", "**/*.spec.*")


def test_merging_nothing_still_protects_the_defaults() -> None:
    assert merge_test_globs(()) == DEFAULT_TEST_GLOBS


def test_an_operator_glob_is_appended_after_the_defaults() -> None:
    assert merge_test_globs(["e2e/**"]) == (*DEFAULT_TEST_GLOBS, "e2e/**")


def test_a_duplicate_of_a_default_is_not_repeated() -> None:
    assert merge_test_globs(["tests/**", "e2e/**"]) == (*DEFAULT_TEST_GLOBS, "e2e/**")


def test_order_is_preserved_and_duplicates_among_operator_globs_collapse() -> None:
    assert merge_test_globs(["e2e/**", "e2e/**", "spec/**"]) == (
        *DEFAULT_TEST_GLOBS,
        "e2e/**",
        "spec/**",
    )


# ── clone_check ────────────────────────────────────────────────────────────────


def test_a_new_clone_check_is_pending_with_nothing_else_stated() -> None:
    check = CloneCheck.pending()

    assert check.status == "pending"
    assert check.at is None
    assert check.output == ""
    assert check.bmad_version is None


def test_clone_check_is_frozen() -> None:
    check = CloneCheck.pending()

    with pytest.raises(ValueError, match="frozen"):
        check.status = "ok"  # type: ignore[misc]


def test_a_clone_check_can_hold_a_finished_result() -> None:
    """2.3's `run_clone_check` is what writes this; the shape has to accept it."""
    check = CloneCheck(status="ok", at=AT, output="ok", bmad_version="6.1.0")

    assert (check.status, check.at, check.output, check.bmad_version) == (
        "ok",
        AT,
        "ok",
        "6.1.0",
    )


# ── verify_skipped ───────────────────────────────────────────────────────────


def test_verify_skipped_is_true_with_no_quality_gate_command() -> None:
    assert a_repository(quality_gate_command="").verify_skipped is True


def test_verify_skipped_is_false_once_a_quality_gate_command_is_set() -> None:
    assert a_repository(quality_gate_command="make lint test").verify_skipped is False


def test_verify_skipped_is_true_for_a_whitespace_only_quality_gate_command() -> None:
    """A command that is only whitespace declares nothing runnable — not a real gate."""
    assert a_repository(quality_gate_command="   ").verify_skipped is True


# ── the entity itself ─────────────────────────────────────────────────────────


def test_a_repository_is_frozen() -> None:
    repository = a_repository()

    with pytest.raises(ValueError, match="frozen"):
        repository.url = "other"  # type: ignore[misc]


def test_the_package_manager_defaults_to_other() -> None:
    assert a_repository().package_manager == "other"
    assert DEFAULT_PACKAGE_MANAGER == "other"
