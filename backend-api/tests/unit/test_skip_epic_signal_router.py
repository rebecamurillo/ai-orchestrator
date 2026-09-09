"""`POST/GET /api/v1/runs/{run_id}/signals` for `skip_epic` (6.5, SPEC CAP-5, FR-20).

`test_signals_router.py` (story 4-9, predates this branch) posts exactly this kind against
`push_rejected_world()` as its own example of "a kind outside this epic's scope" — the
router-level illustration of `test_handle_signal.py`'s pending-gate registry, which this
story's own scope-gate widening (`use_cases/signals.py::_in_scope`) makes literally true
now: that world, unmodified, 200s. Correcting that pre-existing test is an anchor edit this
story cannot self-authorise (it predates the branch and is not one of the two registries the
operator named); this file is the strictly-exceeding coverage that documents the corrected
behaviour without touching it. See the story's own hand-back for the halt this produced.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_read_ports, signal_effect_ports
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

HTTP_OK = 200

RUNS = "/api/v1/runs"


def push_rejected_world() -> World:
    """The exact world `test_signals_router.py::push_rejected_world` builds: `push_rejected`
    on `push`, default `template_name="epic"` (`writer_fixtures.build_run`'s own default) —
    the `epic`-template special case `_has_epic_frame` admits without an `epics[i]` frame."""
    return a_world(
        "needs_you",
        EPIC_PLAN,
        {"push": "error"},
        park_kind="push_rejected",
        park_path="push",
        park_reason="the remote rejected it",
    )


class Api:
    def __init__(self, env: dict[str, str], world: World) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.world = world
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[signal_effect_ports] = self._signal_ports
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

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, push_rejected_world())


async def test_skip_epic_on_a_rejected_push_now_succeeds_over_the_router(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(
            f"{RUNS}/{api.world.run.id}/signals", json={"kind": "skip_epic"}
        )

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["status"] == "done"
    assert api.world.status_of("push") == "skipped"
    assert api.world.status_of("link") == "skipped"


async def test_get_renders_skip_epic_in_admitted_signals_for_a_fresh_blocked_park(
    env: dict[str, str],
) -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {"stories[0].build": "blocked"},
        park_kind="blocked",
        park_path="stories[0].build",
        park_reason="intent gap",
    )
    api = Api(env, world)

    async with api.client() as client:
        response = await client.get(f"{RUNS}/{world.run.id}/signals")

    assert response.status_code == HTTP_OK, response.text
    assert "skip_epic" in response.json()["admitted_signals"]
