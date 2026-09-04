"""The payload rules, and the `errors[]` entry each refusal becomes.

Every row of the story's I/O matrix that is about payload *shape* is here. What matters is
not only that a bad payload is refused but where the refusal points: `api/errors.py` renders
a pydantic `loc` as `errors[].path`, and 2.5 puts the message beside the field that path
names. A rule enforced in the wrong place would still answer 422 — with nothing to attach
the message to.

The hostile-text rows are the Schemathesis gate's: a NUL character and a lone surrogate are
both valid JSON and both raise inside psycopg. They have to be refused here, as a 422, or
they leave as a 500.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from orchestrator.api.schemas.common import StorableText
from orchestrator.api.schemas.projects import (
    CONTEXT_PATH_REASON,
    DUPLICATE_ENV_REASON,
    NAME_MAX_LENGTH,
    EnvVarCreate,
    EnvVarIn,
    MaskedEnvVarOut,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)
from orchestrator.domain.entities.project import (
    ENV_NAME_REASON,
    RESERVED_ENV_REASON,
    MaskedEnvVar,
    ProjectView,
)
from orchestrator.domain.ids import new_id

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


class Text(BaseModel):
    value: StorableText


def locations(error: ValidationError) -> list[tuple[Any, ...]]:
    return [entry["loc"] for entry in error.errors()]


def reasons(error: ValidationError) -> list[str]:
    return [entry["msg"] for entry in error.errors()]


# ── text the database can hold ───────────────────────────────────────────────


def test_ordinary_text_is_stored_as_it_arrived() -> None:
    assert Text(value="Ünïcode — fine 🎯").value == "Ünïcode — fine 🎯"


def test_a_nul_character_is_refused_before_the_database_sees_it() -> None:
    """psycopg raises on it; a 500 here is exactly what the Schemathesis gate catches."""
    with pytest.raises(ValidationError, match="NUL"):
        Text(value="before\x00after")


def test_an_unpaired_surrogate_is_refused_before_the_database_sees_it() -> None:
    with pytest.raises(ValidationError, match="surrogate"):
        Text(value="before\ud800after")


@pytest.mark.parametrize("field", ["name", "context_text"])
def test_hostile_text_in_any_project_field_is_a_422_not_a_500(field: str) -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(**{"name": "ok", field: "x\x00y"})

    assert locations(refusal.value) == [(field,)]


def test_hostile_text_in_a_context_path_names_its_index() -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(name="ok", context_paths=["fine.md", "bad\x00.md"])

    assert locations(refusal.value) == [("context_paths", 1)]


def test_hostile_text_in_a_variable_value_names_its_index() -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(name="ok", env_vars=[{"name": "A", "value": "bad\ud800"}])

    assert locations(refusal.value) == [("env_vars", 0, "value")]


# ── the variable-name rules ──────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["api_url", "1ABC", "A-B", "", "a"])
def test_a_malformed_variable_name_names_the_rule_and_the_field(name: str) -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(name="ok", env_vars=[{"name": name, "value": "x"}])

    assert locations(refusal.value) == [("env_vars", 0, "name")]
    assert ENV_NAME_REASON in reasons(refusal.value)[0]
    assert "^[A-Z][A-Z0-9_]*$" in reasons(refusal.value)[0]


@pytest.mark.parametrize(
    "name",
    [
        "GITHUB_TOKEN",
        "LITELLM_API_KEY",
        "LITELLM_SPEND_KEY",
        "LANGFUSE_SECRET_KEY",
        "ORCHESTRATOR_TOKEN",
    ],
)
def test_a_reserved_variable_name_is_refused_with_the_stated_reason(name: str) -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(name="ok", env_vars=[{"name": name, "value": "x"}])

    assert locations(refusal.value) == [("env_vars", 0, "name")]
    assert RESERVED_ENV_REASON in reasons(refusal.value)[0]


def test_the_index_in_the_path_is_the_offending_entry() -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(
            name="ok",
            env_vars=[{"name": "A", "value": "x"}, {"name": "bad", "value": "y"}],
        )

    assert locations(refusal.value) == [("env_vars", 1, "name")]


def test_two_entries_with_the_same_name_are_refused() -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(
            name="ok", env_vars=[{"name": "A", "value": "x"}, {"name": "A", "value": "y"}]
        )

    assert locations(refusal.value) == [("env_vars",)]
    assert DUPLICATE_ENV_REASON in reasons(refusal.value)[0]


def test_a_duplicate_is_refused_on_an_update_too() -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectUpdate(name="ok", env_vars=[{"name": "A"}, {"name": "A"}])

    assert DUPLICATE_ENV_REASON in reasons(refusal.value)[0]


# ── what each write requires ─────────────────────────────────────────────────


def test_a_create_requires_every_value() -> None:
    """A brand-new Project stores nothing, so there is nothing an entry could keep."""
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(name="ok", env_vars=[{"name": "A"}])

    assert locations(refusal.value) == [("env_vars", 0, "value")]


def test_an_update_makes_the_value_optional() -> None:
    """This is how a form that was never given the secret sends the set back intact."""
    payload = ProjectUpdate(name="ok", env_vars=[{"name": "A"}])

    assert payload.env_vars[0].value is None


def test_a_project_needs_a_name() -> None:
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(name="")

    assert locations(refusal.value) == [("name",)]


def test_a_name_of_the_full_allowed_length_is_accepted() -> None:
    assert len(ProjectCreate(name="n" * NAME_MAX_LENGTH).name) == NAME_MAX_LENGTH


@pytest.mark.parametrize("model", [ProjectCreate, ProjectUpdate])
def test_a_name_past_the_bound_is_refused_before_the_index_sees_it(
    model: type[ProjectCreate],
) -> None:
    """A btree entry has a size limit; a generated name past it would be a 500, not a 409."""
    with pytest.raises(ValidationError) as refusal:
        model(name="n" * (NAME_MAX_LENGTH + 1))

    assert locations(refusal.value) == [("name",)]


# ── context paths are repo-relative ──────────────────────────────────────────


@pytest.mark.parametrize("path", ["docs/a.md", "README.md", "a/b/c/d.md", "docs/.hidden.md"])
def test_a_relative_path_inside_the_clone_is_accepted(path: str) -> None:
    assert ProjectCreate(name="ok", context_paths=[path]).context_paths == [path]


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "/", "../secrets.md", "docs/../../out.md", "..", "", "   "],
    ids=["absolute", "root", "leading-parent", "inner-parent", "bare-parent", "empty", "blank"],
)
def test_a_path_that_is_not_repo_relative_is_refused_with_its_index(path: str) -> None:
    """The agent step resolves these against the worktree; none of them lands inside it."""
    with pytest.raises(ValidationError) as refusal:
        ProjectCreate(name="ok", context_paths=["fine.md", path])

    assert locations(refusal.value) == [("context_paths", 1)]
    assert CONTEXT_PATH_REASON in reasons(refusal.value)[0]


def test_the_same_rule_applies_on_an_update() -> None:
    with pytest.raises(ValidationError):
        ProjectUpdate(name="ok", context_paths=["../out.md"])


def test_surrounding_whitespace_is_trimmed_rather_than_stored() -> None:
    assert ProjectCreate(name="ok", context_paths=["  docs/a.md  "]).context_paths == ["docs/a.md"]


def test_the_context_is_optional_and_defaults_to_nothing() -> None:
    payload = ProjectCreate(name="ok")

    assert payload.context_text == ""
    assert payload.context_paths == []
    assert payload.env_vars == []


@pytest.mark.parametrize("model", [ProjectCreate, ProjectUpdate])
def test_an_unknown_field_is_ignored_rather_than_refused(model: type[ProjectCreate]) -> None:
    """The default; asserted so a later story sees it if it changes the convention."""
    assert model(name="ok", nonsense=1).name == "ok"  # type: ignore[call-arg]


# ── the draft the router hands to the use case ───────────────────────────────


def test_an_omitted_switch_is_carried_through_as_unstated() -> None:
    """The schema does not resolve it: a create and an update resolve it differently."""
    assert ProjectCreate(name="ok").as_draft().log_prompt_content is None
    assert ProjectUpdate(name="ok").as_draft().log_prompt_content is None


@pytest.mark.parametrize("model", [ProjectCreate, ProjectUpdate])
@pytest.mark.parametrize("chosen", [False, True])
def test_a_stated_switch_is_carried_through_as_itself(
    model: type[ProjectCreate], chosen: bool
) -> None:
    draft = model(name="ok", log_prompt_content=chosen).as_draft()

    assert draft.log_prompt_content is chosen


def test_the_create_draft_carries_every_value() -> None:
    draft = ProjectCreate(
        name="My Website",
        context_text="read this",
        context_paths=["docs/a.md"],
        env_vars=[{"name": "A", "value": "x"}],
    ).as_draft()

    assert draft.name == "My Website"
    assert draft.context_text == "read this"
    assert draft.context_paths == ("docs/a.md",)
    assert [(v.name, v.value) for v in draft.env_vars] == [("A", "x")]


def test_the_update_draft_carries_a_keep_as_a_missing_value() -> None:
    draft = ProjectUpdate(name="ok", env_vars=[{"name": "A"}]).as_draft()

    assert [(v.name, v.value) for v in draft.env_vars] == [("A", None)]


# ── the read model ───────────────────────────────────────────────────────────


def a_view(**overrides: object) -> ProjectView:
    fields: dict[str, object] = {
        "id": new_id(),
        "slug": "my-website",
        "name": "My Website",
        "context_text": "read this",
        "context_paths": ("docs/a.md",),
        "env_vars": (MaskedEnvVar(name="TOKEN_A", masked="••••efgh"),),
        "log_prompt_content": False,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return ProjectView(**fields)  # type: ignore[arg-type]


def test_the_read_model_renders_the_use_cases_view() -> None:
    view = a_view()

    read = ProjectRead.of(view)

    assert read.id == view.id
    assert read.slug == "my-website"
    assert read.context_paths == ["docs/a.md"]
    assert read.env_vars == [MaskedEnvVarOut(name="TOKEN_A", masked="••••efgh")]


def test_the_read_model_has_no_field_a_value_could_travel_in() -> None:
    """Whatever a router passes, no serialisation of this model can carry a secret."""
    assert set(MaskedEnvVarOut.model_fields) == {"name", "masked"}
    assert "value" not in ProjectRead.model_fields
    assert "env_vars_enc" not in ProjectRead.model_fields


def test_the_timestamps_leave_as_the_z_form_every_list_in_this_api_uses() -> None:
    body = ProjectRead.of(a_view()).model_dump()

    assert body["created_at"] == "2026-09-04T12:00:00Z"
    assert body["updated_at"] == "2026-09-04T12:00:00Z"


def test_the_id_leaves_as_a_uuid() -> None:
    assert isinstance(ProjectRead.of(a_view()).id, UUID)


def test_the_two_variable_shapes_share_one_name_rule() -> None:
    """`EnvVarCreate` differs from `EnvVarIn` in one field, and inherits everything else."""
    assert issubclass(EnvVarCreate, EnvVarIn)
    for model in (EnvVarIn, EnvVarCreate):
        with pytest.raises(ValidationError):
            model(name="lower", value="x")
