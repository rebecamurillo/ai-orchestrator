"""`infrastructure/dbos/startup.py::walker_deps` wires `NullTracer` when tracing is off (AD-11, 9-2).

Mirrors `test_dbos_startup_tracing.py` but with `LANGFUSE_BASE_URL=""` so
`tracing_enabled=False` and `build_tracer` returns `NullTracer`.  The `sessions()` helper
is replicated here rather than imported from that file — it is frozen (root AGENTS.md hard
rule 1).
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing import NullTracer
from tests.unit.fakes.git import FakeGit


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


def test_walker_deps_wires_null_tracer_when_tracing_off(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    deps = walker_deps(Settings(), sessions(), FakeGit())

    assert isinstance(deps.step_ports.tracer, NullTracer)
