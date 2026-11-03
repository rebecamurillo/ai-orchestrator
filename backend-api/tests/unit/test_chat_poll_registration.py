"""Wiring `chat_poll` (story 3-3, AD-25): `terminal_jobs.engine_jobs(…, chat=)`, the chat slot
`serving` fills and clears, and `main()` passing its `ChatChannels`.

The job is registered as `chat_poll` on `*/{CHAT_POLL_SECONDS} * * * * *` only when a chat
factory is given, so every existing call that passes none still sees `terminal_poll` alone.
`started_at` is read from the clock when the job is built. The job reads the slot on every
fire, and a fire after `serving` has exited (the factory closed at shutdown) does nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator import main as main_module
from orchestrator.application.jobs.chat_ports import ChatPollPorts
from orchestrator.infrastructure import terminal_jobs
from orchestrator.infrastructure.chat import ChatChannels
from orchestrator.infrastructure.dbos.startup import schedule_engine_jobs, serving
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.terminal_jobs import (
    CHAT_POLL_NAME,
    TERMINAL_POLL_NAME,
    current_chat,
    engine_jobs,
)
from tests.unit.fakes.chat import FakeChatChannelFactory
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit

BUILT_AT = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


class RecordingEngine:
    def __init__(self) -> None:
        self.scheduled: list[tuple[str, str]] = []

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        self.scheduled.append((name, cron))


def no_sessions() -> None:  # pragma: no cover — never called: building opens no session
    raise AssertionError("no session is opened while the jobs are built")


def settings(monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    for name, value in extra.items():
        monkeypatch.setenv(name, value)
    return Settings()  # type: ignore[call-arg]


def chat_job(jobs: list[tuple[str, str, Callable[[], None]]]) -> Callable[[], None]:
    return next(job for name, _, job in jobs if name == CHAT_POLL_NAME)


def test_without_a_chat_factory_only_the_terminal_poll_is_registered(env: dict[str, str]) -> None:
    jobs = engine_jobs(Settings(), no_sessions, FakeGit(), FakeWorkflowEngine())

    assert [name for name, _, _ in jobs] == [TERMINAL_POLL_NAME]


@pytest.mark.parametrize(("seconds", "cron"), [("30", "*/30 * * * * *"), ("12", "*/12 * * * * *")])
def test_a_chat_factory_registers_the_poll_on_its_seconds_cron(
    seconds: str, cron: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = engine_jobs(
        settings(monkeypatch, CHAT_POLL_SECONDS=seconds),
        no_sessions,
        FakeGit(),
        FakeWorkflowEngine(),
        chat=FakeChatChannelFactory(),
    )

    assert [(name, value) for name, value, _ in jobs] == [
        (TERMINAL_POLL_NAME, "*/30 * * * * *"),
        (CHAT_POLL_NAME, cron),
    ]
    assert CHAT_POLL_NAME == "chat_poll"


#: Story 4-3 (2026-11-03): the job builds `SignalPorts` on the chat ports' writers, so the
#: stand-in the fake `open_chat_ports` yields carries writers, where it was a bare string.
CHAT_PORTS = SimpleNamespace(writers=SimpleNamespace(attempts=SimpleNamespace(latest_for_run=None)))


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[ChatPollPorts]:
    seen: list[ChatPollPorts] = []
    opened: list[Any] = []

    @contextmanager
    def fake_open(session_factory: Any, notifier: Any = None) -> Iterator[SimpleNamespace]:
        opened.append((session_factory, notifier))
        yield CHAT_PORTS

    monkeypatch.setattr(terminal_jobs, "open_chat_ports", fake_open)
    monkeypatch.setattr(terminal_jobs, "run_chat_poll", seen.append)
    monkeypatch.setattr(terminal_jobs.SystemClock, "now", lambda self: BUILT_AT)
    return seen


def test_a_fire_with_an_empty_slot_does_nothing(
    env: dict[str, str], recorded: list[ChatPollPorts]
) -> None:
    job = chat_job(
        engine_jobs(
            Settings(), no_sessions, FakeGit(), FakeWorkflowEngine(), chat=FakeChatChannelFactory()
        )
    )

    assert current_chat() is None
    job()

    assert recorded == []


def test_a_fire_while_serving_polls_through_the_slots_factory(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, recorded: list[ChatPollPorts]
) -> None:
    factory = FakeChatChannelFactory()
    configured = settings(
        monkeypatch, PUBLIC_BASE_URL="https://orch.example.com", CHAT_REMINDER_HOURS="6"
    )
    job = chat_job(
        engine_jobs(configured, no_sessions, FakeGit(), FakeWorkflowEngine(), chat=factory)
    )

    with serving(RecordingEngine(), no_sessions, FakeGit(), chat=factory):  # type: ignore[arg-type]
        job()
    job()

    (ports,) = recorded
    assert ports.chat is CHAT_PORTS
    assert ports.signal.writers is CHAT_PORTS.writers
    assert ports.factory is factory
    assert ports.public_base_url == "https://orch.example.com"
    assert (ports.reminder_hours, ports.factory) == (6, factory)
    assert ports.started_at == BUILT_AT
    assert ports.clock.now() == BUILT_AT


def test_serving_holds_the_factory_only_while_it_serves(env: dict[str, str]) -> None:
    factory = FakeChatChannelFactory()

    with serving(RecordingEngine(), chat=factory):  # type: ignore[arg-type]
        assert current_chat() is factory
    assert current_chat() is None

    with pytest.raises(RuntimeError), serving(RecordingEngine(), chat=factory):  # type: ignore[arg-type]
        raise RuntimeError("uvicorn fell over")
    assert current_chat() is None


def test_serving_with_a_factory_schedules_the_chat_poll(env: dict[str, str]) -> None:
    engine = RecordingEngine()

    with serving(engine, no_sessions, FakeGit(), chat=FakeChatChannelFactory()):  # type: ignore[arg-type]
        schedule_engine_jobs(Settings())

    assert [name for name, _ in engine.scheduled] == [TERMINAL_POLL_NAME, CHAT_POLL_NAME]


def test_main_serves_with_its_chat_channels_in_the_slot(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    held: list[object] = []
    monkeypatch.setattr(main_module, "run_migrations", lambda settings: "head")
    monkeypatch.setattr(main_module.uvicorn, "run", lambda app, **kw: held.append(current_chat()))

    main_module.main()

    (chat,) = held
    assert isinstance(chat, ChatChannels)
    assert current_chat() is None
