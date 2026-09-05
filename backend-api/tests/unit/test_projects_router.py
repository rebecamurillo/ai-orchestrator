"""`/api/v1/projects` over an ASGI transport, with the fakes injected as its ports.

The use-case rules are asserted in `tests/unit/test_projects_use_cases.py` and the payload
rules in `tests/unit/test_project_schemas.py`. What is left, and what only a request can
show, is the HTTP: the status a create answers with, the envelope a list uses, the problem
document each refusal becomes, and — the claim this whole story exists for — that no
response body anywhere carries a plaintext value.

`dependency_overrides` replaces `project_ports`, so no database and no key are involved:
the ports are the same four fakes every other unit test uses (AD-18).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import project_ports
from orchestrator.api.routers import projects as router_module
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import MASK_PREFIX
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROJECTS = "/api/v1/projects"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


def at(iso: str) -> datetime:
    """Parse before comparing: `_iso_z` drops a zero fraction, so `12:00:00Z` sorts after
    `12:00:00.5Z` as a string. Two timestamps are only ordered as timestamps."""
    return datetime.fromisoformat(iso)


SECRET = "abcdefgh"
URL = "https://x"
#: A NUL character: valid JSON, and a value no `text` column can hold.
HOSTILE = "before\x00after"


class Harness:
    """One application, one set of fakes, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str], *, log_prompt_content_default: bool | None = None):
        if log_prompt_content_default is not None:
            env = dict(env, LOG_PROMPT_CONTENT_DEFAULT=str(log_prompt_content_default).lower())
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.projects = FakeProjectRepository()
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
            uow=self.uow, projects=self.projects, crypto=self.crypto, clock=self.clock
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


def a_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "My Website",
        "context_text": "read this",
        "context_paths": ["docs/a.md"],
        "env_vars": [{"name": "API_URL", "value": URL}, {"name": "TOKEN_A", "value": SECRET}],
    }
    payload.update(overrides)
    return payload


async def create(api: Harness, **overrides: Any) -> httpx.Response:
    async with api.client() as client:
        return await client.post(PROJECTS, json=a_payload(**overrides))


# ── create ───────────────────────────────────────────────────────────────────


async def test_a_create_answers_201_with_the_masked_project(api: Harness) -> None:
    response = await create(api)

    assert response.status_code == HTTP_CREATED
    body = response.json()
    assert body["name"] == "My Website"
    assert body["slug"] == "my-website"
    assert body["context_paths"] == ["docs/a.md"]
    assert body["env_vars"] == [
        {"name": "API_URL", "masked": f"{MASK_PREFIX}://x"},
        {"name": "TOKEN_A", "masked": f"{MASK_PREFIX}efgh"},
    ]


async def test_the_created_project_is_stored_with_ciphertext(api: Harness) -> None:
    response = await create(api)

    stored = api.projects.get(UUID(response.json()["id"]))
    assert stored is not None
    assert [variable.value_enc for variable in stored.env_vars_enc] != [URL, SECRET]
    assert api.crypto.decrypt(stored.env_vars_enc[1].value_enc) == SECRET


async def test_no_response_body_carries_a_plaintext_value(api: Harness) -> None:
    created = await create(api)
    identifier = created.json()["id"]

    async with api.client() as client:
        read = await client.get(f"{PROJECTS}/{identifier}")
        listed = await client.get(PROJECTS)
        updated = await client.put(f"{PROJECTS}/{identifier}", json=a_payload())

    for response in (created, read, listed, updated):
        assert SECRET not in response.text, response.url
        assert URL not in response.text, response.url


async def test_the_timestamps_leave_in_the_z_form(api: Harness) -> None:
    body = (await create(api)).json()

    assert body["created_at"].endswith("Z")
    assert body["updated_at"] == body["created_at"]


async def test_a_duplicate_name_is_a_conflict(api: Harness) -> None:
    await create(api)

    response = await create(api)

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "conflict"


