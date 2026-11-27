"""`/api/v1/projects/{id}/package` over an ASGI transport on the shared fakes (story 3, epic 6)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import template_ports
from orchestrator.api.providers_packages import package_ports
from orchestrator.api.routers import project_package
from orchestrator.application.use_cases.packages import PackagePorts
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.infrastructure.mcp.tools import ALLOWED_OPERATION_IDS
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.package_fixtures import PATH, SHA, merge_text, package_text
from tests.unit.application.package_world import World, files
from tests.unit.fakes.clock import FakeClock

HTTP_OK = 200
HTTP_NO_CONTENT = 204
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
TWO = 2
OPERATIONS = 3
PROBLEM = "application/problem+json"


class Harness:
    def __init__(self, env: dict[str, str], world: World | None = None) -> None:
        self.world = world or World()
        self.token = env["ORCHESTRATOR_TOKEN"]
        self.app: FastAPI = create_app(Settings())
        self.app.dependency_overrides[package_ports] = self._ports
        self.app.dependency_overrides[template_ports] = self._template_ports

    def _ports(self) -> PackagePorts:
        return self.world.ports

    def _template_ports(self) -> TemplatePorts:
        return TemplatePorts(uow=self.world.uow, templates=self.world.templates, clock=FakeClock())

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    @property
    def url(self) -> str:
        return f"/api/v1/projects/{self.world.project.id}/package"

    def body(self, **overrides: Any) -> dict[str, Any]:
        return {"repository_id": str(self.world.hub.id), "path": PATH, "ref": "main", **overrides}


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


async def put(api: Harness, body: Any = None) -> httpx.Response:
    async with api.client() as client:
        return await client.put(api.url, json=api.body() if body is None else body)


async def test_install_then_read_returns_the_same_payload_with_the_hub(api: Harness) -> None:
    installed = await put(api)

    async with api.client() as client:
        read = await client.get(api.url)

    assert installed.status_code == HTTP_OK
    assert read.json() == installed.json()
    body = read.json()
    assert (body["sha"], body["name"], body["path"], body["ref"]) == (SHA, "acme", PATH, "main")
    assert body["repository"] == {
        "id": str(api.world.hub.id),
        "slug": "hub",
        "default_branch": "main",
        "initiative_folder": "initiatives",
    }
    assert body["gate"] == {"pass": ["pass"], "fail": ["fail"], "owners_key": "owners"}
    assert body["status_map"] == {"final": "done", "blocked": "waiting for her"}
    assert [(e["workflow"], e["shown_as"], e["version"]) for e in body["sequence"]] == [
        ("spec", "workflow", 1),
        ("merge", "step", 1),
        ("build", "workflow", None),
    ]
    assert [s["kind"] for s in body["sequence"][0]["steps"]] == [
        "conversation",
        "conversation",
        "automatic",
    ]


async def test_the_stored_templates_are_read_by_their_one_segment_name(api: Harness) -> None:
    await put(api)
    api.app.dependency_overrides[template_ports] = api._template_ports

    async with api.client() as client:
        versions = await client.get("/api/v1/templates/acme.spec/versions")
        one = await client.get("/api/v1/templates/acme.spec/1")

    assert versions.status_code == HTTP_OK
    assert one.status_code == HTTP_OK
    assert one.json()["name"] == "acme.spec"


async def test_a_malformed_package_is_a_422_naming_the_file_and_reason(env: dict[str, str]) -> None:
    api = Harness(env, World(files(**{"templates/merge.yaml": merge_text("other")})))

    response = await put(api)

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM)
    error = response.json()["errors"][0]
    assert (error["path"], error["reason"]) == ("pkg/templates/merge.yaml", "name must be merge")
    assert api.world.stored() == []


async def test_a_package_yaml_refusal_lists_every_problem(env: dict[str, str]) -> None:
    api = Harness(env, World(files(package=package_text(name="Bad_Name", status_map="{ a: b }"))))

    response = await put(api)

    assert response.status_code == HTTP_UNPROCESSABLE
    assert len(response.json()["errors"]) == TWO
    assert response.json()["detail"].startswith("pkg/package.yaml: ")


async def test_a_ref_the_remote_lacks_is_a_409_naming_it(api: Harness) -> None:
    response = await put(api, api.body(ref="gone"))

    assert response.status_code == HTTP_CONFLICT
    assert "gone" in response.json()["detail"]


async def test_a_repository_of_another_project_and_an_unknown_project_are_404s(
    api: Harness,
) -> None:
    _, other = api.world.another_project("Other")
    wrong_repository = await put(api, api.body(repository_id=str(other.id)))
    async with api.client() as client:
        unknown = await client.put(
            f"/api/v1/projects/{other.id}/package",
            json=api.body(repository_id=str(api.world.hub.id)),
        )

    assert wrong_repository.status_code == HTTP_NOT_FOUND
    assert unknown.status_code == HTTP_NOT_FOUND


@pytest.mark.parametrize("path", ["", "/abs", "a/../b", "a/"])
async def test_an_invalid_path_is_a_422_naming_the_folder_rule(api: Harness, path: str) -> None:
    response = await put(api, api.body(path=path))

    assert response.status_code == HTTP_UNPROCESSABLE
    assert "path: must be one or more" in response.json()["detail"]


@pytest.mark.parametrize("extra", [{"extra": 1}, {"ref": ""}])
async def test_an_unknown_key_or_empty_ref_is_a_422(api: Harness, extra: dict[str, Any]) -> None:
    assert (await put(api, api.body(**extra))).status_code == HTTP_UNPROCESSABLE


async def test_delete_then_get_is_a_404(api: Harness) -> None:
    await put(api)
    versions = dict(api.world.templates.versions)

    async with api.client() as client:
        removed = await client.delete(api.url)
        read = await client.get(api.url)
        again = await client.delete(api.url)

    assert removed.status_code == HTTP_NO_CONTENT
    assert (read.status_code, again.status_code) == (HTTP_NOT_FOUND, HTTP_NOT_FOUND)
    assert read.json()["detail"] == "no package installed"
    assert api.world.templates.versions == versions


async def test_the_operation_ids_are_the_allow_list_entries_and_refusals_are_problems(
    api: Harness,
) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    operations = document["paths"]["/api/v1/projects/{project_id}/package"]
    ids = {operation["operationId"] for operation in operations.values()}
    assert ids <= ALLOWED_OPERATION_IDS
    assert len(ids) == OPERATIONS
    for operation in operations.values():
        for code, response in operation["responses"].items():
            if code[0] == "4":
                assert PROBLEM in response["content"]
    assert set(operations["put"]["responses"]) - {"401"} == {"200", "404", "409", "422"}
    assert set(operations["delete"]["responses"]) - {"401"} == {"204", "404", "409", "422"}
    assert "pass" in document["components"]["schemas"]["GateOut"]["properties"]


def test_the_router_declares_the_three_operations() -> None:
    methods = {method for route in project_package.router.routes for method in route.methods}  # type: ignore[attr-defined]

    assert methods == {"PUT", "GET", "DELETE"}
