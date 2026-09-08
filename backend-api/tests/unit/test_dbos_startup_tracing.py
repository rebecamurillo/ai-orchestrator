"""`infrastructure/dbos/startup.py::walker_deps` wires a real `Tracer` (AD-11, 5.2).

`StepPorts.tracer` defaults to `None` (AD-11's own "no tracer wired" degrade, which every
frozen unit test predating this story relies on), so dropping the `tracer=LangfuseTracer(
settings)` line from `walker_deps` would silently stop every row's `step_span` in
production without a single test failing anywhere else. `test_dbos_startup.py` is frozen
(predates this story) and does not check this; this file is the check, built the same way
that file's own `test_the_walker_is_wired_to_the_settings_it_will_run_on` is.
"""

from __future__ import annotations

from typing import Any

from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing import LangfuseTracer
from tests.unit.fakes.git import FakeGit


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


def test_walker_deps_wires_a_real_langfuse_tracer(env: dict[str, str]) -> None:
    deps = walker_deps(Settings(), sessions(), FakeGit())

    assert isinstance(deps.step_ports.tracer, LangfuseTracer)
