"""The open guide routes (story 1.3, SPEC CAP-3; AD-1 amended 2026-11-11)."""

import json
import typing
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from orchestrator.api import open_routes, providers_base
from orchestrator.api.routers import guide, version
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from orchestrator.tools import build_guide

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401
CODE = "refusal-guide-unavailable"
GUIDE = "errors/refusal-guide-unavailable"


def forbidden(dependant: Dependant) -> list[str]:
    """What an open route may not depend on: settings, a unit of work, providers, a port."""
    found: list[str] = []
    for sub in dependant.dependencies:
        call = sub.call
        if call is not None:
            if call is version.instance_settings:
                found.append("instance_settings")
            if call.__module__.startswith("orchestrator.api.providers"):
                found.append(f"providers:{call.__name__}")
            hints = typing.get_type_hints(call, include_extras=True)
            for hint in hints.values():
                base = typing.get_args(hint)[0] if typing.get_origin(hint) is Annotated else hint
                if base is Settings or base is UnitOfWork:
                    found.append(f"type:{base.__name__}")
                elif getattr(base, "__module__", "").startswith("orchestrator.domain.ports"):
                    found.append(f"port:{base.__name__}")
        found.extend(forbidden(sub))
    return found


def forbidden_of(router: APIRouter) -> list[str]:
    return [
        item
        for route in router.routes
        if isinstance(route, APIRoute)
        for item in forbidden(route.dependant)
    ]


