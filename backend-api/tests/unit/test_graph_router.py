"""`GET /api/v1/templates/{name}/{version}/graph` over an ASGI transport (3.4).

A router of its own. `tests/unit/test_templates_router.py` asserts an exact six-entry route
list on `api/routers/templates.py`, and that file is an anchor: a seventh route there would
fail it. `api/routers/clone_check.py` set the precedent — same prefix, same bearer
dependency, invisible from outside — and this module is also where Epic 4's
`GET /runs/{id}/graph` belongs, which makes the split the destination rather than a detour.

Nothing is relaxed by it: the property that frozen test protects (that the templates router
publishes exactly its six operations) stays true, and `test_bearer_auth.py`'s repo-wide
sweeps — every published `/api/v1` path has a `get`, and every published operation refuses
an unauthenticated call — cover this path from the moment it is mounted.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import template_ports
from orchestrator.api.routers import graph as router_module
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

LEAF = "name: leaf\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"

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

#: `BROKEN`'s `uses:` line — the 500's `detail` names it.
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


# ── the graph ────────────────────────────────────────────────────────────────


async def test_a_known_version_answers_its_graph(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/caller/1/graph")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == ["first", "items.call", "items.after"]
    assert body["groups"] == [
        {
            "id": "items",
            "label": "items",
            "kind": "for_each",
            "members": ["items.call", "items.after"],
        }
    ]


async def test_the_edges_are_keyed_from_and_to(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/caller/1/graph")

    assert response.json()["edges"] == [
        {"from": "first", "to": "items.call"},
        {"from": "items.call", "to": "items.after"},
    ]


async def test_a_collapsed_call_carries_its_callee_and_no_gate(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/caller/1/graph")

    call = next(node for node in response.json()["nodes"] if node["id"] == "items.call")
    assert call["call"] == {"name": "leaf", "version": 1}
    assert call["label"] == "leaf@1"
    assert call["gate"] is None


async def test_a_leaf_version_answers_one_node_and_no_edges(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/leaf/1/graph")

    body = response.json()
    assert [node["id"] for node in body["nodes"]] == ["sync"]
    assert body["edges"] == []
    assert body["groups"] == []


# ── the refusals ─────────────────────────────────────────────────────────────


async def test_an_unknown_version_is_a_problem_document_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/caller/9/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_an_unknown_name_is_a_problem_document_404(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/nope/1/graph")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_version_that_is_not_a_number_is_a_problem_document_422(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/caller/not-a-number/graph")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_a_version_above_the_column_is_refused_at_the_path(api: Harness) -> None:
    """The same guard `GET /templates/{name}/{version}` carries: out of `integer` range is
    a 422 at the edge, never a driver error deep in a query."""
    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/caller/2147483648/graph")

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_without_the_bearer_it_is_a_401(api: Harness) -> None:
    async with api.anonymous() as client:
        response = await client.get(f"{TEMPLATES}/caller/1/graph")

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_stored_text_that_no_longer_validates_is_a_500_naming_the_line(
    api: Harness,
) -> None:
    """Unreachable while storage only accepts validated text; still answered, not crashed."""
    api.store("broken", BROKEN)

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/broken/1/graph")

    assert response.status_code == HTTP_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["detail"] == f"line {BROKEN_LINE}: unknown kind"


async def test_the_500_keeps_the_one_title_this_api_sends_for_the_status(
    api: Harness,
) -> None:
    """`api/errors.py` answers every other 500 with this phrase; two titles for one status
    is a contract a client keying on `title` cannot read."""
    api.store("broken", BROKEN)

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/broken/1/graph")

    assert response.json()["title"] == "internal server error"


async def test_the_500_carries_every_problem_the_validator_found(api: Harness) -> None:
    """The same `errors[]` the save route's 422 sends: one bad line is rarely the only one."""
    api.store("broken", BROKEN)

    async with api.client() as client:
        response = await client.get(f"{TEMPLATES}/broken/1/graph")

    errors = response.json()["errors"]
    assert [error["reason"] for error in errors] == ["unknown kind"]
    assert errors[0]["line"] == BROKEN_LINE
    assert errors[0]["template"] == "broken"


# ── the contract ─────────────────────────────────────────────────────────────


def test_the_router_publishes_the_template_graph_as_a_get_and_carries_no_dependency() -> None:
    """Containment, not an exact list: Epic 4's `GET /runs/{id}/graph` lands on this same
    router, and a test that had to be edited to let it land would be an anchor in its way.
    What must hold whatever else arrives is that this path is served, that it is a `GET`
    (`test_bearer_auth.py` indexes every published path's `get`), and that the bearer comes
    from the mount rather than from a route."""
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert (["GET"], "/templates/{name}/{version}/graph") in routes
    for methods, path in routes:
        assert "GET" in methods, path
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_the_operation_is_published_with_a_summary_and_its_refusals(
    api: Harness,
) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    operation = document["paths"][f"{TEMPLATES}/{{name}}/{{version}}/graph"]["get"]
    assert operation["summary"]
    for status in ("404", "422", "500"):
        content = operation["responses"][status]["content"]
        assert PROBLEM_MEDIA_TYPE in content, status
        assert content[PROBLEM_MEDIA_TYPE]["schema"]["$ref"].endswith("/ProblemDetail")


async def test_the_published_edge_is_from_and_to(api: Harness) -> None:
    """AD-3: the browser's types are generated from this document."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    assert set(document["components"]["schemas"]["EdgeOut"]["properties"]) == {"from", "to"}
