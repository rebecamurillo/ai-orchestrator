"""`/api/v1/templates` over an ASGI transport, with the fake repository injected (SPEC CAP-3).

Every path this router publishes carries a `GET` (`test_bearer_auth.py` indexes every
published path's `get` operation), which is why `GET .../versions` and `GET .../validate`
exist here alongside their `POST` siblings — see `api/routers/templates.py`'s docstring.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import template_ports
from orchestrator.api.routers import templates as router_module
from orchestrator.api.schemas.templates import MAX_TEMPLATE_YAML_LENGTH
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422

PROBLEM_MEDIA_TYPE = "application/problem+json"
TEMPLATES = "/api/v1/templates"

LEAF = "name: leaf\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
INVALID_YAML = "not: [valid\n"


class Harness:
    """One application, one fake repository, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.uow = FakeUnitOfWork()
        self.templates = FakeTemplateVersionRepository()
        self.clock = FakeClock()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[template_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> TemplatePorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return TemplatePorts(uow=self.uow, templates=self.templates, clock=self.clock)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def store(self, name: str = "leaf", version: int = 1, **overrides: Any) -> None:
        fields: dict[str, Any] = {
            "name": name,
            "version": version,
            "yaml": LEAF.replace("name: leaf", f"name: {name}"),
            "hash": f"sha-{name}-{version}",
            "created_at": self.clock.now(),
        }
        fields.update(overrides)
        self.templates.add(TemplateVersion(**fields))  # type: ignore[arg-type]


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


# ── list ─────────────────────────────────────────────────────────────────────


async def test_list_templates_answers_a_page(api: Harness) -> None:
    api.store("leaf", 1)

    async with api.client() as client:
        response = await client.get(TEMPLATES)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["next_cursor"] is None
    assert body["items"] == [
        {"name": "leaf", "description": None, "latest_version": 1, "versions": [1]}
    ]


async def test_list_templates_is_empty_when_nothing_is_stored(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(TEMPLATES)

    assert response.json()["items"] == []


# ── read one version ─────────────────────────────────────────────────────────


async def test_get_version_answers_the_stored_text_and_zero_calls(api: Harness) -> None:
    api.store("leaf", 1)

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/1")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["name"] == "leaf"
    assert body["version"] == 1
    assert body["calls"] == []
    assert body["called_by"] == []
    assert body["pinned_by"] == 0
    assert body["inputs"] == []


async def test_get_version_of_an_unknown_pair_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/1")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_version_number_beyond_postgres_integer_range_is_a_422_not_a_500(
    api: Harness,
) -> None:
    """schemathesis found this: an out-of-range `version` must never reach the database."""
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/99999999999")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_version_number_of_zero_or_less_is_a_422(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/0")

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_get_version_reports_its_caller(api: Harness) -> None:
    api.store("leaf", 1)
    api.store(
        "root-caller",
        1,
        yaml=(
            "name: root-caller\nversion: 1\nsteps:\n"
            "  - id: leaf\n    uses: template\n    with:\n"
            "      name: leaf\n      version: 1\n      inputs: {}\n"
        ),
        calls=(TemplateRef(name="leaf", version=1),),
    )

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/1")

    assert response.json()["called_by"] == [{"name": "root-caller", "version": 1}]


# ── list versions ────────────────────────────────────────────────────────────


async def test_list_versions_is_ascending(api: Harness) -> None:
    api.store("leaf", 1)
    api.store("leaf", 2, yaml=LEAF.replace("version: 1", "version: 2"))

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/versions")

    assert response.json() == {"items": [1, 2], "next_cursor": None}


async def test_list_versions_of_an_unknown_name_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/versions")

    assert response.status_code == HTTP_NOT_FOUND


# ── save a new version ───────────────────────────────────────────────────────


async def test_saving_the_first_version_answers_201(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/leaf/versions", json={"yaml": LEAF})

    assert response.status_code == HTTP_CREATED
    body = response.json()
    assert body["version"] == 1
    assert body["hash"]
    assert body["created_at"] is not None


async def test_saving_the_next_version_requires_the_right_number(api: Harness) -> None:
    api.store("leaf", 1, yaml=LEAF)

    wrong = LEAF.replace("version: 1", "version: 5")
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/leaf/versions", json={"yaml": wrong})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert "version must be 2" in response.json()["detail"]


async def test_saving_under_the_wrong_name_is_a_422(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/epic/versions", json={"yaml": LEAF})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert "name must be epic" in response.json()["detail"]


async def test_saving_invalid_yaml_answers_422_with_structured_errors(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/leaf/versions", json={"yaml": INVALID_YAML})

    assert response.status_code == HTTP_UNPROCESSABLE
    body = response.json()
    assert body["errors"]
    assert body["errors"][0]["reason"]
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_yaml_beyond_the_size_cap_is_a_422(api: Harness) -> None:
    """3.1 deferred a size guard on posted YAML to this story's `/validate`; this pins it."""
    oversized = "x" * (MAX_TEMPLATE_YAML_LENGTH + 1)

    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/leaf/validate", json={"yaml": oversized})

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_a_saved_version_is_immediately_readable_byte_for_byte(api: Harness) -> None:
    async with api.client() as client:
        await client.post(f"{TEMPLATES}/leaf/versions", json={"yaml": LEAF})
        response = await client.get(f"{TEMPLATES}/leaf/1")

    assert response.json()["yaml"] == LEAF


# ── validate ─────────────────────────────────────────────────────────────────


async def test_posting_valid_yaml_to_validate_answers_200_with_no_errors(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/leaf/validate", json={"yaml": LEAF})

    assert response.status_code == HTTP_OK
    assert response.json() == {"errors": [], "unvalidated": []}


async def test_posting_invalid_yaml_to_validate_answers_200_with_errors(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/leaf/validate", json={"yaml": INVALID_YAML})

    assert response.status_code == HTTP_OK
    assert response.json()["errors"]


async def test_get_validate_re_checks_the_latest_stored_version(api: Harness) -> None:
    api.store("leaf", 1, yaml=LEAF)

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/validate")

    assert response.status_code == HTTP_OK
    assert response.json() == {"errors": [], "unvalidated": []}


async def test_get_validate_of_an_unknown_name_is_a_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/validate")

    assert response.status_code == HTTP_NOT_FOUND


# ── the published contract ───────────────────────────────────────────────────


def test_the_router_declares_every_path_with_a_get_beside_any_post() -> None:
    """`test_bearer_auth.py` indexes every published path's `get` operation."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], "/templates"),
        (["GET"], "/templates/{name}/validate"),
        (["GET"], "/templates/{name}/versions"),
        (["GET"], "/templates/{name}/{version}"),
        (["POST"], "/templates/{name}/validate"),
        (["POST"], "/templates/{name}/versions"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_every_operation_is_published_with_a_summary(api: Harness) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    for path in (
        TEMPLATES,
        f"{TEMPLATES}/{{name}}/{{version}}",
        f"{TEMPLATES}/{{name}}/versions",
        f"{TEMPLATES}/{{name}}/validate",
    ):
        for operation in document["paths"][path].values():
            assert operation["summary"]