@pytest.fixture
def build(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    (source / "a").mkdir(parents=True)
    (source / "a" / "one.md").write_text(
        "---\ntitle: One\nkind: page\naudience: any\n---\nBody one\n"
    )
    (source / "host.md").write_text(
        "---\ntitle: Host page\nkind: page\naudience: host\n---\n"
        "Local agent on the host or the user only.\n"
    )
    out = tmp_path / "build"
    code = build_guide.main(
        ["--source", str(source), "--out", str(out), "--version-file", str(version.VERSION_FILE)]
    )
    assert code == 0
    (out / "schemas").mkdir()
    (out / "schemas" / "x.json").write_text('{"type": "object"}')
    (tmp_path / "x.md").write_text("outside the build directory")
    return out


def client(app: FastAPI, token: str | None = None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://backend-api",
        headers=headers,
    )


@pytest.fixture
def app(env: dict[str, str], build: Path) -> FastAPI:
    application = create_app(Settings())
    application.dependency_overrides[guide.guide_dir] = lambda: build
    return application


def assert_refused(response: httpx.Response) -> None:
    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == CODE
    assert body["guide"] == GUIDE


def index_of(build: Path) -> list[dict[str, str]]:
    pages: list[dict[str, str]] = json.loads((build / "guide-index.json").read_text())["pages"]
    return pages


async def test_the_index_a_page_and_a_schema_are_open(app: FastAPI, build: Path) -> None:
    async with client(app) as http:
        llms = await http.get("/llms.txt")
        assert llms.status_code == HTTP_OK
        assert llms.headers["content-type"] == "text/plain; charset=utf-8"
        for page in index_of(build):
            response = await http.get(f"/guide/{page['id']}.md")
            assert response.status_code == HTTP_OK, page["id"]
            assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        schema = await http.get("/schemas/x.json")
        assert schema.status_code == HTTP_OK
        assert schema.headers["content-type"].startswith("application/schema+json")
        assert schema.json() == {"type": "object"}


async def test_llms_txt_lists_every_page_under_its_section(app: FastAPI, build: Path) -> None:
    async with client(app) as http:
        text = (await http.get("/llms.txt")).text
    release = version.app_version()
    lines = text.split("\n")
    assert lines[:3] == [
        "# ai-orchestrator guide",
        "",
        f"> The guide for release {release}. Every page is at /guide/{{id}}.md.",
    ]
    assert text.endswith("\n")
    section = ""
    seen: dict[str, str] = {}
    for line in lines:
        if line.startswith("## "):
            section = line[3:]
        elif line.startswith("- ["):
            page_id = line.split("(/guide/")[1].removesuffix(".md)")
            seen[page_id] = section
    for page in index_of(build):
        expected = (
            "Errors"
            if page["id"].startswith("errors/")
            else "Host"
            if page["audience"] == "host"
            else "Guide"
        )
        assert seen[page["id"]] == expected
        title = page["title"]
        assert f"- [{title}](/guide/{page['id']}.md)" in lines


async def test_a_source_without_a_host_page_omits_the_host_section(
    env: dict[str, str], tmp_path: Path
) -> None:
    source = tmp_path / "s"
    source.mkdir()
    (source / "p.md").write_text("---\ntitle: P\nkind: page\naudience: any\n---\nx\n")
    out = tmp_path / "o"
    build_guide.main(["--source", str(source), "--out", str(out)])
    application = create_app(Settings())
    application.dependency_overrides[guide.guide_dir] = lambda: out
    async with client(application) as http:
        text = (await http.get("/llms.txt")).text
    assert "## Host" not in text
    assert "## Guide" in text
    assert "## Errors" in text


@pytest.mark.parametrize(
    "path",
    [
        "/guide/nope.md",
        "/guide/a/two.md",
        "/guide/%2e%2e/x.md",
        "/schemas/nope.json",
        "/schemas/X.json",
        "/schemas/a.b.json",
    ],
)
async def test_anything_not_found_is_the_one_problem(app: FastAPI, path: str) -> None:
    async with client(app) as http:
        assert_refused(await http.get(path))


async def test_a_file_on_disk_but_not_in_the_index_is_not_served(app: FastAPI, build: Path) -> None:
    (build / "a" / "stray.md").write_text("stray")
    async with client(app) as http:
        assert_refused(await http.get("/guide/a/stray.md"))


async def test_an_indexed_page_whose_file_is_gone_is_not_served(app: FastAPI, build: Path) -> None:
    (build / "a" / "one.md").unlink()
    async with client(app) as http:
        assert_refused(await http.get("/guide/a/one.md"))


async def test_a_missing_build_directory_is_the_problem(app: FastAPI, tmp_path: Path) -> None:
    app.dependency_overrides[guide.guide_dir] = lambda: tmp_path / "absent"
    async with client(app) as http:
        for path in ("/llms.txt", "/guide/a/one.md", "/schemas/x.json"):
            assert_refused(await http.get(path))


@pytest.mark.parametrize(
    "content",
    ["{not json", '{"pages": "nope"}', "[]", '{"pages": [{"id": ["a"]}], "release": "x"}'],
)
async def test_an_unreadable_index_is_the_problem(app: FastAPI, build: Path, content: str) -> None:
    (build / "guide-index.json").write_text(content)
    async with client(app) as http:
        assert_refused(await http.get("/llms.txt"))
        assert_refused(await http.get("/guide/a/one.md"))


def test_the_resolve_and_compare_helper_refuses_to_leave_the_root(build: Path) -> None:
    assert guide.inside(build, "../x.md") is None
    assert guide.inside(build, "a/../../x.md") is None
    assert guide.inside(build, "a/one.md") is not None


async def test_a_served_page_carries_the_release_of_the_version_route(
    app: FastAPI, env: dict[str, str]
) -> None:
    async with client(app, env["ORCHESTRATOR_TOKEN"]) as http:
        page = (await http.get("/guide/a/one.md")).text
        app_version = (await http.get("/api/v1/version")).json()["app_version"]
    assert f"release: {app_version}" in page.split("---")[1]


async def test_no_open_response_sets_a_cookie_or_cors_header(app: FastAPI) -> None:
    async with client(app) as http:
        for path in ("/llms.txt", "/guide/a/one.md", "/schemas/x.json", "/guide/nope.md"):
            response = await http.get(path)
            assert "set-cookie" not in response.headers
            assert not [h for h in response.headers if h.lower().startswith("access-control-")]


async def test_the_instance_data_stays_behind_the_bearer(app: FastAPI) -> None:
    async with client(app) as http:
        for path in ("/api/v1/projects", "/api/v1/templates"):
            assert (await http.get(path)).status_code == HTTP_UNAUTHORIZED


async def test_openapi_describes_the_three_routes(app: FastAPI) -> None:
    async with client(app) as http:
        paths = (await http.get("/openapi.json")).json()["paths"]
    media = {
        "/llms.txt": "text/plain; charset=utf-8",
        "/guide/{page_id}.md": "text/markdown; charset=utf-8",
        "/schemas/{name}.json": "application/schema+json",
    }
    for path, media_type in media.items():
        operation = paths[path]["get"]
        assert media_type in operation["responses"]["200"]["content"]
        problem = operation["responses"]["404"]["content"]["application/problem+json"]
        assert problem["schema"]["$ref"].endswith("/ProblemDetail")


def test_the_default_build_directory_sits_beside_the_version_file() -> None:
    assert guide.guide_dir() == guide.GUIDE_DIR
    assert guide.GUIDE_DIR == version.VERSION_FILE.parent / "guide-build"


async def test_install_open_routes_mounts_the_guide_on_any_app(build: Path) -> None:
    bare = FastAPI()
    open_routes.install_open_routes(bare)
    bare.dependency_overrides[guide.guide_dir] = lambda: build
    async with client(bare) as http:
        assert (await http.get("/llms.txt")).status_code == HTTP_OK


def test_the_guard_passes_on_the_shipped_router() -> None:
    routes = [route for route in guide.router.routes if isinstance(route, APIRoute)]
    assert len(routes) == 3  # noqa: PLR2004
    assert forbidden_of(guide.router) == []


def planted(dependency: Callable[..., Any]) -> APIRouter:
    router = APIRouter()

    @router.get("/planted")
    def read(value: Annotated[Any, Depends(dependency)]) -> None:
        return None

    return router


def test_the_guard_flags_settings_a_unit_of_work_and_providers() -> None:
    def wants_settings(settings: Settings) -> None:
        return None

    def wants_uow() -> UnitOfWork:
        raise NotImplementedError

    assert "instance_settings" in forbidden_of(planted(version.instance_settings))
    assert "type:Settings" in forbidden_of(planted(wants_settings))
    assert "type:UnitOfWork" in forbidden_of(planted(wants_uow))
    assert forbidden_of(planted(providers_base.setup_record))
    assert any(
        item.startswith("providers:") for item in forbidden_of(planted(providers_base.setup_record))
    )


def test_the_guard_walks_nested_dependencies() -> None:
    def inner(settings: Settings) -> None:
        return None

    def outer(value: Annotated[None, Depends(inner)]) -> None:
        return None

    assert forbidden_of(planted(outer)) == ["type:Settings"]
