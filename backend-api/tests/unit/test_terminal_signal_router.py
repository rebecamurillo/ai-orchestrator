"""`POST/GET /api/v1/runs/{run_id}/signals` for the terminal kinds (6.7, SPEC CAP-7, FR-21).

`test_signals_router.py::test_a_kind_outside_this_epics_scope_is_a_409_not_available_yet`
used `terminal_start` as its vehicle — the last kind `use_cases/signals.py::_in_scope` still
refused. This story lands it, so no vehicle remained and the operator's standing
authorisation applies: that test is retired together with the now-dead predicate, and this
file is the coverage that proves the endpoint's real behaviour in its place.

It is strictly wider than what it replaces. The retired test asserted one 409 and its
sentence; this file asserts the 200 that sentence became, the three kinds' own effects over
the router, the 409 a session's own refusal answers, and — the assertion no scope-gate test
could make — that the screen and the server agree: `GET .../signals` offers exactly the kinds
`POST .../signals` will apply while a session is open, in both directions.

`PUT /runs/{id}/files` is asserted here too. 6.3 already wrote its `or run.terminal_session`
refusal; nothing in this story changes it, and a test that says so is what keeps a later
edit from quietly dropping the half of the rule no screen would notice.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import (
    run_files_write_ports,
    run_read_ports,
    signal_effect_ports,
)
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_files import RunFilesWritePorts
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.workspace import FakeWorkspace

HTTP_OK = 200
HTTP_CONFLICT = 409

RUNS = "/api/v1/runs"
BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
SPEC_FOLDER = "specs/gates"
STORY_PATH = f"{SPEC_FOLDER}/stories/1-answer.md"


def blocked_world(**over: object) -> World:
    return a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="intent gap",
        inputs={"spec_folder": SPEC_FOLDER},
        worktree_path="/work/wt/epics-1",
        **over,
    )


class Api:
    def __init__(self, env: dict[str, str], world: World) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.world = world
        self.workspace = FakeWorkspace("/work/wt/epics-1", {STORY_PATH: "---\nstatus: done\n---\n"})
        # `PUT /runs/{id}/files` commits through a scope its own provider opens; the fake
        # refuses a commit outside one, so the test opens it the way
        # `test_run_files_write_router.py` already does. The signal endpoint's own scope is
        # `world.ports.uow`, which `signal_run` enters and leaves for itself.
        self.file_uow = FakeUnitOfWork()
        self.file_uow.__enter__()
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[signal_effect_ports] = self._signal_ports
        self.app.dependency_overrides[run_files_write_ports] = self._write_ports
        self.app.dependency_overrides[run_read_ports] = lambda: RunReadPorts(
            runs=world.ports.runs, steps=world.ports.steps
        )
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _signal_ports(self) -> Iterator[SignalEffectPorts]:
        yield SignalEffectPorts(
            signal=self.world.signal_ports,
            git=FakeGit(),
            process=FakeProcessRunner(),
            work_dir="/work",
            read_environment=lambda _run_id: None,
        )

    def _write_ports(self) -> Iterator[RunFilesWritePorts]:
        yield RunFilesWritePorts(
            runs=self.world.ports.runs,
            workspace=lambda _root: self.workspace,
            git=FakeGit(),
            records=self.world.ports.records,
            clock=FakeClock(EPOCH),
            uow=self.file_uow,
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, blocked_world())


@pytest.fixture
def in_session(env: dict[str, str]) -> Api:
    return Api(env, blocked_world(terminal_session=True))


# ── the kind the retired test used as its example of "not available yet" ─────


async def test_terminal_start_now_succeeds_over_the_router(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(
            f"{RUNS}/{api.world.run.id}/signals", json={"kind": "terminal_start"}
        )

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["status"] == "needs_you"
    # `RunSummaryOut` carries no `terminal_session` — only the detail's own subclass does —
    # so the flag is read where it was written
    assert api.world.stored_run().terminal_session is True


async def test_terminal_release_ends_the_session_over_the_router(in_session: Api) -> None:
    async with in_session.client() as client:
        response = await client.post(
            f"{RUNS}/{in_session.world.run.id}/signals", json={"kind": "terminal_release"}
        )

    assert response.status_code == HTTP_OK, response.text
    assert in_session.world.stored_run().terminal_session is False


async def test_terminal_resume_resumes_the_run_over_the_router(in_session: Api) -> None:
    async with in_session.client() as client:
        response = await client.post(
            f"{RUNS}/{in_session.world.run.id}/signals", json={"kind": "terminal_resume"}
        )

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["status"] == "running"
    assert in_session.world.status_of(BUILD) == "done"
    assert in_session.world.status_of(VERIFY) == "queued"


# ── what a session refuses, as a problem document ────────────────────────────


async def test_answering_during_a_session_is_a_409_that_says_how_to_get_the_action_back(
    in_session: Api,
) -> None:
    async with in_session.client() as client:
        response = await client.post(
            f"{RUNS}/{in_session.world.run.id}/signals",
            json={"kind": "answer", "payload": {"text": "use the psycopg adapter"}},
        )

    assert response.status_code == HTTP_CONFLICT, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "terminal session in progress: Release it before answer"
    assert in_session.world.status_of(BUILD) == "blocked"


async def test_the_same_answer_succeeds_once_the_session_is_released(in_session: Api) -> None:
    """The 409 above is the session's doing, and Release is the way out of it — asserted as
    one sequence over the router, because that is the Operator's own."""
    run_id = in_session.world.run.id
    async with in_session.client() as client:
        await client.post(f"{RUNS}/{run_id}/signals", json={"kind": "terminal_release"})
        response = await client.post(
            f"{RUNS}/{run_id}/signals",
            json={"kind": "answer", "payload": {"text": "use the psycopg adapter"}},
        )

    assert response.status_code == HTTP_OK, response.text
    assert in_session.world.status_of(BUILD) == "queued"


