"""`/api/v1` Repository operations over an ASGI transport, with the fakes injected as ports.

The use-case rules are asserted in `tests/unit/test_repositories_use_cases.py` and the
payload rules in `tests/unit/test_repository_schemas.py`. What is left, and what only a
request can show, is the HTTP: the status a create answers with, the envelope the list
uses, the problem document each refusal becomes, and that `GET /projects/{id}` embeds every
stored Repository, in the order they were created.

`dependency_overrides` replaces `project_ports`, so no database and no key are involved: the
ports are the same fakes every other unit test uses (AD-18).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import project_ports
from orchestrator.api.routers import repositories as router_module
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import Project, slugify
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROJECTS = "/api/v1/projects"
REPOSITORIES = "/api/v1/repositories"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


class Harness:
    """One application, one set of fakes, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.projects = FakeProjectRepository()
        self.repositories = FakeRepositoryRepository()
        self.crypto = FakeCrypto()
        self.clock = FakeClock()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[project_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> ProjectPorts:
        """Re-enter the fake unit of work per request, the way the real provider does."""
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return ProjectPorts(
            uow=self.uow,
            projects=self.projects,
            repositories=self.repositories,
            crypto=self.crypto,
            clock=self.clock,
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def project(self, name: str = "My Website") -> UUID:
        """Store a Project directly — a Repository always nests under one."""
        project = Project(
            id=new_id(),
            slug=slugify(name),
            name=name,
            context_text="",
            context_paths=(),
            env_vars_enc=(),
            log_prompt_content=False,
            created_at=self.clock.now(),
            updated_at=self.clock.now(),
        )
        self.projects.add(project)
        return project.id


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


def a_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": "https://github.com/org/my-repo.git",
        "default_branch": "main",
    }
    payload.update(overrides)
    return payload


async def add(api: Harness, project_id: UUID, **overrides: Any) -> httpx.Response:
    async with api.client() as client:
        return await client.post(
            f"{PROJECTS}/{project_id}/repositories", json=a_payload(**overrides)
        )


# ── create ───────────────────────────────────────────────────────────────────


# Operator decision 2026-10-06: `test_globs` is stored exactly as sent; the two tests below
# replace the ones that pinned the always-merged defaults.
async def test_a_create_answers_201_with_no_protected_globs(api: Harness) -> None:
    project_id = api.project()

    response = await add(api, project_id)

    assert response.status_code == HTTP_CREATED
    body = response.json()
    assert body["project_id"] == str(project_id)
    assert body["test_globs"] == []
    assert body["verify_skipped"] is True
    assert body["clone_check"] == {
        "status": "pending",
        "at": None,
        "output": "",
        "bmad_version": None,
    }
    assert body["package_manager"] == "other"


async def test_a_quality_gate_command_turns_off_verify_skipped(api: Harness) -> None:
    project_id = api.project()

    response = await add(api, project_id, quality_gate_command="make lint test")

    assert response.json()["verify_skipped"] is False


async def test_test_globs_are_stored_exactly_as_sent(api: Harness) -> None:
    project_id = api.project()

    response = await add(api, project_id, test_globs=["e2e/**"])

    assert response.json()["test_globs"] == ["e2e/**"]


async def test_creating_under_an_unknown_project_is_a_404(api: Harness) -> None:
    response = await add(api, UUID(UNKNOWN_ID))

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "not found"


async def test_a_duplicate_url_in_the_same_project_is_a_409(api: Harness) -> None:
    project_id = api.project()
    await add(api, project_id)

    response = await add(api, project_id)

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "conflict"


async def test_the_same_url_under_a_different_project_is_accepted(api: Harness) -> None:
    first = api.project("First")
    second = api.project("Second")
    await add(api, first)

    response = await add(api, second)

    assert response.status_code == HTTP_CREATED


async def test_a_missing_required_field_is_a_422_naming_its_path(api: Harness) -> None:
    project_id = api.project()

    async with api.client() as client:
        response = await client.post(
            f"{PROJECTS}/{project_id}/repositories", json={"default_branch": "main"}
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["errors"][0]["path"] == "body.url"


async def test_an_invalid_glob_is_a_422_naming_its_index(api: Harness) -> None:
    project_id = api.project()

    response = await add(api, project_id, test_globs=["/abs/**"])

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["errors"][0]["path"] == "body.test_globs.0"


# ── read ─────────────────────────────────────────────────────────────────────


async def test_reading_one_repository_answers_it(api: Harness) -> None:
    project_id = api.project()
    created = (await add(api, project_id)).json()

    async with api.client() as client:
        response = await client.get(f"{REPOSITORIES}/{created['id']}")

    assert response.status_code == HTTP_OK
    assert response.json() == created


async def test_an_unknown_repository_id_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{REPOSITORIES}/{UNKNOWN_ID}")

    assert response.status_code == HTTP_NOT_FOUND


async def test_listing_a_projects_repositories(api: Harness) -> None:
    project_id = api.project()
    first = (await add(api, project_id, url="https://x/org/one.git")).json()
    api.clock.advance(60)
    second = (await add(api, project_id, url="https://x/org/two.git")).json()

    async with api.client() as client:
        response = await client.get(f"{PROJECTS}/{project_id}/repositories")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert set(body) == {"items", "next_cursor"}
    assert body["next_cursor"] is None
    assert [item["id"] for item in body["items"]] == [first["id"], second["id"]]


async def test_listing_an_unknown_projects_repositories_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{PROJECTS}/{UNKNOWN_ID}/repositories")

    assert response.status_code == HTTP_NOT_FOUND


# ── update ───────────────────────────────────────────────────────────────────


async def test_updating_changes_the_stated_fields(api: Harness) -> None:
    project_id = api.project()
    created = (await add(api, project_id)).json()
    api.clock.advance(60)

    async with api.client() as client:
        response = await client.put(
            f"{REPOSITORIES}/{created['id']}", json=a_payload(default_branch="develop")
        )

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["default_branch"] == "develop"
    assert body["slug"] == created["slug"]
    assert body["clone_check"] == created["clone_check"]
    assert body["updated_at"] != created["updated_at"]


async def test_updating_an_unknown_id_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.put(f"{REPOSITORIES}/{UNKNOWN_ID}", json=a_payload())

    assert response.status_code == HTTP_NOT_FOUND


async def test_updating_onto_a_duplicate_url_is_a_409(api: Harness) -> None:
    project_id = api.project()
    await add(api, project_id, url="https://x/org/taken.git")
    mine = (await add(api, project_id, url="https://x/org/mine.git")).json()

    async with api.client() as client:
        response = await client.put(
            f"{REPOSITORIES}/{mine['id']}", json=a_payload(url="https://x/org/taken.git")
        )

    assert response.status_code == HTTP_CONFLICT


# ── GET /projects/{id} embeds the Repositories ────────────────────────────────


async def test_get_project_embeds_no_repositories_when_there_are_none(api: Harness) -> None:
    project_id = api.project()

    async with api.client() as client:
        response = await client.get(f"{PROJECTS}/{project_id}")

    assert response.status_code == HTTP_OK
    assert response.json()["repositories"] == []


async def test_get_project_embeds_every_stored_repository_in_creation_order(
    api: Harness,
) -> None:
    project_id = api.project()
    first = (await add(api, project_id, url="https://x/org/one.git")).json()
    api.clock.advance(60)
    second = (await add(api, project_id, url="https://x/org/two.git")).json()

    async with api.client() as client:
        response = await client.get(f"{PROJECTS}/{project_id}")

    assert response.status_code == HTTP_OK
    embedded = response.json()["repositories"]
    assert [item["id"] for item in embedded] == [first["id"], second["id"]]
    assert embedded[0] == first


async def test_get_project_of_an_unknown_id_is_still_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{PROJECTS}/{UNKNOWN_ID}")

    assert response.status_code == HTTP_NOT_FOUND


async def test_the_project_list_also_embeds_each_projects_repositories(api: Harness) -> None:
    """Nothing about `list_projects` composing with `embedded_repositories` is exercised
    by `test_projects_router.py` — that module predates Repositories entirely — so a
    regression narrowing the list route back to `repositories: []` would pass every test
    but this one."""
    project_id = api.project()
    repository = (await add(api, project_id, url="https://x/org/listed.git")).json()

    async with api.client() as client:
        response = await client.get(PROJECTS)

    assert response.status_code == HTTP_OK
    (item,) = [p for p in response.json()["items"] if p["id"] == str(project_id)]
    assert item["repositories"] == [repository]


async def test_updating_a_project_still_carries_its_stored_repository(api: Harness) -> None:
    """`update_project` never touches a Repository, but the response embeds it all the
    same — re-read, not carried over from before the call."""
    project_id = api.project()
    repository = (await add(api, project_id, url="https://x/org/updated.git")).json()

    async with api.client() as client:
        response = await client.put(
            f"{PROJECTS}/{project_id}",
            json={"name": "Renamed", "context_paths": [], "env_vars": []},
        )

    assert response.status_code == HTTP_OK
    assert response.json()["repositories"] == [repository]


# ── the published contract ───────────────────────────────────────────────────


def test_the_router_declares_four_operations_and_repeats_no_dependency() -> None:
    """The bearer is attached to the whole `/api/v1` prefix by `main.py` (AD-4)."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], "/projects/{project_id}/repositories"),
        (["GET"], "/repositories/{repository_id}"),
        (["POST"], "/projects/{project_id}/repositories"),
        (["PUT"], "/repositories/{repository_id}"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_every_operation_is_published_with_a_summary(api: Harness) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    for path in (f"{PROJECTS}/{{project_id}}/repositories", f"{REPOSITORIES}/{{repository_id}}"):
        for operation in document["paths"][path].values():
            assert operation["summary"]


#: What each operation can refuse with, beside the 401 the whole prefix declares.
DECLARED_REFUSALS = {
    ("post", f"{PROJECTS}/{{project_id}}/repositories"): {"404", "409", "422"},
    ("get", f"{PROJECTS}/{{project_id}}/repositories"): {"404", "422"},
    ("get", f"{REPOSITORIES}/{{repository_id}}"): {"404", "422"},
    ("put", f"{REPOSITORIES}/{{repository_id}}"): {"404", "409", "422"},
}


async def test_every_refusal_an_operation_can_answer_is_published(api: Harness) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    for (method, path), expected in DECLARED_REFUSALS.items():
        responses = set(document["paths"][path][method]["responses"])

        assert responses - {"200", "201", "401"} == expected, f"{method} {path}"


async def test_every_published_refusal_is_the_problem_document_this_api_sends(
    api: Harness,
) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    for (method, path), expected in DECLARED_REFUSALS.items():
        for status in expected:
            content = document["paths"][path][method]["responses"][status]["content"]
            assert PROBLEM_MEDIA_TYPE in content, f"{method} {path} {status}"
            assert content[PROBLEM_MEDIA_TYPE]["schema"]["$ref"].endswith("/ProblemDetail")
