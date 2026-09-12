"""`ProjectRead` monthly spend fields (story 8-6): `monthly_spend_usd`,
`monthly_spend_provisional`, `needs_you_count`, `failed_recent_count`.

A file of its own, not an addition to `test_project_schemas.py` or
`test_project_schemas_trajectory_count.py` — anchors are read-only (root AGENTS.md hard
rule 1); this is new coverage for new fields, not a revision of existing assertions.

The four fields are nullable for the same reason `trajectory_count` is: a defaulted
*non-nullable* field is still `required` in the generated TypeScript, and frozen
web-client fixtures that predate this story construct `ProjectRead` object literals without
these keys — this test proves the backend half of that guarantee.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from orchestrator.api.schemas.projects import ProjectRead
from orchestrator.domain.entities.project import ProjectView

AT = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)

THREE_NEEDS_YOU = 3
TWO_FAILED = 2


def a_view(**overrides: object) -> ProjectView:
    fields: dict[str, object] = {
        "id": UUID(int=1),
        "slug": "my-website",
        "name": "My website",
        "context_text": "",
        "context_paths": (),
        "env_vars": (),
        "log_prompt_content": False,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return ProjectView(**fields)  # type: ignore[arg-type]


# ── defaults via of() ─────────────────────────────────────────────────────────


def test_monthly_spend_usd_defaults_to_zero_string() -> None:
    read = ProjectRead.of(a_view())

    assert read.monthly_spend_usd == "0.00"


def test_monthly_spend_provisional_defaults_to_false() -> None:
    read = ProjectRead.of(a_view())

    assert read.monthly_spend_provisional is False


def test_needs_you_count_defaults_to_zero() -> None:
    read = ProjectRead.of(a_view())

    assert read.needs_you_count == 0


def test_failed_recent_count_defaults_to_zero() -> None:
    read = ProjectRead.of(a_view())

    assert read.failed_recent_count == 0


# ── values pass through of() ──────────────────────────────────────────────────


def test_monthly_spend_usd_carries_the_value_given() -> None:
    read = ProjectRead.of(a_view(), monthly_spend_usd="12.30")

    assert read.monthly_spend_usd == "12.30"


def test_monthly_spend_provisional_carries_true() -> None:
    read = ProjectRead.of(a_view(), monthly_spend_provisional=True)

    assert read.monthly_spend_provisional is True


def test_needs_you_count_carries_the_value_given() -> None:
    read = ProjectRead.of(a_view(), needs_you_count=THREE_NEEDS_YOU)

    assert read.needs_you_count == THREE_NEEDS_YOU


def test_failed_recent_count_carries_the_value_given() -> None:
    read = ProjectRead.of(a_view(), failed_recent_count=TWO_FAILED)

    assert read.failed_recent_count == TWO_FAILED


# ── nullable for frozen-fixture compatibility ─────────────────────────────────


def test_project_read_built_without_the_four_fields_still_validates() -> None:
    """The shape frozen web-client fixtures build: no monthly spend keys at all.
    Nullable, so pydantic does not require them."""
    read = ProjectRead(
        id=UUID(int=1),
        slug="my-website",
        name="My website",
        context_text="",
        context_paths=[],
        env_vars=[],
        log_prompt_content=False,
        repositories=[],
        runs=[],
        created_at=AT,
        updated_at=AT,
    )  # type: ignore[call-arg]

    assert read.monthly_spend_usd is None
    assert read.monthly_spend_provisional is None
    assert read.needs_you_count is None
    assert read.failed_recent_count is None


def test_four_fields_are_never_null_once_rendered_through_of() -> None:
    body = ProjectRead.of(a_view()).model_dump()

    assert body["monthly_spend_usd"] == "0.00"
    assert body["monthly_spend_provisional"] is False
    assert body["needs_you_count"] == 0
    assert body["failed_recent_count"] == 0
