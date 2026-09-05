"""The Project's own rules, in the one place every layer reads them from.

The API restates them as pydantic validators, the use cases enforce them again over stored
state, and the database indexes two of them. Each of those is a copy; this module asserts
the original, so a drift is a failure here and not a surprise in the browser.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.domain.entities.project import (
    ENV_NAME_PATTERN,
    MASK_PREFIX,
    RESERVED_ENV_REASON,
    SLUG_FALLBACK,
    SLUG_MAX_LENGTH,
    EncryptedEnvVar,
    MaskedEnvVar,
    Project,
    ProjectView,
    is_reserved_env_name,
    is_valid_env_name,
    mask,
    numbered_slug,
    slugify,
)
from orchestrator.domain.ids import new_id

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def a_project(**overrides: object) -> Project:
    fields: dict[str, object] = {
        "id": new_id(),
        "slug": "my-website",
        "name": "My Website",
        "context_text": "",
        "context_paths": (),
        "env_vars_enc": (),
        "log_prompt_content": False,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Project(**fields)  # type: ignore[arg-type]


# ── the variable-name rule ───────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["A", "API_URL", "TOKEN_A", "A1", "A_1_B"])
def test_a_shell_exportable_name_is_accepted(name: str) -> None:
    assert is_valid_env_name(name)


@pytest.mark.parametrize("name", ["api_url", "1ABC", "A-B", "", "_A", "Ab", "A B", "Á"])
def test_a_name_the_shell_cannot_export_is_refused(name: str) -> None:
    assert not is_valid_env_name(name)


def test_the_pattern_is_anchored_at_both_ends() -> None:
    """`re.match` alone would accept `A-B` on the strength of its first character."""
    assert ENV_NAME_PATTERN.pattern.startswith("^")
    assert ENV_NAME_PATTERN.pattern.endswith("$")


# ── the reserved names (AD-5) ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "GITHUB_TOKEN",
        "LITELLM_API_KEY",
        "LITELLM_SPEND_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_BASE_URL",
        "ORCHESTRATOR_TOKEN",
        "ORCHESTRATOR_SECRET_KEY",
    ],
)
def test_an_instance_setting_is_not_a_project_variable(name: str) -> None:
    assert is_reserved_env_name(name)


@pytest.mark.parametrize("name", ["API_URL", "LITELLM_MODEL", "LANGFUSE", "ORCHESTRATOR"])
def test_a_name_that_only_looks_like_one_is_a_project_variable(name: str) -> None:
    """The prefixes carry a trailing underscore; `LANGFUSE` alone is nobody's setting."""
    assert not is_reserved_env_name(name)


def test_the_reason_is_stated_once_so_every_layer_says_the_same_thing() -> None:
    assert RESERVED_ENV_REASON == "instance setting, not a project variable"


# ── masking ──────────────────────────────────────────────────────────────────


def test_a_long_value_shows_only_its_last_four_characters() -> None:
    assert mask("abcdefgh") == f"{MASK_PREFIX}efgh"


@pytest.mark.parametrize("value", ["", "a", "ab", "abc"])
def test_a_value_shorter_than_four_shows_nothing_of_itself(value: str) -> None:
    assert mask(value) == MASK_PREFIX


def test_a_mask_never_contains_the_head_of_the_value() -> None:
    secret = "super-secret-token"

    assert secret not in mask(secret)
    assert mask(secret) == f"{MASK_PREFIX}oken"


# ── the slug ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("My Website 2!", "my-website-2"),
        ("My Website", "my-website"),
        ("  leading and trailing  ", "leading-and-trailing"),
        ("double--dash", "double-dash"),
        ("UPPER", "upper"),
        ("a/b\\c", "a-b-c"),
        ("2026", "2026"),
    ],
)
def test_a_name_becomes_the_slug_the_work_directory_uses(name: str, expected: str) -> None:
    assert slugify(name) == expected


@pytest.mark.parametrize("name", ["!!!", "   ", "", "———", "日本語"])
def test_a_name_with_no_slug_characters_falls_back(name: str) -> None:
    assert slugify(name) == SLUG_FALLBACK


def test_a_long_name_is_truncated_and_leaves_no_dangling_separator() -> None:
    slug = slugify("a" * 39 + " bbbb")

    assert len(slug) <= SLUG_MAX_LENGTH
    assert not slug.endswith("-")
    assert slug == "a" * 39


