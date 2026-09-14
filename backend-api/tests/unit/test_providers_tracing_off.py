"""`api/providers.py` wires `NullTracer` when `LANGFUSE_BASE_URL` is blank (AD-11, 9-2).

Mirrors `test_api_providers_tracing.py` but with `LANGFUSE_BASE_URL=""` so
`tracing_enabled=False` and `build_tracer` returns `NullTracer`.  The helper classes are
replicated here rather than imported from that file — it is frozen (root AGENTS.md hard
rule 1).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI

from orchestrator.api.providers import (
    create_run_ports,
    history_ports,
    readiness_ports,
    run_view_ports,
)
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing import NullTracer
from orchestrator.main import create_app
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit


# ── helpers (replicated from test_api_providers_tracing.py — that file is frozen) ────────

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


# ── tracing-off wiring tests ──────────────────────────────────────────────────────────────

def test_create_run_ports_wires_null_tracer_when_tracing_off(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    app = create_app(
        Settings(),
        session_factory=RecordingSessionFactory(),
        engine=FakeWorkflowEngine(),
        git=FakeGit(),
    )

    ports = next(create_run_ports(_request_for(app)))

    assert isinstance(ports.tracer, NullTracer)


def test_readiness_ports_wires_null_tracer_when_tracing_off(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    app = create_app(
        Settings(),
        session_factory=RecordingSessionFactory(),
        engine=FakeWorkflowEngine(),
        git=FakeGit(),
    )

    ports = next(readiness_ports(_request_for(app)))

    assert isinstance(ports.create_run.tracer, NullTracer)


def test_run_view_ports_wires_null_tracer_when_tracing_off(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    app = create_app(Settings(), session_factory=RecordingSessionFactory())

    ports = next(run_view_ports(_request_for(app)))

    assert isinstance(ports.tracer, NullTracer)


def test_history_ports_wires_null_tracer_when_tracing_off(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    app = create_app(Settings(), session_factory=RecordingSessionFactory())

    ports = next(history_ports(_request_for(app)))

    assert isinstance(ports.tracer, NullTracer)
