"""`ProjectRead.trajectory_count` (SPEC CAP-6, UX-DR12): the count *Export trajectories*
reads on the Project screen.

A file of its own, not an addition to `test_project_schemas.py` — anchors are read-only
(root `AGENTS.md` hard rule 1); this is new coverage for a new field, not a revision of an
existing assertion. `trajectory_count` is nullable in the schema for the same reason
`builtin` is (`api/schemas/projects.py`'s own docstring): a defaulted *non-nullable* field
is still `required` in the generated TypeScript, and two frozen web-client fixtures
(`newwf-state.test.ts`, `newwf-fields.test.ts`) construct `ProjectRead` object literals that
predate this field — this test proves the backend half of that: a `ProjectRead` built the
way those frozen tests build one (no `trajectory_count` key at all) still validates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from orchestrator.api.schemas.projects import ProjectRead
from orchestrator.domain.entities.project import ProjectView

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


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


def test_trajectory_count_defaults_to_zero_when_not_given() -> None:
    read = ProjectRead.of(a_view())

    assert read.trajectory_count == 0


def test_trajectory_count_carries_the_value_given() -> None:
    given_count = 3

    read = ProjectRead.of(a_view(), trajectory_count=given_count)

    assert read.trajectory_count == given_count


def test_a_project_read_built_without_the_field_still_validates() -> None:
    """The shape the frozen web-client `ProjectRead` fixtures build (`newwf-state.test.ts`):
    no `trajectory_count` key at all. Nullable, so pydantic does not require one."""
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

    assert read.trajectory_count is None


def test_trajectory_count_is_never_null_once_rendered_through_of() -> None:
    body = ProjectRead.of(a_view()).model_dump()

    assert body["trajectory_count"] == 0
