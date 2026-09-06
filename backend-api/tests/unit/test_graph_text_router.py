"""`POST` and `GET /api/v1/templates/{name}/graph` over an ASGI transport (3.6).

A third graph router, and the split is forced twice over. `tests/unit/test_graph_router.py`
asserts that **every** route on `api/routers/graph.py` includes `GET`, so a `POST` cannot
land there; `tests/unit/test_templates_router.py` asserts an exact six-entry route list on
`api/routers/templates.py`, so a seventh cannot land there either. Both files are anchors,
and neither property is relaxed by putting this pair on a module of its own — same prefix,
same bearer dependency, invisible from outside (AD-4), the precedent
`api/routers/clone_check.py` set.

The `GET` beside the `POST` is mandatory, not decorative: `tests/unit/test_bearer_auth.py`
indexes `document["paths"][path]["get"]` for every published `/api/v1` path.

Every request here goes through `create_app`, never through the router in isolation, because
the one thing a router-level test could not see is the failure this story most has to avoid:
`api/routers/templates.py` registers `GET /templates/{name}/{version}` last, and Starlette
matches in registration order, so a three-segment `GET /templates/{name}/graph` mounted
*after* it would be swallowed as `version="graph"` and answered 422.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator import main as composition_root
from orchestrator.api.providers import template_ports
from orchestrator.api.routers import graph_text as router_module
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_SERVER_ERROR = 500

PROBLEM_MEDIA_TYPE = "application/problem+json"
TEMPLATES = "/api/v1/templates"
GRAPH_PATH = f"{TEMPLATES}/{{name}}/graph"

LEAF = "name: leaf\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"

LEAF_V2 = (
    "name: leaf\nversion: 2\nsteps:\n"
    "  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
    "  - id: push\n    uses: git.push\n    gate: deterministic\n"
)

CALLER = """\
name: caller
version: 1
inputs:
  folder: { type: path, required: true }
steps:
  - id: first
    uses: git.sync
    gate: deterministic
  - id: items
    for_each: "{{folder}}/items.yaml"
    as: item
    pause_after_item_when: "item.done_checkpoint"
    steps:
      - id: call
        uses: template
        with:
          name: leaf
          version: 1
"""

BROKEN = "name: broken\nversion: 1\nsteps:\n  - id: sync\n    uses: no.such.kind\n"

UNKNOWN_CALLEE = """\
name: caller
version: 1
steps:
  - id: call
    uses: template
    with:
      name: nothing-stores-this
      version: 1
"""

#: `BROKEN`'s `uses:` line — the 422 and the 500 both name it.
BROKEN_LINE = 5


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

    def anonymous(self) -> httpx.AsyncClient:
        """A client carrying no credential — `headers={}` on a request only merges."""
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
        )

    def store(self, name: str, yaml_text: str, **overrides: Any) -> None:
        fields: dict[str, Any] = {
            "name": name,
            "version": 1,
            "yaml": yaml_text,
            "hash": f"sha-{name}",
            "created_at": self.clock.now(),
        }
        fields.update(overrides)
        self.templates.add(TemplateVersion(**fields))  # type: ignore[arg-type]


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    harness = Harness(env)
    harness.store("leaf", LEAF)
    harness.store("caller", CALLER, calls=(TemplateRef(name="leaf", version=1),))
    return harness


# ── the posted graph ─────────────────────────────────────────────────────────


async def test_posted_yaml_answers_its_graph(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/caller/graph", json={"yaml": CALLER})

    assert response.status_code == HTTP_OK
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == ["first", "items.call", "items.after"]
    assert body["edges"] == [
        {"from": "first", "to": "items.call"},
        {"from": "items.call", "to": "items.after"},
    ]
    assert body["groups"] == [
        {
            "id": "items",
            "label": "items",
            "kind": "for_each",
            "members": ["items.call", "items.after"],
        }
    ]


async def test_posted_text_answers_what_the_stored_version_answers(api: Harness) -> None:
    """The story's first acceptance criterion, over the one text that is both."""
    async with api.client() as client:
        posted = await client.post(f"{TEMPLATES}/caller/graph", json={"yaml": CALLER})
        stored = await client.get(f"{TEMPLATES}/caller/1/graph")

    assert posted.json() == stored.json()


async def test_the_posted_text_is_never_stored(api: Harness) -> None:
    async with api.client() as client:
        await client.post(f"{TEMPLATES}/leaf/graph", json={"yaml": LEAF_V2})
        response = await client.get(f"{TEMPLATES}/leaf/versions")

    assert response.json()["items"] == [1]


