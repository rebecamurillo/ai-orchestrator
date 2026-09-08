"""`walker_deps` wires the `LogReader` the verify redispatch reads its log tail with (5.5).

`StepPorts.logs` defaults to `None` and `walk._verify_failure` degrades to an empty tail
when it is — the same degrade every other optional port has, and the reason it needs a test
of its own: dropping the line in `startup.py` would send every redispatched Story back to
the agent with a `## Verify Failure` section holding the command, the code and nothing else
(FR-10), and no unit test that did not look here would fail.

`test_dbos_startup_agent.py` is frozen; this file is built the same way it is.
"""

from __future__ import annotations

from typing import Any

from orchestrator.domain.ports.logs import LogReader
from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.process.logs import RealLogReader
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


def test_the_walker_is_handed_a_log_reader(env: dict[str, str]) -> None:
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert ports.logs is not None
    assert isinstance(ports.logs, LogReader)


def test_it_is_the_same_reader_the_run_detail_reads_an_attempt_tail_with(
    env: dict[str, str],
) -> None:
    """One adapter for one port (SPEC CAP-12): the walker and `api/providers.py` read the
    same files the same way, so a redispatch shows what the Run detail shows."""
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert isinstance(ports.logs, RealLogReader)
