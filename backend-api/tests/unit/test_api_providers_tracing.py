"""`api/providers.py::create_run_ports` and `run_view_ports` wire a real `Tracer` (AD-11, 5.2).

`CreateRunPorts.tracer`/`RunViewPorts.tracer` default to `None` (AD-11's own "no tracer
wired" degrade, which every frozen unit test in `test_api_providers.py` relies on — it
never sets one), so dropping the `tracer=LangfuseTracer(settings)` line from either
provider function would silently stop all tracing in production without a single test
failing anywhere else: every router test injects its own fake ports, and no e2e test reads
`trace_id`/`trace_url`. These two tests are that check, built the same minimal way
`test_api_providers.py`'s own `RecordingSessionFactory`/`_request_for` are — duplicated
rather than imported, because that file is frozen (predates this story) and this module
must not modify it (root `AGENTS.md` hard rule 1).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from orchestrator.api.providers import create_run_ports, run_view_ports
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing import LangfuseTracer
from orchestrator.main import create_app
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect."""

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


class RecordingSessionFactory:
    def __call__(self) -> RecordingSession:
        return RecordingSession()


def _request_for(app: FastAPI) -> Any:
    class Probe:
        def __init__(self, application: FastAPI) -> None:
            self.app = application

    return Probe(app)


def test_create_run_ports_wires_a_real_langfuse_tracer(env: dict[str, str]) -> None:
    app = create_app(
        Settings(),
        session_factory=RecordingSessionFactory(),
        engine=FakeWorkflowEngine(),
        git=FakeGit(),
    )

    ports = next(create_run_ports(_request_for(app)))

    assert isinstance(ports.tracer, LangfuseTracer)


def test_run_view_ports_wires_a_real_langfuse_tracer(env: dict[str, str]) -> None:
    app = create_app(Settings(), session_factory=RecordingSessionFactory())

    ports = next(run_view_ports(_request_for(app)))

    assert isinstance(ports.tracer, LangfuseTracer)
