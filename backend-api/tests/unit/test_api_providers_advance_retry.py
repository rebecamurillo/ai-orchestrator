"""`advance_retry_ports` hands the use case a unit of work it can enter (epic 8 story 3)."""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI

from orchestrator.api.errors import install_error_handlers
from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY
from orchestrator.api.providers_initiatives import advance_retry_ports
from orchestrator.application.use_cases.advance_retry import AdvanceRetryPorts
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.test_api_providers import RecordingSessionFactory

HTTP_OK = 200


def probe_app(factory: Any, engine: Any) -> tuple[FastAPI, list[AdvanceRetryPorts]]:
    app = FastAPI()
    install_error_handlers(app)
    setattr(app.state, SESSION_FACTORY, factory)
    setattr(app.state, ENGINE, engine)
    captured: list[AdvanceRetryPorts] = []

    @app.get("/probe")
    def probe(
        ports: Annotated[AdvanceRetryPorts, Depends(advance_retry_ports)],
    ) -> dict[str, bool]:
        captured.append(ports)
        with ports.uow:
            ports.uow.commit()
        return {"ok": True}

    return app, captured


async def test_the_use_case_enters_the_unit_of_work_and_the_session_closes() -> None:
    factory = RecordingSessionFactory()
    engine = FakeWorkflowEngine()
    app, captured = probe_app(factory, engine)

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        response = await client.get("/probe")

    assert response.status_code == HTTP_OK
    (ports,) = captured
    (session,) = factory.sessions
    assert ports.initiatives._session is session  # type: ignore[attr-defined]
    assert ports.advances._session is session  # type: ignore[attr-defined]
    assert ports.engine is engine
    assert session.calls == ["commit", "close"]
