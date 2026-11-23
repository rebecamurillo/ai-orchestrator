"""`GET /runs/{id}/steps/{seq}/attempts/{n}/drawer` over an ASGI transport (story 5, AC8, AC10)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from orchestrator.api import providers_step_drawer
from orchestrator.api.protected_routes import install_run_page_routes
from orchestrator.api.providers_base import SESSION_FACTORY, SETTINGS
from orchestrator.api.providers_step_drawer import step_drawer_ports
from orchestrator.api.routers import run_step_drawer as router_module
from orchestrator.api.schemas import run_step_drawer as schemas
from orchestrator.application.use_cases.run_step_drawer import StepDrawerPorts
from orchestrator.domain.entities.facts import AttemptFacts, EventFact, FactSet
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.log_facts import LogFactsCapabilities
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.test_run_step_drawer import NOW, a_row, a_run, an_attempt
from tests.unit.fakes.facts import FakeFactSetRepository
from tests.unit.fakes.git_history import FakeGitHistory
from tests.unit.fakes.log_facts import ScriptedLogFacts
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

PATH = "/api/v1/runs/{run_id}/steps/{seq}/attempts/{n}/drawer"
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401
PROBLEM = "application/problem+json"
UNKNOWN = "01a06887-79ab-759b-97a0-71c32ad939c2"


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.run = a_run()
        self.row = a_row(self.run)
        self.attempt = an_attempt(
            self.row, started_at=NOW, ended_at=NOW, exit_code=0, cost_usd=Decimal("0.5")
        )
        self.ports = StepDrawerPorts(
            runs=FakeRunRepository([self.run]),
            steps=FakeStepRunRepository([self.row]),
            attempts=FakeAttemptRepository([self.attempt]),
            logs=FakeLogReader(),
            history=FakeGitHistory(),
            facts=FakeFactSetRepository(),
            extractors={},
        )
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[step_drawer_ports] = lambda: self.ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def client(self, *, bearer: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if bearer else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )

    def url(self, run_id: object = None, seq: object = 1, n: object = 0) -> str:
        return f"/api/v1/runs/{run_id or self.run.id}/steps/{seq}/attempts/{n}/drawer"


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_a_known_row_answers_the_drawer(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(api.url())

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["header"]["n"] == 1
    assert body["header"]["cost_usd"] == "0.500000"
    assert body["header"]["started_at"].endswith("Z")
    assert body["log"]["attempt_id"] == str(api.attempt.id)
    assert body["files_read"] == {"state": "not_recorded", "paths": []}
    assert body["files_written"]["state"] == "none"
    assert body["run_order"] is None
    assert body["attempts"] == [{"n": 1, "status": "done"}]


async def test_an_agent_attempt_with_read_events_lists_its_paths(api: Api) -> None:
    row = a_row(api.run, kind="agent")
    attempt = an_attempt(row, started_at=NOW)
    extractor = ScriptedLogFacts(name="claude", version=2)
    extractor.capabilities = LogFactsCapabilities(False, False, False, False, files_read=True)
    facts = FakeFactSetRepository()
    fact_set = FactSet(
        id=new_id(),
        attempt_id=attempt.id,
        run_id=api.run.id,
        extractor="claude",
        extractor_version=2,
        read_at=NOW,
        status="ok",
    )
    events = tuple(
        EventFact(at=NOW, conversation="main", kind="read", path=p) for p in ("b.py", "a.py")
    )
    facts.add(fact_set, AttemptFacts(events=events))
    api.ports = StepDrawerPorts(
        runs=api.ports.runs,
        steps=FakeStepRunRepository([row]),
        attempts=FakeAttemptRepository([attempt]),
        logs=FakeLogReader(),
        history=FakeGitHistory(),
        facts=facts,
        extractors={"claude": extractor},
    )

    async with api.client() as client:
        response = await client.get(api.url(seq=row.seq))

    assert response.json()["files_read"] == {"state": "listed", "paths": ["a.py", "b.py"]}


async def test_unknown_run_seq_and_attempt_are_404_problems(api: Api) -> None:
    async with api.client() as client:
        responses = [
            await client.get(api.url(run_id=UNKNOWN)),
            await client.get(api.url(seq=9)),
            await client.get(api.url(n=3)),
        ]

    for response in responses:
        assert response.status_code == HTTP_NOT_FOUND
        assert response.headers["content-type"].startswith(PROBLEM)


@pytest.mark.parametrize("kwargs", [{"seq": -1}, {"n": -1}, {"run_id": "not-a-uuid"}])
async def test_malformed_segments_are_422(api: Api, kwargs: dict[str, object]) -> None:
    async with api.client() as client:
        response = await client.get(api.url(**kwargs))

    assert response.status_code == HTTP_UNPROCESSABLE


async def test_without_the_bearer_it_is_401(api: Api) -> None:
    async with api.client(bearer=False) as client:
        response = await client.get(api.url())

    assert response.status_code == HTTP_UNAUTHORIZED


def test_the_path_is_published_with_a_declared_401(api: Api) -> None:
    operation = api.app.openapi()["paths"][PATH]["get"]

    assert "401" in operation["responses"]


def test_install_run_page_routes_mounts_the_path() -> None:
    app = FastAPI()

    install_run_page_routes(app)

    assert PATH in app.openapi()["paths"]


def test_the_provider_builds_the_ports_from_app_state(env: dict[str, str]) -> None:
    app = FastAPI()
    setattr(app.state, SETTINGS, Settings(**{k.lower(): v for k, v in env.items()}))
    setattr(app.state, SESSION_FACTORY, sessionmaker(create_engine("sqlite://")))
    request = Request({"type": "http", "app": app})
    generator: Iterator[StepDrawerPorts] = providers_step_drawer.step_drawer_ports(request)

    ports = next(generator)
    generator.close()

    assert isinstance(ports, StepDrawerPorts)


def test_the_schema_module_is_importable() -> None:
    assert schemas.StepDrawerOut is not None


def test_the_router_declares_the_one_get() -> None:
    routes = [(sorted(r.methods), r.path) for r in router_module.router.routes]

    assert routes == [(["GET"], "/runs/{run_id}/steps/{seq}/attempts/{n}/drawer")]
