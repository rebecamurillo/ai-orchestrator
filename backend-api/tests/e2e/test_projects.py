"""The Project round-trip against the running stack — the claims only a database settles.

The unit suite proves the rules over fakes: encryption, masking, the keep/replace/delete
semantics of `PUT`, the conflict and the 404. What it cannot prove is that any of it
survives a real schema — that `jsonb` keeps the order the Operator typed, that the unique
indexes exist, that a `timestamptz` comes back with its zone, and that the ciphertext a
`text` column stored is byte-identical to the one that went in.

There is no `DELETE` in this story, so every run leaves its Projects behind. Names are
therefore made unique per run: a suite that could only pass on an empty database would fail
the second time it was run against the same stack, which is not a property of the code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from orchestrator.infrastructure.db import create_engine_from
from orchestrator.infrastructure.settings import Settings

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROJECTS = "/api/v1/projects"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"

MASK = "••••"
URL_VALUE = "https://example.invalid/hook"
SECRET_VALUE = "s3cr3t-abcdefgh"


@pytest.fixture
def unique_name() -> str:
    """A name no earlier run of this suite can have taken."""
    return f"e2e project {uuid4()}"


def at(iso: str) -> datetime:
    """Parse before comparing: `_iso_z` drops a zero fraction, so `12:00:00Z` sorts after
    `12:00:00.5Z` as a string. Two timestamps are only ordered as timestamps."""
    return datetime.fromisoformat(iso)


def created_id(response: httpx.Response) -> str:
    """The new Project's id, with the status asserted first.

    Reading `["id"]` off a refusal raises `KeyError` and hides which call actually failed.
    """
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["id"])


def create(client: httpx.Client, name: str, **overrides: Any) -> httpx.Response:
    payload: dict[str, Any] = {
        "name": name,
        "context_text": "the context every agent reads",
        "context_paths": ["docs/a.md", "README.md"],
        "env_vars": [
            {"name": "API_URL", "value": URL_VALUE},
            {"name": "TOKEN_A", "value": SECRET_VALUE},
        ],
    }
    payload.update(overrides)
    return client.post(PROJECTS, json=payload)


def test_a_project_round_trips_through_the_database(
    authenticated: httpx.Client, unique_name: str
) -> None:
    """create → get → list → update, against a real schema and a real Fernet key."""
    created = create(authenticated, unique_name)
    assert created.status_code == HTTP_CREATED, created.text
    body = created.json()
    identifier = body["id"]

    # the create answered with masks, and the order the payload had
    assert body["env_vars"] == [
        {"name": "API_URL", "masked": f"{MASK}{URL_VALUE[-4:]}"},
        {"name": "TOKEN_A", "masked": f"{MASK}{SECRET_VALUE[-4:]}"},
    ]
    assert body["context_paths"] == ["docs/a.md", "README.md"]
    assert body["created_at"].endswith("Z")

    read = authenticated.get(f"{PROJECTS}/{identifier}")
    assert read.status_code == HTTP_OK
    assert read.json() == body

    listed = authenticated.get(PROJECTS)
    assert listed.status_code == HTTP_OK
    page = listed.json()
    assert set(page) == {"items", "next_cursor"}
    assert page["next_cursor"] is None
    assert body in page["items"]

    updated = authenticated.put(
        f"{PROJECTS}/{identifier}",
        json={
            "name": f"{unique_name} renamed",
            "context_text": "changed",
            "context_paths": [],
            "env_vars": [{"name": "API_URL"}, {"name": "NEW_ONE", "value": "wxyz"}],
        },
    )
    assert updated.status_code == HTTP_OK, updated.text
    after = updated.json()

    # kept, added, dropped — and the slug and creation time untouched
    assert [variable["name"] for variable in after["env_vars"]] == ["API_URL", "NEW_ONE"]
    assert after["env_vars"][0]["masked"] == f"{MASK}{URL_VALUE[-4:]}"
    assert after["slug"] == body["slug"]
    assert after["created_at"] == body["created_at"]
    assert at(after["updated_at"]) > at(body["updated_at"])
    assert after["context_paths"] == []


def test_the_list_is_ordered_by_name(authenticated: httpx.Client, unique_name: str) -> None:
    """Two names that differ only by a suffix, so the claim holds under any collation.

    The order is the database's `ORDER BY name`, and a database sorts by its collation
    rather than by codepoint — which is why this asserts the relative position of two names
    it controls instead of comparing the whole page against a Python `sorted()`.
    """
    create(authenticated, f"{unique_name} b")
    create(authenticated, f"{unique_name} a")

    names = [item["name"] for item in authenticated.get(PROJECTS).json()["items"]]

    assert names.index(f"{unique_name} a") < names.index(f"{unique_name} b")


def test_a_kept_value_still_decrypts_after_the_round_trip(
    authenticated: httpx.Client, unique_name: str
) -> None:
    """The mask is over the plaintext, so an unchanged mask means the ciphertext survived."""
    identifier = created_id(create(authenticated, unique_name))

    authenticated.put(
        f"{PROJECTS}/{identifier}",
        json={"name": unique_name, "env_vars": [{"name": "TOKEN_A"}]},
    )
    read = authenticated.get(f"{PROJECTS}/{identifier}")

    assert read.json()["env_vars"] == [{"name": "TOKEN_A", "masked": f"{MASK}{SECRET_VALUE[-4:]}"}]


def test_no_response_body_ever_carries_a_plaintext_value(
    authenticated: httpx.Client, unique_name: str
) -> None:
    """The claim this story exists for, asserted against the deployed process (AD-5)."""
    created = create(authenticated, unique_name)
    identifier = created_id(created)

    responses = [
        created,
        authenticated.get(f"{PROJECTS}/{identifier}"),
        authenticated.get(PROJECTS),
        authenticated.put(
            f"{PROJECTS}/{identifier}",
            json={"name": unique_name, "env_vars": [{"name": "TOKEN_A"}]},
        ),
    ]

    for response in responses:
        assert SECRET_VALUE not in response.text, response.url
        assert URL_VALUE not in response.text, response.url


def test_a_duplicate_name_is_refused_by_the_stack(
    authenticated: httpx.Client, unique_name: str
) -> None:
    create(authenticated, unique_name)

    second = create(authenticated, unique_name)

    assert second.status_code == HTTP_CONFLICT
    assert second.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert second.json()["title"] == "conflict"


def test_two_projects_whose_names_share_a_slug_both_land(
    authenticated: httpx.Client, unique_name: str
) -> None:
    """The slug is uniquely indexed; a collision has to be numbered, not refused."""
    first = create(authenticated, unique_name)
    second = create(authenticated, unique_name.upper())

    assert second.status_code == HTTP_CREATED, second.text
    assert second.json()["slug"] != first.json()["slug"]
    # the base is shortened to make room for the suffix, so the number is never dropped
    assert second.json()["slug"].endswith("-2")


def test_an_unknown_id_is_a_problem_document(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{PROJECTS}/{UNKNOWN_ID}")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_an_id_that_is_not_a_uuid_is_refused_before_the_database(
    authenticated: httpx.Client,
) -> None:
    response = authenticated.get(f"{PROJECTS}/not-a-uuid")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_a_reserved_variable_name_is_refused_with_a_path(
    authenticated: httpx.Client, unique_name: str
) -> None:
    response = create(authenticated, unique_name, env_vars=[{"name": "GITHUB_TOKEN", "value": "x"}])

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["errors"][0]["path"] == "body.env_vars.0.name"


def test_text_the_database_cannot_hold_is_a_422_and_not_a_500(
    authenticated: httpx.Client, unique_name: str
) -> None:
    """A NUL character raises inside psycopg; the schema refuses it first."""
    response = create(authenticated, f"{unique_name}\x00")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_every_project_operation_needs_the_bearer(client: httpx.Client) -> None:
    for method, path in (
        ("get", PROJECTS),
        ("post", PROJECTS),
        ("get", f"{PROJECTS}/{UNKNOWN_ID}"),
        ("put", f"{PROJECTS}/{UNKNOWN_ID}"),
    ):
        response = client.request(method, path)

        assert response.status_code == HTTP_UNAUTHORIZED, f"{method} {path}"


# ── the schema the migration was written to create ───────────────────────────


@pytest.fixture(scope="module")
def project_indexes(stack: str) -> dict[str, bool]:
    """`{index name: is unique}` for the `project` table, read from the migrated database.

    The unit suite asserts the two unique indexes against `Base.metadata`, which the model
    populates — the migration file is not involved in that answer at all. Deleting both
    `create_index` calls from `0002_project.py` would leave every one of those assertions
    green. This reads what `alembic upgrade head` actually built, at the one boundary where
    it has run, in the same shape `tests/e2e/test_migrations.py` reads `alembic_version`.
    """
    settings = Settings()
    engine = create_engine_from(settings)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "select i.relname, x.indisunique from pg_index x "
                    "join pg_class i on i.oid = x.indexrelid "
                    "join pg_class t on t.oid = x.indrelid "
                    "join pg_namespace n on n.oid = t.relnamespace "
                    "where t.relname = 'project' and n.nspname = 'public'"
                )
            )
            return {name: bool(unique) for name, unique in rows}
    finally:
        engine.dispose()


@pytest.mark.parametrize("index", ["ix_project_name", "ix_project_slug"])
def test_the_migration_created_the_index_the_model_declares(
    project_indexes: dict[str, bool], index: str
) -> None:
    assert index in project_indexes, sorted(project_indexes)


@pytest.mark.parametrize("index", ["ix_project_name", "ix_project_slug"])
def test_that_index_is_unique_and_not_merely_present(
    project_indexes: dict[str, bool], index: str
) -> None:
    """Uniqueness is the guarantee: two concurrent creates, only one row (AD-14 `/work`)."""
    assert project_indexes[index] is True