async def test_invalid_posted_yaml_is_a_422_problem_document(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/broken/graph", json={"yaml": BROKEN})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["detail"] == f"line {BROKEN_LINE}: unknown kind"


async def test_the_422_carries_every_problem_the_validator_found(api: Harness) -> None:
    """The same `errors[]` `POST /templates/{name}/versions` sends; the reader needs the
    list, not the head of it."""
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/broken/graph", json={"yaml": BROKEN})

    errors = response.json()["errors"]
    assert [error["reason"] for error in errors] == ["unknown kind"]
    assert errors[0]["line"] == BROKEN_LINE


async def test_posted_yaml_naming_an_unknown_callee_is_a_422(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/caller/graph", json={"yaml": UNKNOWN_CALLEE})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["errors"]


async def test_a_body_without_yaml_is_a_problem_document_422(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(f"{TEMPLATES}/leaf/graph", json={})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_posting_without_the_bearer_is_a_401(api: Harness) -> None:
    async with api.anonymous() as client:
        response = await client.post(f"{TEMPLATES}/leaf/graph", json={"yaml": LEAF})

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── the stored latest ────────────────────────────────────────────────────────


async def test_the_get_answers_the_latest_stored_version(api: Harness) -> None:
    api.store("leaf", LEAF_V2, version=2, hash="sha-leaf-2")

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/graph")

    assert response.status_code == HTTP_OK
    assert [node["id"] for node in response.json()["nodes"]] == ["sync", "push"]


async def test_the_get_reaches_this_operation_and_not_the_version_route(api: Harness) -> None:
    """The story's second acceptance criterion. `templates.router` registers
    `GET /templates/{name}/{version}` last and would parse `graph` as a version — a 422 —
    if this router were mounted after it."""
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/graph")

    assert response.status_code == HTTP_OK
    assert [node["id"] for node in response.json()["nodes"]] == ["sync"]


async def test_an_unknown_name_is_a_problem_document_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/no-such-template/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_stored_text_that_no_longer_validates_is_a_500_naming_the_line(
    api: Harness,
) -> None:
    api.store("broken", BROKEN)

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/broken/graph")

    assert response.status_code == HTTP_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "internal server error"
    assert response.json()["detail"] == f"line {BROKEN_LINE}: unknown kind"
    assert [error["reason"] for error in response.json()["errors"]] == ["unknown kind"]


async def test_reading_without_the_bearer_is_a_401(api: Harness) -> None:
    async with api.anonymous() as client:
        response = await client.get(f"{TEMPLATES}/leaf/graph")

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


# ── the contract ─────────────────────────────────────────────────────────────


def test_the_router_publishes_one_path_with_both_methods_and_no_route_dependency() -> None:
    """The bearer comes from the mount (AD-4), never from a route."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], "/templates/{name}/graph"),
        (["POST"], "/templates/{name}/graph"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


def test_the_router_is_mounted_before_the_templates_router() -> None:
    """Registration order is what decides whether `graph` is a literal or a version.

    Read off the composition root's own source rather than off the built application: what
    matters is the order the two `include_router` calls are written in, and FastAPI keeps a
    mounted router as one opaque entry whose sub-routes are not addressable from `app.routes`.
    The behaviour that order produces is asserted over the wire above.
    """
    tree = ast.parse(inspect.getsource(composition_root))
    mounted = [
        ast.unparse(call.args[0])
        for call in ast.walk(tree)
        if isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "include_router"
    ]

    assert mounted.index("graph_text.router") < mounted.index("templates.router")


async def test_both_operations_are_published_with_a_summary_and_problem_refusals(
    api: Harness,
) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    operations = document["paths"][GRAPH_PATH]
    assert set(operations) == {"get", "post"}
    for method, statuses in (("get", ("404", "422", "500")), ("post", ("422",))):
        operation = operations[method]
        assert operation["summary"], method
        for status in statuses:
            content = operation["responses"][status]["content"]
            assert PROBLEM_MEDIA_TYPE in content, f"{method} {status}"
            assert content[PROBLEM_MEDIA_TYPE]["schema"]["$ref"].endswith("/ProblemDetail")


async def test_the_path_publishes_a_get_so_the_repo_wide_sweep_can_index_it(
    api: Harness,
) -> None:
    """`test_bearer_auth.py` reads `document["paths"][path]["get"]` for every published
    `/api/v1` path; a POST-only path fails that frozen test."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert "get" in document["paths"][GRAPH_PATH]


async def test_the_posted_body_declares_the_one_yaml_field(api: Harness) -> None:
    """AD-3: the browser's `POST` body type is generated from this document."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    schema = document["components"]["schemas"]["GraphTextIn"]
    assert set(schema["properties"]) == {"yaml"}
    assert schema["required"] == ["yaml"]
