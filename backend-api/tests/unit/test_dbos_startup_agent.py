"""`walker_deps` wires the three ports the `agent` kind needs, and registers the kind (5.4).

Every one of these would fail silently without a test of its own. `StepPorts.harnesses`,
`harness_env` and `attempt_writes` all default to `None` — the degrade that keeps every
frozen `StepPorts(...)` construction working — so a dropped line here would turn every
dispatch into an `internal` park in production and nothing else would notice. The same is
true of the kind import: `register` runs when `application/steps/agent.py` is imported, and
this module is the only place that imports it (`infrastructure/dbos/startup.py`'s own
docstring says why it is not `application/steps/__init__.py`).

`test_dbos_startup.py` and `test_dbos_startup_tracing.py` are frozen; this file is built
the same way both of them are.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps.agent import KIND, AgentExecutor
from orchestrator.application.steps.registry import EXECUTORS
from orchestrator.domain.ports.harness import Harness, HarnessEnv
from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.harness import ClaudeHarness
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


def test_importing_startup_registers_the_agent_kind() -> None:
    """The import in `startup.py` is the whole registration (AD-9)."""
    assert isinstance(EXECUTORS[KIND], AgentExecutor)


def test_the_walker_is_handed_the_harness_registry(env: dict[str, str]) -> None:
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert ports.harnesses is not None
    assert list(ports.harnesses) == ["claude"]
    assert isinstance(ports.harnesses["claude"], Harness)


def test_the_registry_starts_its_processes_through_the_walkers_own_runner(
    env: dict[str, str],
) -> None:
    """AD-14: one `ProcessRunner`, so one object can kill every group this process made."""
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert ports.harnesses is not None
    harness = ports.harnesses["claude"]
    assert isinstance(harness, ClaudeHarness)
    assert harness.runner is ports.process


def test_the_walker_is_handed_an_environment_builder(env: dict[str, str]) -> None:
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert ports.harness_env is not None
    assert isinstance(ports.harness_env, HarnessEnv)


def test_the_walker_is_handed_a_way_to_open_one_attempt_write(env: dict[str, str]) -> None:
    """`sessions()` refuses to be called, so this also proves nothing opens one yet."""
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert ports.attempt_writes is not None


def test_the_environment_reader_is_bound_to_a_crypto_factory_it_never_calls(
    env: dict[str, str],
) -> None:
    """A factory, because `FernetCrypto` refuses the contract's placeholder key — and the
    frozen `test_dbos_startup.py` builds these deps with exactly that placeholder."""
    deps = walker_deps(Settings(), sessions(), FakeGit())

    assert deps.read_environment.keywords["crypto"] is not None  # type: ignore[attr-defined]