async def test_editing_a_file_during_a_session_is_refused(in_session: Api) -> None:
    """6.3's own `or run.terminal_session` guard, over the endpoint that carries it."""
    async with in_session.client() as client:
        response = await client.put(
            f"{RUNS}/{in_session.world.run.id}/files",
            json={"path": STORY_PATH, "content": "---\nstatus: done\n---\n\nedited\n"},
        )

    assert response.status_code == HTTP_CONFLICT, response.text
    assert in_session.workspace.read(STORY_PATH) == "---\nstatus: done\n---\n"


async def test_editing_the_same_file_succeeds_without_a_session(api: Api) -> None:
    async with api.client() as client:
        response = await client.put(
            f"{RUNS}/{api.world.run.id}/files",
            json={"path": STORY_PATH, "content": "---\nstatus: done\n---\n\nedited\n"},
        )

    assert response.status_code == HTTP_OK, response.text


# ── the screen and the server agree ──────────────────────────────────────────


async def test_a_session_offers_exactly_cancel_and_release(in_session: Api) -> None:
    async with in_session.client() as client:
        response = await client.get(f"{RUNS}/{in_session.world.run.id}/signals")

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["admitted_signals"] == ["cancel", "terminal_release"]


async def test_the_same_stop_without_a_session_offers_its_own_actions(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{api.world.run.id}/signals")

    offered = response.json()["admitted_signals"]
    assert offered == ["answer", "skip_story", "skip_epic", "cancel"]
    assert "terminal_release" not in offered


async def test_every_kind_the_session_stops_offering_is_also_refused_by_the_endpoint(
    in_session: Api,
) -> None:
    """Both directions of the invariant in one test: nothing offered is refused, and nothing
    refused is offered."""
    run_id = in_session.world.run.id
    async with in_session.client() as client:
        offered = (await client.get(f"{RUNS}/{run_id}/signals")).json()["admitted_signals"]
        refused = []
        for kind in ("answer", "continue", "retry", "skip_story", "skip_epic", "budget_raise"):
            response = await client.post(f"{RUNS}/{run_id}/signals", json={"kind": kind})
            if response.status_code == HTTP_CONFLICT:
                refused.append(kind)

    assert offered == ["cancel", "terminal_release"]
    assert refused == ["answer", "continue", "retry", "skip_story", "skip_epic", "budget_raise"]
