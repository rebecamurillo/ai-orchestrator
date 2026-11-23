"""The `SignalPorts` a step session's turn end sends `step_close` through (epic 5, AD-38).

The same shape as `infrastructure/terminal_jobs.py::_terminal_poll_job`'s: the writers of
the turn's own scope and the engine, so `signal_run` writes the gate record and the effect
in one unit of work and then wakes the walk."""

from __future__ import annotations

from orchestrator.application.use_cases.signal_apply import SignalPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.ports.engine import WorkflowEngine


def step_close_ports(writers: WriterPorts, engine: WorkflowEngine) -> SignalPorts:
    return SignalPorts(writers=writers, engine=engine)
