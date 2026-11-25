"""`GET /initiatives`, `/projects/{id}/initiatives`, `/initiatives/{id}` over ASGI on the
shared fakes (story 4, epic 7): AC1, AC2, AC3's columns and counts, AC5's 404."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers_initiatives import initiative_read_ports
from orchestrator.api.routers import initiatives as initiative_router
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.initiative_read_world import NOW, ReadWorld, a_project, sequence

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
TWO = 2
PROBLEM = "application/problem+json"
LIST = "/api/v1/initiatives"


class Harness:
    def __init__(self, env: dict[str, str]) -> None:
        self.world = ReadWorld()
        self.token = env["ORCHESTRATOR_TOKEN"]
        self.app: FastAPI = create_app(Settings())
        self.app.dependency_overrides[initiative_read_ports] = self._ports

    def _ports(self) -> InitiativeReadPorts:
        return self.world.ports

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def harness(env: dict[str, str]) -> Harness:
    return Harness(env)


async def test_two_projects_list_newest_first_and_narrow_by_project(harness: Harness) -> None:
    world = harness.world
    other = a_project("Other", "other")
    world.projects.add(other)
    older = world.initiative(slug="older")
    newer = world.initiative(slug="newer", project_id=other.id)
    world.run(older, minutes=1)
    world.run(newer, minutes=2)

    async with harness.client() as client:
        both = (await client.get(LIST)).json()
        narrowed = (await client.get(f"{LIST}?project_id={other.id}")).json()
        nested = (await client.get(f"/api/v1/projects/{other.id}/initiatives")).json()

    assert [r["slug"] for r in both["items"]] == ["newer", "older"]
    assert {"project_name", "name", "step", "status", "updated_at"} <= set(both["items"][0])
    assert [r["slug"] for r in narrowed["items"]] == ["newer"]
    assert nested == narrowed
    assert both["next_cursor"] is None


@pytest.mark.parametrize(
    "path", [f"{LIST}?project_id={new_id()}", f"/api/v1/projects/{new_id()}/initiatives"]
)
async def test_an_unknown_project_is_a_404_problem(harness: Harness, path: str) -> None:
    async with harness.client() as client:
        response = await client.get(path)

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_the_filters_and_the_counts(harness: Harness) -> None:
    world = harness.world
    waiting = world.initiative(slug="waiting", sequence=sequence(deploy=True))
    world.run(waiting, status="needs_you", park_kind="blocked", park_path="x", park_reason="why")
    world.initiative(slug="old", cancelled_at=NOW - timedelta(days=40))

    async with harness.client() as client:
        needs = (await client.get(f"{LIST}?filter=needs_you")).json()
        ongoing = (await client.get(LIST)).json()
        everything = (await client.get(f"{LIST}?filter=all")).json()

    assert [r["slug"] for r in needs["items"]] == ["waiting"]
    assert [r["slug"] for r in ongoing["items"]] == ["waiting"]
    assert len(everything["items"]) == TWO
    assert [c["workflow"] for c in everything["columns"]] == ["spec", "build", "deploy"]
    assert everything["counts"]["need_you"] == 1
    assert everything["counts"]["cancelled"] == 1
    assert everything["counts"]["oldest_wait_at"] is not None


async def test_an_unknown_filter_is_refused(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.get(f"{LIST}?filter=everything")

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_the_detail_answers_the_step_turns_and_park_seq(harness: Harness) -> None:
    world = harness.world
    initiative = world.initiative()
    run = world.parked_spec(initiative, park_reason="step not closed · none")

    async with harness.client() as client:
        response = await client.get(f"{LIST}/{initiative.id}")

    body = response.json()
    assert response.status_code == HTTP_OK
    assert body["park_seq"] == run.park_seq
    assert body["status"] == "waiting for her"
    talk = body["workflows"][0]["steps"][0]
    assert talk["status"] == "waiting for her"
    assert [t["n"] for t in talk["turns"]] == [1, 2]


async def test_an_unknown_initiative_is_a_404_problem(harness: Harness) -> None:
    async with harness.client() as client:
        response = await client.get(f"{LIST}/{new_id()}")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


def test_the_router_declares_the_three_reads_and_the_two_actions() -> None:
    # story 5 of epic 7, 2026-11-22: cancel and start-next join the router, and create
    # joins `/initiatives`; the three reads stay GET-only apart from that path.
    methods: dict[str, set[str]] = {}
    for route in initiative_router.router.routes:
        methods.setdefault(route.path, set()).update(route.methods)  # type: ignore[attr-defined]

    assert methods == {
        "/initiatives": {"GET", "POST"},
        "/projects/{project_id}/initiatives": {"GET"},
        "/initiatives/{initiative_id}": {"GET"},
        "/initiatives/{initiative_id}/cancel": {"POST"},
        "/initiatives/{initiative_id}/start-next": {"POST"},
    }
