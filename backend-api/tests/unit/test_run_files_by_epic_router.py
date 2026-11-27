"""`GET /runs/{id}/files-by-epic` and `/diff` over an ASGI transport (story 7, AC8, AC9)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from orchestrator.api.protected_routes import install_run_page_routes
from orchestrator.api.providers_base import GIT, SESSION_FACTORY, SETTINGS
from orchestrator.api.providers_run_files import run_files_by_epic_ports
from orchestrator.api.routers import run_files_by_epic as router_module
from orchestrator.api.schemas import run_files_by_epic as schemas
from orchestrator.application.use_cases.run_files_by_epic import FilesByEpicPorts
from orchestrator.domain.ports.git import Change
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.test_run_files_by_epic import FILES, RANGE, Rig
from tests.unit.fakes.git import FakeGit

LIST = "/api/v1/runs/{run_id}/files-by-epic"
DIFF = "/api/v1/runs/{run_id}/files-by-epic/diff"
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401
PROBLEM = "application/problem+json"
UNKNOWN = "01a06887-79ab-759b-97a0-71c32ad939c2"
QUERY = "?epic=0&story=1&path=src/a.py"


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.rig = Rig(attempts=RANGE)
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[run_files_by_epic_ports] = lambda: self.rig.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self, *, bearer: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if bearer else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )

    def url(self, template: str, run_id: object = None) -> str:
        return template.format(run_id=run_id or self.rig.run.id)


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_the_list_answers_epics_and_stories(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(api.url(LIST))

    assert response.status_code == HTTP_OK
    epics = response.json()["epics"]
    assert [e["index"] for e in epics] == [0, 1]
    assert epics[0]["stories"][0] == {
        "id": "1",
        "title": "First",
        "story_file": "initiatives/i/e1/stories/1-x.md",
        "started": True,
        "changed": ["src/a.py"],
    }
    assert epics[0]["stories"][1]["story_file"] is None


async def test_the_diff_answers_the_unified_diff(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(api.url(DIFF) + QUERY)

    assert response.status_code == HTTP_OK
    assert response.json()["diff"] == "THE DIFF"
    assert response.json()["path"] == "src/a.py"


async def test_unknown_run_and_unchanged_path_are_404_problems(api: Api) -> None:
    async with api.client() as client:
        responses = [
            await client.get(api.url(LIST, UNKNOWN)),
            await client.get(api.url(DIFF, UNKNOWN) + QUERY),
            await client.get(api.url(DIFF) + "?epic=0&story=1&path=src/b.py"),
        ]

    for response in responses:
        assert response.status_code == HTTP_NOT_FOUND
        assert response.headers["content-type"].startswith(PROBLEM)


@pytest.mark.parametrize(
    "suffix",
    ["?epic=-1&story=1&path=p", "?epic=0&path=p", "?epic=0&story=1", "?epic=x&story=1&path=p"],
)
async def test_malformed_queries_are_422(api: Api, suffix: str) -> None:
    async with api.client() as client:
        response = await client.get(api.url(DIFF) + suffix)

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_a_non_uuid_run_is_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(api.url(LIST, "not-a-uuid"))

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_without_the_bearer_it_is_401(api: Api) -> None:
    async with api.client(bearer=False) as client:
        responses = [await client.get(api.url(LIST)), await client.get(api.url(DIFF) + QUERY)]

    assert [r.status_code for r in responses] == [HTTP_UNAUTHORIZED, HTTP_UNAUTHORIZED]


def test_both_paths_are_published_with_a_declared_401(api: Api) -> None:
    paths = api.app.openapi()["paths"]

    assert "401" in paths[LIST]["get"]["responses"]
    assert "401" in paths[DIFF]["get"]["responses"]


def test_install_run_page_routes_mounts_both_paths() -> None:
    app = FastAPI()

    install_run_page_routes(app)

    assert {LIST, DIFF} <= set(app.openapi()["paths"])


def test_the_provider_builds_the_ports_from_app_state(env: dict[str, str]) -> None:
    app = FastAPI()
    setattr(app.state, SETTINGS, Settings(**{k.lower(): v for k, v in env.items()}))
    setattr(app.state, SESSION_FACTORY, sessionmaker(create_engine("sqlite://")))
    setattr(app.state, GIT, FakeGit(changes={"/": (Change(path="x", kind="added"),)}))
    request = Request({"type": "http", "app": app})
    generator: Iterator[FilesByEpicPorts] = run_files_by_epic_ports(request)

    ports = next(generator)
    generator.close()

    assert isinstance(ports, FilesByEpicPorts)


def test_the_router_declares_the_two_gets() -> None:
    routes = [(sorted(r.methods), r.path) for r in router_module.router.routes]

    assert routes == [
        (["GET"], "/runs/{run_id}/files-by-epic"),
        (["GET"], "/runs/{run_id}/files-by-epic/diff"),
    ]


def test_the_schema_module_is_importable() -> None:
    assert schemas.RunFilesByEpicOut is not None
    assert FILES
