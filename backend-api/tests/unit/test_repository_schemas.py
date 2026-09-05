"""The Repository payload rules, and the `errors[]` entry each refusal becomes.

The story's I/O-matrix rows that are about payload *shape*: a missing required field, an
invalid glob naming its index, and hostile text a `text` column cannot hold. The use-case
rules — the `test_globs` merge over stored state, the duplicate-url conflict, the slug — are
asserted in `tests/unit/test_repositories_use_cases.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.projects import RepositoryCreate, RepositoryOut, RepositoryUpdate
from orchestrator.domain.entities.repository import DEFAULT_TEST_GLOBS, CloneCheck, Repository
from orchestrator.domain.ids import new_id
from orchestrator.domain.rules.globs import GLOB_REASON

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def locations(error: ValidationError) -> list[tuple[object, ...]]:
    return [entry["loc"] for entry in error.errors()]


def reasons(error: ValidationError) -> list[str]:
    return [entry["msg"] for entry in error.errors()]


# ── what a create requires ────────────────────────────────────────────────────


def test_a_create_requires_a_url() -> None:
    with pytest.raises(ValidationError) as refusal:
        RepositoryCreate(default_branch="main")  # type: ignore[call-arg]

    assert locations(refusal.value) == [("url",)]


def test_a_create_requires_a_default_branch() -> None:
    with pytest.raises(ValidationError) as refusal:
        RepositoryCreate(url="https://x/org/repo.git")  # type: ignore[call-arg]

    assert locations(refusal.value) == [("default_branch",)]


@pytest.mark.parametrize("field", ["url", "default_branch"])
@pytest.mark.parametrize("model", [RepositoryCreate, RepositoryUpdate])
def test_an_empty_required_field_is_refused(model: type[RepositoryCreate], field: str) -> None:
    payload = {"url": "https://x/org/repo.git", "default_branch": "main", field: ""}

    with pytest.raises(ValidationError) as refusal:
        model(**payload)  # type: ignore[arg-type]

    assert locations(refusal.value) == [(field,)]


def test_a_minimal_create_needs_nothing_else() -> None:
    payload = RepositoryCreate(url="https://x/org/repo.git", default_branch="main")

    assert payload.test_globs == []
    assert payload.package_manager == "other"
    assert payload.install_command == ""
    assert payload.quality_gate_command == ""
    assert payload.unit_test_command == ""


# ── globs ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("glob", ["/abs/**", "../x", "tests/../x", ""])
def test_an_invalid_glob_names_its_index(glob: str) -> None:
    with pytest.raises(ValidationError) as refusal:
        RepositoryCreate(
            url="https://x/org/repo.git",
            default_branch="main",
            test_globs=["fine/**", glob],
        )

    assert locations(refusal.value) == [("test_globs", 1)]
    assert GLOB_REASON in reasons(refusal.value)[0]


def test_the_same_glob_rule_applies_on_an_update() -> None:
    with pytest.raises(ValidationError):
        RepositoryUpdate(
            url="https://x/org/repo.git", default_branch="main", test_globs=["/abs/**"]
        )


def test_a_valid_glob_is_accepted() -> None:
    payload = RepositoryCreate(
        url="https://x/org/repo.git", default_branch="main", test_globs=["e2e/**"]
    )

    assert payload.test_globs == ["e2e/**"]


# ── hostile text ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "field",
    ["url", "default_branch", "install_command", "quality_gate_command", "unit_test_command"],
)
def test_hostile_text_in_any_field_is_a_422_not_a_500(field: str) -> None:
    payload: dict[str, object] = {"url": "https://x/org/repo.git", "default_branch": "main"}
    payload[field] = "before\x00after"

    with pytest.raises(ValidationError) as refusal:
        RepositoryCreate(**payload)  # type: ignore[arg-type]

    assert locations(refusal.value) == [(field,)]


def test_hostile_text_in_a_glob_names_its_index() -> None:
    with pytest.raises(ValidationError) as refusal:
        RepositoryCreate(
            url="https://x/org/repo.git",
            default_branch="main",
            test_globs=["fine/**", "bad\x00.py"],
        )

    assert locations(refusal.value) == [("test_globs", 1)]


# ── package_manager ──────────────────────────────────────────────────────────


def test_an_unknown_package_manager_is_refused() -> None:
    with pytest.raises(ValidationError) as refusal:
        RepositoryCreate(
            url="https://x/org/repo.git", default_branch="main", package_manager="poetry"
        )

    assert locations(refusal.value) == [("package_manager",)]


@pytest.mark.parametrize("manager", ["uv", "pnpm", "npm", "yarn", "pip", "cargo", "go", "other"])
def test_every_supported_package_manager_is_accepted(manager: str) -> None:
    payload = RepositoryCreate(
        url="https://x/org/repo.git", default_branch="main", package_manager=manager
    )

    assert payload.package_manager == manager


# ── the draft the router hands to the use case ────────────────────────────────


def test_the_create_draft_carries_every_value() -> None:
    draft = RepositoryCreate(
        url="https://x/org/repo.git",
        default_branch="develop",
        install_command="npm ci",
        quality_gate_command="make lint test",
        unit_test_command="npm test",
        test_globs=["e2e/**"],
        package_manager="npm",
    ).as_draft()

    assert draft.url == "https://x/org/repo.git"
    assert draft.default_branch == "develop"
    assert draft.install_command == "npm ci"
    assert draft.quality_gate_command == "make lint test"
    assert draft.unit_test_command == "npm test"
    assert draft.test_globs == ("e2e/**",)
    assert draft.package_manager == "npm"


def test_the_update_draft_carries_every_value_too() -> None:
    draft = RepositoryUpdate(url="https://x/org/repo.git", default_branch="main").as_draft()

    assert draft.url == "https://x/org/repo.git"
    assert draft.default_branch == "main"
    assert draft.test_globs == ()


@pytest.mark.parametrize("model", [RepositoryCreate, RepositoryUpdate])
def test_an_unknown_field_is_ignored_rather_than_refused(model: type[RepositoryCreate]) -> None:
    """The default; asserted so a later story sees it if it changes the convention."""
    payload = model(url="https://x/org/repo.git", default_branch="main", nonsense=1)  # type: ignore[call-arg]

    assert payload.url == "https://x/org/repo.git"


# ── the read model ───────────────────────────────────────────────────────────


def a_repository(**overrides: object) -> Repository:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "slug": "my-repo",
        "url": "https://x/org/repo.git",
        "default_branch": "main",
        "install_command": "",
        "quality_gate_command": "",
        "unit_test_command": "",
        "test_globs": DEFAULT_TEST_GLOBS,
        "package_manager": "other",
        "clone_check": CloneCheck.pending(),
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


def test_verify_skipped_is_derived_true_with_no_quality_gate_command() -> None:
    out = RepositoryOut.of(a_repository())

    assert out.verify_skipped is True


def test_verify_skipped_is_derived_false_once_a_quality_gate_command_is_set() -> None:
    out = RepositoryOut.of(a_repository(quality_gate_command="make lint test"))

    assert out.verify_skipped is False


def test_the_read_model_carries_the_pending_clone_check() -> None:
    out = RepositoryOut.of(a_repository())

    assert out.clone_check.status == "pending"
    assert out.clone_check.at is None
    assert out.clone_check.output == ""
    assert out.clone_check.bmad_version is None


def test_the_read_model_carries_a_finished_clone_check_too() -> None:
    out = RepositoryOut.of(
        a_repository(clone_check=CloneCheck(status="ok", at=AT, output="ok", bmad_version="6.1.0"))
    )

    assert out.clone_check.status == "ok"
    assert out.clone_check.at == AT
    assert out.clone_check.bmad_version == "6.1.0"


def test_the_timestamps_leave_as_the_z_form() -> None:
    body = RepositoryOut.of(a_repository()).model_dump()

    assert body["created_at"] == "2026-09-04T12:00:00Z"
    assert body["updated_at"] == "2026-09-04T12:00:00Z"


def test_the_test_globs_leave_as_a_plain_list() -> None:
    out = RepositoryOut.of(a_repository(test_globs=(*DEFAULT_TEST_GLOBS, "e2e/**")))

    assert out.test_globs == [*DEFAULT_TEST_GLOBS, "e2e/**"]
