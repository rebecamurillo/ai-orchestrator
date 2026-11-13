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

import structlog

from orchestrator.application.jobs.chat_poll import ChatPollPorts, run_chat_poll
from orchestrator.application.jobs.chat_ports import error_class
from orchestrator.application.jobs.terminal_poll import TerminalPollPorts, run_terminal_poll
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.domain.ports.chat import ChatChannelFactory
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.notifier import Notifier
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.crypto.factory import crypto_factory
from orchestrator.infrastructure.db import open_writer_ports
from orchestrator.infrastructure.db.chat import open_chat_ports
from orchestrator.infrastructure.db.writers import SessionFactory
from orchestrator.infrastructure.harness.registry import build_harnesses
from orchestrator.infrastructure.notify import build_notifier
from orchestrator.infrastructure.process.runner import RealProcessRunner
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.workspace import FsWorkspace

log = structlog.get_logger(__name__)

#: The name `engine.schedule` registers it under, and the key of its own cron setting.
TERMINAL_POLL_NAME = "terminal_poll"
#: The chat job (AD-25), on `*/{CHAT_POLL_SECONDS} * * * * *`.
CHAT_POLL_NAME = "chat_poll"
CHAT_POLL_CRON = "*/{seconds} * * * * *"

#: The chat factory `dbos/startup.py::serving` holds while the server runs, cleared on exit:
#: the factory's client is closed at shutdown, so a fire after that must not reach it. The
#: chat job reads this on every fire rather than closing over the factory.
CHAT_SLOT: list[ChatChannelFactory] = []


def current_chat() -> ChatChannelFactory | None:
    return CHAT_SLOT[-1] if CHAT_SLOT else None


def _terminal_poll_job(
    session_factory: SessionFactory,
    git: Git,
    engine: WorkflowEngine,
    notifier: Notifier | None = None,
) -> Callable[[], None]:
    def run() -> None:
        with open_writer_ports(session_factory, git=git, notifier=notifier) as writers:
            ports = TerminalPollPorts(
                signal=SignalPorts(writers=writers, engine=engine),
                git=git,
                # the class itself, not an instance: the root is one Run's own worktree,
                # which the poll only knows once it has read the Run
                workspace=FsWorkspace,
            )
            run_terminal_poll(ports)

    return run


def _chat_poll_job(
    settings: Settings, session_factory: SessionFactory, engine: WorkflowEngine
) -> Callable[[], None]:
    """The chat job. Its `SignalPorts` carry both mode callables, wired as
    `api/providers.py::signal_effect_ports` wires them, so a thread answer resumes the
    recorded session (story 4-3); without them `_check_mode` would choose `restart`."""
    started_at = SystemClock().now()
    crypto = crypto_factory(settings)
    notifier = build_notifier(settings)
    harnesses = build_harnesses(settings, RealProcessRunner())

    def resumable(name: str) -> bool:
        return name in harnesses and harnesses[name].capabilities.resume

    def run() -> None:
        factory = current_chat()
        if factory is None:
            return
        try:
            with open_chat_ports(session_factory, notifier) as chat:
                run_chat_poll(
                    ChatPollPorts(
                        chat=chat,
                        signal=SignalPorts(
                            writers=chat.writers,
                            engine=engine,
                            harness_is_resumable=resumable,
                            latest_attempt_for_run=chat.writers.attempts.latest_for_run,
                        ),
                        factory=factory,
                        crypto=crypto,
                        clock=SystemClock(),
                        public_base_url=settings.public_base_url,
                        reminder_hours=settings.chat_reminder_hours,
                        started_at=started_at,
                    )
                )
        except Exception as error:
            log.warning("chat poll failed", error_class=error_class(error))

    return run


def engine_jobs(
    settings: Settings,
    session_factory: SessionFactory,
    git: Git,
    engine: WorkflowEngine,
    chat: ChatChannelFactory | None = None,
) -> list[tuple[str, str, Callable[[], None]]]:
    """`(name, cron, job)` for every scheduled job that signals a Run through the engine, and
    `chat_poll` when a chat factory is given (story 3-3)."""
    jobs = [
        (
            TERMINAL_POLL_NAME,
            settings.terminal_poll_cron,
            _terminal_poll_job(session_factory, git, engine, build_notifier(settings)),
        )
    ]
    if chat is not None:
        cron = CHAT_POLL_CRON.format(seconds=settings.chat_poll_seconds)
        jobs.append((CHAT_POLL_NAME, cron, _chat_poll_job(settings, session_factory, engine)))
    return jobs
