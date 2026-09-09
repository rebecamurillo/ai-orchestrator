"""Wiring the scheduled jobs that need the engine itself (SPEC CAP-7, FR-21).

`infrastructure/jobs.py` builds the two sweeps of SPEC CAP-11 from a session factory and a
`Git`. `terminal_poll` cannot join them, and the reason is a real one rather than a filing
preference: it *sends a signal*, so it needs `SignalPorts(writers, engine)` — and
`scheduled_jobs(settings, session_factory, git)` is never handed a `WorkflowEngine`.
`infrastructure/dbos/startup.py` is where the engine lives (`_SERVING` holds it), so this
module is registered from there, by `schedule_engine_jobs`, beside `schedule_jobs`.

The shape is otherwise `jobs.py`'s exactly: a zero-argument callable per job, opening its own
unit of work on every fire rather than holding a connection across however long a 30-second
cron runs for. `open_writer_ports` is the same scope `api/providers.py::signal_effect_ports`
gives `handle_signal`, so the poll's `signal_run` writes through the ports every other
Operator transition writes through (AD-8).
"""

from __future__ import annotations

from collections.abc import Callable

from orchestrator.application.jobs.terminal_poll import TerminalPollPorts, run_terminal_poll
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.db import open_writer_ports
from orchestrator.infrastructure.db.writers import SessionFactory
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.workspace import FsWorkspace

#: The name `engine.schedule` registers it under, and the key of its own cron setting.
TERMINAL_POLL_NAME = "terminal_poll"


def _terminal_poll_job(
    session_factory: SessionFactory, git: Git, engine: WorkflowEngine
) -> Callable[[], None]:
    def run() -> None:
        with open_writer_ports(session_factory) as writers:
            ports = TerminalPollPorts(
                signal=SignalPorts(writers=writers, engine=engine),
                git=git,
                # the class itself, not an instance: the root is one Run's own worktree,
                # which the poll only knows once it has read the Run
                workspace=FsWorkspace,
            )
            run_terminal_poll(ports)

    return run


def engine_jobs(
    settings: Settings, session_factory: SessionFactory, git: Git, engine: WorkflowEngine
) -> list[tuple[str, str, Callable[[], None]]]:
    """`(name, cron, job)` for every scheduled job that signals a Run through the engine."""
    return [
        (
            TERMINAL_POLL_NAME,
            settings.terminal_poll_cron,
            _terminal_poll_job(session_factory, git, engine),
        )
    ]
