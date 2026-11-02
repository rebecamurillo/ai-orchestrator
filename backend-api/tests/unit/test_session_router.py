"""`GET /api/v1/runs/{run_id}/session`, and the two session kinds over `POST .../signals`
(story 2-3, AD-23)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_read_ports, signal_effect_ports
from orchestrator.api.providers_session import session_ports
from orchestrator.api.routers import session as session_router
from orchestrator.api.schemas.session import AnchorEditOut, SessionOut
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.session_checks import SessionPorts
from orchestrator.application.use_cases.session_view import SessionView
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.session_fixtures import (
    HEAD_SHA,
    MODEL,
    SPEC_FOLDER,
    WORKTREE,
    SessionWorld,
    a_session_world,
)
from tests.unit.fakes.git import FakeGit

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

RUNS = "/api/v1/runs"
STORIES = f"{SPEC_FOLDER}/stories.yaml"


class Api:
    def __init__(self, env: dict[str, str], session: SessionWorld) -> None:
        self.session = session
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[signal_effect_ports] = self._effect_ports
        self.app.dependency_overrides[session_ports] = lambda: session_ports(session.ports)
        self.app.dependency_overrides[run_read_ports] = lambda: RunReadPorts(
            runs=session.world.ports.runs, steps=session.world.ports.steps
        )
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _effect_ports(self) -> Iterator[SignalEffectPorts]:
        yield self.session.ports

    @property
    def run_id(self) -> str:
        return str(self.session.world.run.id)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    git = FakeGit(
        changes={WORKTREE: (Change(path=STORIES, kind="modified"),)},
        statuses={WORKTREE: ""},
        heads={WORKTREE: [HEAD_SHA]},
    )
    return Api(env, a_session_world(git=git))


START = {
    "kind": "session_start",
    "payload": {"scope": "story", "harness": "claude", "model": MODEL},
}


async def test_a_stop_reads_an_available_session(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{api.run_id}/session")

    assert response.status_code == HTTP_OK, response.text
    assert response.json() == {
        "active": False,
        "available": True,
        "scopes": ["story", "epic", "run"],
        "scope": None,
        "harness": None,
        "model": None,
        "anchor_edits": [],
        # Story 2-5, 2026-11-02 (AD-23): the read model gains the session's turns.
        "turn_running": False,
        "turns": [],
    }


async def test_an_open_session_locks_the_run_and_names_its_edits(api: Api) -> None:
    async with api.client() as client:
        started = await client.post(f"{RUNS}/{api.run_id}/signals", json=START)
        api.session.turn()
        read = await client.get(f"{RUNS}/{api.run_id}/session")
        offered = await client.get(f"{RUNS}/{api.run_id}/signals")
        answer = await client.post(
            f"{RUNS}/{api.run_id}/signals", json={"kind": "answer", "payload": {"text": "go"}}
        )

    assert started.status_code == HTTP_OK, started.text
    assert started.json()["admitted_signals"] == ["cancel", "session_end"]
    assert offered.json()["admitted_signals"] == ["cancel", "session_end"]
    body = read.json()
    assert (body["active"], body["available"], body["scope"]) == (True, False, "story")
    assert (body["harness"], body["model"]) == ("claude", MODEL)
    assert body["anchor_edits"] == [{"path": STORIES, "kind": "modified"}]
    assert answer.status_code == HTTP_CONFLICT
    assert answer.json()["detail"] == "senior session open: end it before answer"


async def test_the_close_refuses_then_releases_once_the_edit_is_confirmed(api: Api) -> None:
    async with api.client() as client:
        await client.post(f"{RUNS}/{api.run_id}/signals", json=START)
        api.session.turn()
        refused = await client.post(f"{RUNS}/{api.run_id}/signals", json={"kind": "session_end"})
        extra = await client.post(
            f"{RUNS}/{api.run_id}/signals",
            json={"kind": "session_end", "payload": {"confirmed_paths": ["README.md"]}},
        )
        ended = await client.post(
            f"{RUNS}/{api.run_id}/signals",
            json={"kind": "session_end", "payload": {"confirmed_paths": [STORIES]}},
        )
        read = await client.get(f"{RUNS}/{api.run_id}/session")

    assert refused.status_code == HTTP_CONFLICT
    assert refused.json()["detail"].endswith(STORIES)
    assert extra.status_code == HTTP_UNPROCESSABLE
    assert ended.status_code == HTTP_OK, ended.text
    # the POST's own read model is the list view's, which answers without the parked row
    assert ended.json()["admitted_signals"] == ["skip_step", "skip_story", "cancel"]
    assert read.json()["active"] is False


async def test_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{new_id()}/session")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_run_id_that_is_not_a_uuid_is_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/not-a-uuid/session")

    assert response.status_code == HTTP_UNPROCESSABLE


def test_the_provider_carries_the_signal_ports_writers_git_and_registry() -> None:
    session = a_session_world()
    ports = session.ports

    built = session_ports(ports)

    assert isinstance(built, SessionPorts)
    assert built.writers is ports.signal.writers
    assert built.git is ports.git
    assert set(built.harnesses) == {"claude"}


def test_the_route_declares_its_problem_documents() -> None:
    assert set(session_router.REFUSALS) == {HTTP_NOT_FOUND, HTTP_UNPROCESSABLE}


def test_the_view_maps_onto_the_schema() -> None:
    view = SessionView(
        active=True,
        available=False,
        scopes=("story", "run"),
        scope="story",
        harness="claude",
        model=MODEL,
        anchor_edits=(Change(path=STORIES, kind="deleted"),),
    )

    out = SessionOut.of(view)

    assert out.scopes == ["story", "run"]
    assert out.anchor_edits == [AnchorEditOut(path=STORIES, kind="deleted")]
