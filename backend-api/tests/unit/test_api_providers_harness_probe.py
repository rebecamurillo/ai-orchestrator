"""`harness_probe_ports` (story 2-1): the registry `GET /harnesses/{name}/probe` runs on.

The composition root is the only place `Settings` is read (AD-2), so it is the only place
that can show that this instance's configuration reaches the probe: every other suite for the
route and the use case builds `HarnessProbePorts` by hand over
`tests/unit/fakes/harness.py`, and would keep passing if this provider named no harness at
all. The defect that shape hides is a concrete one — `ORCH_TEST_MODE` decides whether the
`fake` harness exists (`infrastructure/harness/registry.py`), and a provider that built the
registry from anything but this instance's `Settings` would offer a probe for a harness the
rest of the process does not have.

Driven the way `tests/unit/test_api_providers.py` drives `project_ports`: a one-route probe
application holding the adapters on `app.state`, whose route captures the ports it was handed.
Unlike the other providers this one opens no transaction, so no session factory is needed for
the dependency itself — it is on the state because `create_app`'s own wiring is not what is
under test here.
"""

from __future__ import annotations

from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI

from orchestrator.api.errors import install_error_handlers
from orchestrator.api.providers import SETTINGS, harness_probe_ports
from orchestrator.application.use_cases.harness_probe import HarnessProbePorts
from orchestrator.infrastructure.settings import Settings
from tests.unit.test_api_providers import HTTP_OK, call

#: The harness `ORCH_TEST_MODE` adds and nothing else may (AR-14).
FAKE = "fake"


def probe_app(settings: Settings) -> tuple[FastAPI, list[Any]]:
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SETTINGS, settings)
    captured: list[Any] = []

    @app.get("/probe")
    def probe(ports: Annotated[HarnessProbePorts, Depends(harness_probe_ports)]) -> dict[str, bool]:
        captured.append(ports)
        return {"ok": True}

    return app, captured


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


async def test_the_ports_carry_the_registry_this_instance_builds(settings: Settings) -> None:
    app, captured = probe_app(settings)

    response = await call(app, "/probe")

    assert response.status_code == HTTP_OK
    (ports,) = captured
    assert set(ports.harnesses) == {"claude", "codex", "local"}


async def test_the_registry_is_the_one_this_instance_s_settings_describe(
    settings: Settings,
) -> None:
    """Not a constant: on an instance in test mode the `fake` harness is a registry entry,
    and a probe offered for it is what proves the setting was read here."""
    app, captured = probe_app(Settings(orch_test_mode=True))

    await call(app, "/probe")

    (ports,) = captured
    assert FAKE in ports.harnesses
    assert ports.harnesses[FAKE].probe().ok is True


async def test_every_request_gets_its_own_registry(settings: Settings) -> None:
    """What the provider's own docstring promises: built fresh per request, on no session and
    no transaction, so nothing a probe does to an adapter outlives the request that made it."""
    app, captured = probe_app(settings)

    await call(app, "/probe")
    await call(app, "/probe")

    first, second = captured
    assert first is not second
    assert first.harnesses["claude"] is not second.harnesses["claude"]
