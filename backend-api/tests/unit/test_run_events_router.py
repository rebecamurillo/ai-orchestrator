"""`GET /api/v1/runs/{run_id}/events` over an ASGI transport (agent-delivery-kit plan §7 v2).

The waiting loop's own arithmetic is `tests/unit/test_longpoll.py`'s and the read model is
`tests/unit/application/test_run_events_use_case.py`'s. What only a request can show is here:
the route shape, that an unknown id is a fast 404 rather than a thirty-second one, that `wait`
is bounded, that a change made while the connection is held is answered early, and that the
route is behind the one bearer.

`POLL_INTERVAL_S` is flattened to zero for the waiting tests, so a thirty-second hold costs
nothing and the assertions are about how many reads happened, not about elapsed time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from orchestrator.api.providers_run_events import run_event_reader
from orchestrator.api.routers import run_events as router_module
from orchestrator.api.schemas.run_events import RunEventsOut
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_events import RunEvent, run_event
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
PROBLEM_MEDIA_TYPE = "application/problem+json"

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
WRITTEN_AT = datetime(2026, 10, 1, 9, 5, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000f1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000f2")
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"

#: Read counts and waits, named because `PLR2004` refuses a bare integer in a comparison.
ONE_READ = 1
SECOND_READ = 2
SECONDS_WAITED = 3
SHORT_WAIT_S = 2


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "repo-init",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "spend_usd": Decimal("0.25"),
        "inputs": {"base_branch": "main"},
        "created_at": NOW,
        "updated_at": WRITTEN_AT,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


class Api:
    """One application whose events reader is the real use case over the shared fakes.

    `change_after` is how a transition mid-wait is scripted: the reader counts its own calls
    and, on the nth, replaces the stored Run with `becomes` — which is exactly what another
    transaction committing a park looks like to a held connection.
    """

    def __init__(
        self,
        env: dict[str, str],
        run: Run,
        *,
        change_after: int | None = None,
        becomes: Run | None = None,
    ) -> None:
        self.runs = FakeRunRepository([run])
        self.steps = FakeStepRunRepository()
        self.reads = 0
        self._change_after = change_after
        self._becomes = becomes
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[run_event_reader] = lambda: self._read
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _read(self, run_id: UUID) -> RunEvent:
        self.reads += 1
        if self._becomes is not None and self.reads == self._change_after:
            self.runs.runs[self._becomes.id] = self._becomes
        return run_event(RunReadPorts(runs=self.runs, steps=self.steps), run_id)

    def client(self, *, anonymous: bool = False) -> httpx.AsyncClient:
        headers = {} if anonymous else {"Authorization": f"Bearer {self.token}"}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )


def events_path(run_id: object) -> str:
    return f"/api/v1/runs/{run_id}/events"


@pytest.fixture
def instant(monkeypatch: pytest.MonkeyPatch) -> None:
    """A held connection with no seconds in it."""
    monkeypatch.setattr("orchestrator.infrastructure.longpoll.POLL_INTERVAL_S", 0)


# ── the route shape ──────────────────────────────────────────────────────────────────────


def test_the_router_declares_exactly_the_one_operation() -> None:
    routes = [route for route in router_module.router.routes if isinstance(route, APIRoute)]

    assert [(route.path, sorted(route.methods)) for route in routes] == [
        ("/runs/{run_id}/events", ["GET"]),
    ]
    for route in routes:
        assert route.summary
        assert HTTP_NOT_FOUND in route.responses
        assert HTTP_UNPROCESSABLE in route.responses
        assert route.response_model is RunEventsOut


async def test_the_published_operation_bounds_the_wait_in_the_contract(
    env: dict[str, str],
) -> None:
    api = Api(env, a_run())
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    operation = document["paths"]["/api/v1/runs/{run_id}/events"]["get"]
    wait = next(p for p in operation["parameters"] if p["name"] == "wait")
    assert (wait["schema"]["minimum"], wait["schema"]["maximum"]) == (0, router_module.MAX_WAIT_S)


# ── the immediate answer ─────────────────────────────────────────────────────────────────


async def test_without_a_wait_it_answers_the_current_state_at_once(env: dict[str, str]) -> None:
    run = a_run()
    api = Api(env, run)

    async with api.client() as client:
        response = await client.get(events_path(run.id))

    assert response.status_code == HTTP_OK, response.text
    assert response.json() == {
        "run_id": str(run.id),
        "status": "running",
        "updated_at": "2026-10-01T09:05:00Z",
        "changed": False,
        "admitted_signals": ["cancel"],
        "spend_usd": "0.250000",
        "budget_usd": "10.000000",
        "park_kind": None,
        "park_path": None,
    }
    assert api.reads == ONE_READ


# ── holding the connection ───────────────────────────────────────────────────────────────


async def test_a_change_while_the_connection_is_held_is_answered_early(
    env: dict[str, str], instant: None
) -> None:
    run = a_run()
    parked = run.model_copy(
        update={
            "status": "needs_you",
            "park_kind": "blocked",
            "updated_at": WRITTEN_AT + timedelta(seconds=30),
        }
    )
    api = Api(env, run, change_after=SECOND_READ, becomes=parked)

    async with api.client() as client:
        response = await client.get(events_path(run.id), params={"wait": 30})

    body = response.json()
    assert (body["changed"], body["status"], body["park_kind"]) == (True, "needs_you", "blocked")
    assert body["updated_at"] == "2026-10-01T09:05:30Z"
    # the first read is the baseline, the second is the one that saw the park — not thirty
    assert api.reads == SECOND_READ


async def test_a_run_that_does_not_move_answers_unchanged_after_exactly_the_wait(
    env: dict[str, str], instant: None
) -> None:
    run = a_run()
    api = Api(env, run)

    async with api.client() as client:
        response = await client.get(events_path(run.id), params={"wait": SECONDS_WAITED})

    assert response.json()["changed"] is False
    # the baseline read, then one per second of the wait
    assert api.reads == ONE_READ + SECONDS_WAITED


async def test_a_since_the_run_has_already_passed_answers_at_once(env: dict[str, str]) -> None:
    """The gap the watcher would otherwise be blind to: a change between two calls."""
    run = a_run()
    api = Api(env, run)

    async with api.client() as client:
        response = await client.get(
            events_path(run.id), params={"wait": 30, "since": "2026-10-01T09:00:00Z"}
        )

    assert response.json()["changed"] is True
    assert api.reads == ONE_READ


async def test_a_since_that_matches_the_stored_state_still_waits(
    env: dict[str, str], instant: None
) -> None:
    run = a_run()
    api = Api(env, run)

    async with api.client() as client:
        response = await client.get(
            events_path(run.id), params={"wait": SHORT_WAIT_S, "since": "2026-10-01T09:05:00Z"}
        )

    assert response.json()["changed"] is False
    assert api.reads == ONE_READ + SHORT_WAIT_S


# ── the refusals ─────────────────────────────────────────────────────────────────────────


async def test_an_unknown_run_is_a_problem_before_any_waiting(env: dict[str, str]) -> None:
    api = Api(env, a_run())

    async with api.client() as client:
        response = await client.get(events_path(UNKNOWN_ID), params={"wait": 30})

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert api.reads == ONE_READ


async def test_a_wait_above_the_cap_is_refused(env: dict[str, str]) -> None:
    run = a_run()
    api = Api(env, run)

    async with api.client() as client:
        response = await client.get(events_path(run.id), params={"wait": 31})

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert api.reads == 0


async def test_a_naive_since_is_refused_rather_than_guessed_at(env: dict[str, str]) -> None:
    run = a_run()
    api = Api(env, run)

    async with api.client() as client:
        response = await client.get(
            events_path(run.id), params={"wait": 1, "since": "2026-10-01T09:05:00"}
        )

    assert response.status_code == HTTP_UNPROCESSABLE
    assert api.reads == 0


async def test_the_route_is_behind_the_bearer(env: dict[str, str]) -> None:
    run = a_run()
    api = Api(env, run)

    async with api.client(anonymous=True) as client:
        response = await client.get(events_path(run.id))

    assert response.status_code == HTTP_UNAUTHORIZED
    assert api.reads == 0
