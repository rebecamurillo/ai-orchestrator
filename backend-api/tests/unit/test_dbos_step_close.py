"""`infrastructure/dbos/step_close.py` builds the turn end's `SignalPorts` (epic 5 story 1, AC9)."""

from __future__ import annotations

from orchestrator.infrastructure.dbos.step_close import step_close_ports
from tests.unit.application.writer_fixtures import a_world


def test_the_ports_are_built_over_the_given_writers_and_engine() -> None:
    world = a_world("running", (("intake", "conversation"),), {"intake": "running"})

    ports = step_close_ports(world.ports, world.engine)

    assert ports.writers is world.ports
    assert ports.engine is world.engine