async def test_a_refused_variable_name_arrives_as_an_errors_entry(api: Harness) -> None:
    response = await create(api, env_vars=[{"name": "GITHUB_TOKEN", "value": "x"}])

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    entry = response.json()["errors"][0]
    assert entry["path"] == "body.env_vars.0.name"
    assert "instance setting, not a project variable" in entry["reason"]


async def test_hostile_text_is_a_problem_document_and_never_a_500(api: Harness) -> None:
    """A NUL character raises inside psycopg; it has to be refused at the edge."""
    response = await create(api, name=HOSTILE)

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["errors"][0]["path"] == "body.name"


@pytest.mark.parametrize("default", [False, True])
async def test_a_create_that_omits_the_switch_takes_the_instance_default(
    env: dict[str, str], default: bool
) -> None:
    api = Harness(env, log_prompt_content_default=default)

    response = await create(api)

    assert response.json()["log_prompt_content"] is default
    stored = api.projects.get(UUID(response.json()["id"]))
    assert stored is not None
    assert stored.log_prompt_content is default


async def test_an_update_that_omits_the_switch_keeps_the_stored_one(
    env: dict[str, str],
) -> None:
    """The instance default is a create-time rule; a `PUT` must not silently reset it."""
    api = Harness(env, log_prompt_content_default=False)
    created = (await create(api, log_prompt_content=True)).json()
    assert created["log_prompt_content"] is True

    async with api.client() as client:
        response = await client.put(f"{PROJECTS}/{created['id']}", json=a_payload())

    assert response.status_code == HTTP_OK
    assert response.json()["log_prompt_content"] is True
    stored = api.projects.get(UUID(created["id"]))
    assert stored is not None
    assert stored.log_prompt_content is True


async def test_an_update_that_states_the_switch_writes_it(env: dict[str, str]) -> None:
    api = Harness(env, log_prompt_content_default=False)
    created = (await create(api, log_prompt_content=True)).json()

    async with api.client() as client:
        response = await client.put(
            f"{PROJECTS}/{created['id']}", json=a_payload(log_prompt_content=False)
        )

    assert response.json()["log_prompt_content"] is False


# ── read ─────────────────────────────────────────────────────────────────────


async def test_reading_one_project_answers_the_masked_project(api: Harness) -> None:
    created = (await create(api)).json()

    async with api.client() as client:
        response = await client.get(f"{PROJECTS}/{created['id']}")

    assert response.status_code == HTTP_OK
    assert response.json() == created


