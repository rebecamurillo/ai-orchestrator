"""`walker_deps` wires the spend scope the `agent` tail reads the budget from (5.7).

`StepPorts.spend_writes` defaults to `None` and `agent_tail._spend_and_budget` degrades to
"skip the read" when it is — the same degrade every other optional port has, and the
reason it needs a test of its own: dropping the line in `startup.py` would leave every
Run silent about its own budget in production, and no unit test that did not look here
would fail.

`test_dbos_startup_agent.py` and `test_dbos_startup_logs.py` are frozen; this file is
built the same way both of them are.
"""

from __future__ import annotations

from typing import Any

from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit


def sessions() -> Any:
    def factory() -> Any:  # pragma: no cover — never called: nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


def test_the_walker_is_handed_a_spend_scope(env: dict[str, str]) -> None:
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert ports.spend_writes is not None
