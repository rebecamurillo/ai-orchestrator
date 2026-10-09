"""The Repository round-trip against the running stack — the claims only a database settles.

create Project -> add Repository -> get -> list-by-project -> update -> duplicate-url 409 ->
unknown-id 404, plus a `GET /projects/{id}` assertion that `repositories` embeds correctly.
There is no `DELETE`, so every Project and Repository url is made unique per run — the same
reason `tests/e2e/test_projects.py` names its Projects uniquely.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from orchestrator.infrastructure.db import create_engine_from
from orchestrator.infrastructure.settings import Settings

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROJECTS = "/api/v1/projects"
REPOSITORIES = "/api/v1/repositories"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


@pytest.fixture
def project_id(authenticated: httpx.Client) -> str:
    """A fresh Project every Repository in this suite nests under."""
    response = authenticated.post(PROJECTS, json={"name": f"e2e repository project {uuid4()}"})
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["id"])


@pytest.fixture
def unique_url() -> str:
    """A url no earlier run of this suite can have taken."""
    return f"https://example.invalid/{uuid4()}.git"


def repositories_url(project_id: str) -> str:
    return f"{PROJECTS}/{project_id}/repositories"


def create_repository(
    client: httpx.Client, project_id: str, url: str, **overrides: object
) -> httpx.Response:
    payload: dict[str, object] = {"url": url, "default_branch": "main"}
    payload.update(overrides)
    return client.post(repositories_url(project_id), json=payload)


def test_a_repository_round_trips_through_the_database(
    authenticated: httpx.Client, project_id: str, unique_url: str
) -> None:
    """create → get → list → update, against a real schema."""
    created = create_repository(
        authenticated, project_id, unique_url, quality_gate_command="make lint test"
    )
    assert created.status_code == HTTP_CREATED, created.text
    body = created.json()
    identifier = body["id"]

    assert body["project_id"] == project_id
    # Operator decision 2026-10-06: `test_globs` is stored exactly as sent, nothing merged in.
    assert body["test_globs"] == []
    assert body["verify_skipped"] is False
    assert body["clone_check"]["status"] == "pending"
    assert body["clone_check"]["at"] is None

    read = authenticated.get(f"{REPOSITORIES}/{identifier}")
    assert read.status_code == HTTP_OK
    assert read.json() == body

    listed = authenticated.get(repositories_url(project_id))
    assert listed.status_code == HTTP_OK
    page = listed.json()
    assert set(page) == {"items", "next_cursor"}
    assert page["next_cursor"] is None
    assert body in page["items"]

    updated = authenticated.put(
        f"{REPOSITORIES}/{identifier}",
        json={"url": unique_url, "default_branch": "develop"},
    )
    assert updated.status_code == HTTP_OK, updated.text
    after = updated.json()

    # the branch changed, the slug and the clone_check did not
    assert after["default_branch"] == "develop"
    assert after["slug"] == body["slug"]
    assert after["clone_check"] == body["clone_check"]
    assert after["test_globs"] == []


def test_test_globs_are_stored_exactly_as_sent_and_replaced_on_update(
    authenticated: httpx.Client, project_id: str, unique_url: str
) -> None:
    # Operator decision 2026-10-06: replaces the test that pinned the always-merged defaults.
    response = create_repository(authenticated, project_id, unique_url, test_globs=["e2e/**"])

    assert response.status_code == HTTP_CREATED, response.text
    assert response.json()["test_globs"] == ["e2e/**"]

    updated = authenticated.put(
        f"{REPOSITORIES}/{response.json()['id']}",
        json={"url": unique_url, "default_branch": "main", "test_globs": ["spec/**"]},
    )
    assert updated.status_code == HTTP_OK, updated.text
    assert updated.json()["test_globs"] == ["spec/**"]


def test_a_duplicate_url_in_the_same_project_is_refused(
    authenticated: httpx.Client, project_id: str, unique_url: str
) -> None:
    create_repository(authenticated, project_id, unique_url)

    second = create_repository(authenticated, project_id, unique_url)

    assert second.status_code == HTTP_CONFLICT
    assert second.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_the_same_url_under_a_different_project_is_accepted(
    authenticated: httpx.Client, project_id: str, unique_url: str
) -> None:
    create_repository(authenticated, project_id, unique_url)
    other = authenticated.post(PROJECTS, json={"name": f"e2e repository project {uuid4()}"})
    assert other.status_code == HTTP_CREATED, other.text

    second = create_repository(authenticated, other.json()["id"], unique_url)

    assert second.status_code == HTTP_CREATED, second.text


def test_an_unknown_project_id_is_a_404(authenticated: httpx.Client, unique_url: str) -> None:
    response = create_repository(authenticated, UNKNOWN_ID, unique_url)

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_listing_an_unknown_projects_repositories_is_a_404(authenticated: httpx.Client) -> None:
    response = authenticated.get(repositories_url(UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND


def test_an_unknown_repository_id_is_a_404(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{REPOSITORIES}/{UNKNOWN_ID}")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_updating_an_unknown_repository_id_is_a_404(authenticated: httpx.Client) -> None:
    response = authenticated.put(
        f"{REPOSITORIES}/{UNKNOWN_ID}",
        json={"url": "https://example.invalid/x.git", "default_branch": "main"},
    )

    assert response.status_code == HTTP_NOT_FOUND


def test_a_missing_required_field_is_a_422(authenticated: httpx.Client, project_id: str) -> None:
    response = authenticated.post(repositories_url(project_id), json={"default_branch": "main"})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["errors"][0]["path"] == "body.url"


def test_an_invalid_glob_is_a_422(
    authenticated: httpx.Client, project_id: str, unique_url: str
) -> None:
    response = create_repository(authenticated, project_id, unique_url, test_globs=["../x"])

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["errors"][0]["path"] == "body.test_globs.0"


def test_get_project_embeds_its_repositories(
    authenticated: httpx.Client, project_id: str, unique_url: str
) -> None:
    created = create_repository(authenticated, project_id, unique_url)
    assert created.status_code == HTTP_CREATED, created.text
    created_body = created.json()

    response = authenticated.get(f"{PROJECTS}/{project_id}")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert [item["id"] for item in body["repositories"]] == [created_body["id"]]
    assert body["repositories"][0] == created_body


def test_every_repository_operation_needs_the_bearer(client: httpx.Client, project_id: str) -> None:
    for method, path in (
        ("get", repositories_url(project_id)),
        ("post", repositories_url(project_id)),
        ("get", f"{REPOSITORIES}/{UNKNOWN_ID}"),
        ("put", f"{REPOSITORIES}/{UNKNOWN_ID}"),
    ):
        response = client.request(method, path)

        assert response.status_code == HTTP_UNAUTHORIZED, f"{method} {path}"


# ── the schema the migration was written to create ───────────────────────────


@pytest.fixture(scope="module")
def repository_indexes(stack: str) -> dict[str, bool]:
    """`{index name: is unique}` for the `repository` table, read from the migrated
    database — the same boundary `tests/e2e/test_projects.py::project_indexes` reads at,
    for the same reason: the unit suite asserts these against `Base.metadata`, which the
    model populates, never against what `0003_repository.py` actually built.
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
                    "where t.relname = 'repository' and n.nspname = 'public'"
                )
            )
            return {name: bool(unique) for name, unique in rows}
    finally:
        engine.dispose()


@pytest.mark.parametrize("index", ["ix_repository_project_id_url", "ix_repository_project_id_slug"])
def test_the_migration_created_the_index_the_model_declares(
    repository_indexes: dict[str, bool], index: str
) -> None:
    assert index in repository_indexes, sorted(repository_indexes)


@pytest.mark.parametrize("index", ["ix_repository_project_id_url", "ix_repository_project_id_slug"])
def test_that_index_is_unique_and_not_merely_present(
    repository_indexes: dict[str, bool], index: str
) -> None:
    assert repository_indexes[index] is True