async def test_an_unknown_id_is_a_404_problem_document(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{PROJECTS}/{UNKNOWN_ID}")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "not found"


@pytest.mark.parametrize("method", ["get", "put"])
async def test_an_id_that_is_not_a_uuid_is_a_422(api: Harness, method: str) -> None:
    async with api.client() as client:
        response = await client.request(method, f"{PROJECTS}/not-a-uuid", json=a_payload())

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_the_list_is_the_one_envelope_this_api_uses(api: Harness) -> None:
    await create(api, name="Charlie", env_vars=[])
    await create(api, name="Alpha", env_vars=[])
    await create(api, name="Bravo", env_vars=[])

    async with api.client() as client:
        response = await client.get(PROJECTS)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert set(body) == {"items", "next_cursor"}
    assert body["next_cursor"] is None
    assert [item["name"] for item in body["items"]] == ["Alpha", "Bravo", "Charlie"]


async def test_an_empty_list_is_still_the_envelope(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(PROJECTS)

    assert response.json() == {"items": [], "next_cursor": None}


# ── update ───────────────────────────────────────────────────────────────────


async def test_an_update_keeps_replaces_and_deletes(api: Harness) -> None:
    created = (await create(api)).json()
    stored_before = api.projects.get(UUID(created["id"]))
    assert stored_before is not None
    kept = stored_before.env_vars_enc[0].value_enc
    api.clock.advance(60)

    async with api.client() as client:
        response = await client.put(
            f"{PROJECTS}/{created['id']}",
            json=a_payload(env_vars=[{"name": "API_URL"}, {"name": "NEW_ONE", "value": "wxyz"}]),
        )

    assert response.status_code == HTTP_OK
    body = response.json()
    assert [variable["name"] for variable in body["env_vars"]] == ["API_URL", "NEW_ONE"]
    stored_after = api.projects.get(UUID(created["id"]))
    assert stored_after is not None
    assert stored_after.env_vars_enc[0].value_enc == kept
    assert at(body["updated_at"]) > at(body["created_at"])
    assert body["slug"] == created["slug"]


async def test_a_keep_with_nothing_to_keep_is_a_422_problem_document(api: Harness) -> None:
    created = (await create(api)).json()

    async with api.client() as client:
        response = await client.put(
            f"{PROJECTS}/{created['id']}", json=a_payload(env_vars=[{"name": "NOWHERE"}])
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert "no stored value to keep" in response.json()["detail"]


async def test_renaming_onto_another_projects_name_is_a_conflict(api: Harness) -> None:
    await create(api, name="Taken", env_vars=[])
    mine = (await create(api, name="Mine", env_vars=[])).json()

    async with api.client() as client:
        response = await client.put(f"{PROJECTS}/{mine['id']}", json=a_payload(name="Taken"))

    assert response.status_code == HTTP_CONFLICT


async def test_updating_an_unknown_id_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.put(f"{PROJECTS}/{UNKNOWN_ID}", json=a_payload())

    assert response.status_code == HTTP_NOT_FOUND


# ── the published contract ───────────────────────────────────────────────────


async def test_every_operation_is_published_with_a_summary(api: Harness) -> None:
    """Schemathesis drives what the document publishes; the UI reads the summaries."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    paths = document["paths"]
    assert set(paths[PROJECTS]) == {"get", "post"}
    assert set(paths[f"{PROJECTS}/{{project_id}}"]) == {"get", "put"}
    for path in (PROJECTS, f"{PROJECTS}/{{project_id}}"):
        for operation in paths[path].values():
            assert operation["summary"]


def test_the_router_declares_four_operations_and_repeats_no_dependency() -> None:
    """The bearer is attached to the whole `/api/v1` prefix by `main.py` (AD-4)."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], "/projects"),
        (["GET"], "/projects/{project_id}"),
        (["POST"], "/projects"),
        (["PUT"], "/projects/{project_id}"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_the_create_is_published_as_a_201(api: Harness) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "201" in document["paths"][PROJECTS]["post"]["responses"]


#: What each operation can refuse with, beside the 401 the whole prefix declares. A list
#: takes no body and no path parameter, so 422 is not among the answers it can give.
DECLARED_REFUSALS = {
    ("get", PROJECTS): set(),
    ("post", PROJECTS): {"409", "422"},
    ("get", f"{PROJECTS}/{{project_id}}"): {"404", "422"},
    ("put", f"{PROJECTS}/{{project_id}}"): {"404", "409", "422"},
}


async def test_every_refusal_an_operation_can_answer_is_published(api: Harness) -> None:
    """2.5 renders these; an undeclared response has no type in the generated client."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    for (method, path), expected in DECLARED_REFUSALS.items():
        responses = set(document["paths"][path][method]["responses"])

        assert responses - {"200", "201", "401"} == expected, f"{method} {path}"


async def test_every_published_refusal_is_the_problem_document_this_api_sends(
    api: Harness,
) -> None:
    """Undeclared, FastAPI would publish its own `HTTPValidationError` shape for the 422."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    for (method, path), expected in DECLARED_REFUSALS.items():
        for status in expected:
            content = document["paths"][path][method]["responses"][status]["content"]
            assert PROBLEM_MEDIA_TYPE in content, f"{method} {path} {status}"
            assert content[PROBLEM_MEDIA_TYPE]["schema"]["$ref"].endswith("/ProblemDetail")
    assert "HTTPValidationError" not in document["components"]["schemas"]


async def test_the_published_schemas_carry_no_value_field(api: Harness) -> None:
    """AD-3: the browser's types come from this document, and none may hold a value."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    read = document["components"]["schemas"]["ProjectRead"]
    masked = document["components"]["schemas"]["MaskedEnvVarOut"]
    assert "value" not in read["properties"]
    assert set(masked["properties"]) == {"name", "masked"}