@pytest.mark.parametrize("name", ["My Website 2!", "x" * 100, "!!!"])
def test_a_slug_is_always_within_the_alphabet_a_directory_name_allows(name: str) -> None:
    slug = slugify(name)

    assert 0 < len(slug) <= SLUG_MAX_LENGTH
    assert all(character.isascii() for character in slug)
    assert set(slug) <= set("abcdefghijklmnopqrstuvwxyz0123456789-")
    assert "--" not in slug


def test_a_collision_is_numbered() -> None:
    assert numbered_slug("my-website", 2) == "my-website-2"
    assert numbered_slug("my-website", 3) == "my-website-3"


def test_a_numbered_slug_shortens_the_base_rather_than_dropping_the_number() -> None:
    """Dropping the suffix would produce exactly the slug the number exists to avoid."""
    numbered = numbered_slug("a" * SLUG_MAX_LENGTH, 12)

    assert len(numbered) <= SLUG_MAX_LENGTH
    assert numbered.endswith("-12")


def test_a_numbered_slug_of_an_all_separator_base_still_names_something() -> None:
    assert numbered_slug("-", 2) == f"{SLUG_FALLBACK}-2"


# ── the entity and its read model ────────────────────────────────────────────


def test_a_project_is_frozen() -> None:
    """Every mutation goes through a use case, which writes a new entity and commits."""
    project = a_project()

    with pytest.raises(ValueError, match="frozen"):
        project.name = "other"  # type: ignore[misc]


@pytest.mark.parametrize("model", [EncryptedEnvVar, MaskedEnvVar, ProjectView])
def test_every_project_model_is_frozen(model: type) -> None:
    assert model.model_config["frozen"] is True


def test_the_read_model_carries_masks_and_no_value() -> None:
    project = a_project(
        env_vars_enc=(
            EncryptedEnvVar(name="API_URL", value_enc="ciphertext-one"),
            EncryptedEnvVar(name="TOKEN_A", value_enc="ciphertext-two"),
        )
    )

    view = project.view({"API_URL": "https://x", "TOKEN_A": "abcdefgh"})

    assert view.env_vars == (
        MaskedEnvVar(name="API_URL", masked=f"{MASK_PREFIX}://x"),
        MaskedEnvVar(name="TOKEN_A", masked=f"{MASK_PREFIX}efgh"),
    )
    assert "value_enc" not in view.model_dump()


def test_the_read_model_masks_the_plaintext_and_not_the_ciphertext() -> None:
    """A mask over the ciphertext would show four characters the Operator never typed."""
    project = a_project(env_vars_enc=(EncryptedEnvVar(name="TOKEN_A", value_enc="Z" * 120),))

    view = project.view({"TOKEN_A": "abcdefgh"})

    assert view.env_vars[0].masked == f"{MASK_PREFIX}efgh"


def test_the_read_model_keeps_the_rest_of_the_project() -> None:
    project = a_project(context_text="read this", context_paths=("docs/a.md",))

    view = project.view({})

    assert (view.id, view.slug, view.name) == (project.id, project.slug, project.name)
    assert view.context_text == "read this"
    assert view.context_paths == ("docs/a.md",)
    assert view.log_prompt_content is False
    assert (view.created_at, view.updated_at) == (AT, AT)


def test_the_stored_entity_carries_no_field_a_plaintext_could_travel_in() -> None:
    """`Project` has one place for a value, and a token is what goes in it.

    The plaintext is put through `view()` in the same test, so it exists in this test's
    scope and the assertion below can genuinely fail: if the entity ever gained a field
    that held it — a cached value, a `masked` mirror — this is where it would appear.
    """
    plaintext = "s3cr3t-abcdefgh"
    project = a_project(env_vars_enc=(EncryptedEnvVar(name="TOKEN_A", value_enc="gAAAAA-token"),))

    project.view({"TOKEN_A": plaintext})

    assert "gAAAAA-token" in project.model_dump_json()
    assert plaintext not in project.model_dump_json()
    assert set(EncryptedEnvVar.model_fields) == {"name", "value_enc"}


def test_a_view_never_serialises_the_plaintext_it_was_masked_from() -> None:
    """The masked read model is what leaves; only four characters of the value survive it."""
    plaintext = "s3cr3t-abcdefgh"
    project = a_project(env_vars_enc=(EncryptedEnvVar(name="TOKEN_A", value_enc="gAAAAA-token"),))

    rendered = project.view({"TOKEN_A": plaintext}).model_dump_json()

    assert plaintext not in rendered
    assert "gAAAAA-token" not in rendered
    assert mask(plaintext) in rendered
