"""`readiness_ports` hands `start` the models the environment names (SPEC CAP-8, AD-20).

The composition root is the only place `Settings` is read (AD-2), so it is the only place
that can prove the setting reaches the use case. Every other suite for `start` builds
`HarnessReadinessPorts` by hand and would keep passing if `api/providers.py` never named
`readiness_models` at all — which is exactly the shape of the defect being fixed here: a
value that exists in the contract, is typed in `Settings`, and is never threaded.

Driven the way `tests/unit/test_api_providers.py` drives `project_ports`: a one-route probe
application holding the adapters on `app.state`, whose route captures the ports it is
handed. The session factory is that suite's own recording double — nothing here connects to
a database, and no route runs a use case.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI

from orchestrator.api.errors import install_error_handlers
from orchestrator.api.providers import ENGINE, GIT, SESSION_FACTORY, SETTINGS, readiness_ports
from orchestrator.application.use_cases.harness_readiness import HarnessReadinessPorts
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.test_api_providers import HTTP_OK, RecordingSessionFactory, call

OVERRIDE = "claude=some-route,codex=another-route,local=a-third-route"


def probe_app(settings: Settings) -> tuple[FastAPI, list[Any]]:
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SESSION_FACTORY, RecordingSessionFactory())
    setattr(app.state, ENGINE, FakeWorkflowEngine())
    setattr(app.state, SETTINGS, settings)
    setattr(app.state, GIT, FakeGit())
    captured: list[Any] = []

    @app.get("/probe")
    def probe(
        ports: Annotated[HarnessReadinessPorts, Depends(readiness_ports)],
    ) -> dict[str, bool]:
        captured.append(ports)
        return {"ok": True}

    return app, captured


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


async def test_the_models_are_the_ones_the_environment_names(settings: Settings) -> None:
    """Not a constant: the probe runs on an environment whose mapping is nothing like the
    committed one, and the ports must carry that one."""
    app, captured = probe_app(Settings(readiness_models=OVERRIDE))

    response = await call(app, "/probe")

    assert response.status_code == HTTP_OK
    (ports,) = captured
    assert ports.models == {
        "claude": "some-route",
        "codex": "another-route",
        "local": "a-third-route",
    }


async def test_the_committed_contract_reaches_start_through_the_same_wiring(
    settings: Settings,
) -> None:
    app, captured = probe_app(settings)

    await call(app, "/probe")

    assert captured[0].models == settings.readiness_models


async def test_the_budget_still_comes_from_the_same_settings_object(
    settings: Settings,
) -> None:
    """The neighbour this setting is threaded like, asserted beside it so a future edit
    cannot swap one for the other unnoticed."""
    app, captured = probe_app(settings)

    await call(app, "/probe")

    assert captured[0].budget_usd == settings.readiness_budget_usd
    assert isinstance(captured[0].budget_usd, Decimal)
