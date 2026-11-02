"""`infrastructure/db/chat.py::open_chat_ports`: every chat port on one session (story 3-3).

One session, so 4-1's answer and its thread's close commit together, and closed on every
path. The session is recorded rather than real; the SQL is `test_chat_repository_adapter.py`'s.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.jobs.chat_ports import ChatPorts
from orchestrator.domain.ports.repositories import (
    ChatNoticeRepository,
    ChatThreadRepository,
    ProjectChannelRepository,
    ProjectRepository,
    RepositoryRepository,
)
from orchestrator.infrastructure.db.chat import open_chat_ports
from tests.unit.fakes.notifier import FakeNotifier


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


class RecordingFactory:
    def __init__(self) -> None:
        self.sessions: list[RecordingSession] = []

    def __call__(self) -> Any:
        session = RecordingSession()
        self.sessions.append(session)
        return session


def test_every_port_is_built_on_one_session() -> None:
    factory = RecordingFactory()

    with open_chat_ports(factory) as chat:
        assert isinstance(chat, ChatPorts)
        assert isinstance(chat.threads, ChatThreadRepository)
        assert isinstance(chat.notices, ChatNoticeRepository)
        assert isinstance(chat.channels, ProjectChannelRepository)
        assert isinstance(chat.projects, ProjectRepository)
        assert isinstance(chat.repositories, RepositoryRepository)
        (session,) = factory.sessions
        held = {
            id(port._session)  # type: ignore[attr-defined]
            for port in (
                chat.threads,
                chat.notices,
                chat.channels,
                chat.projects,
                chat.repositories,
                chat.writers.runs,
                chat.writers.records,
            )
        }
        assert held == {id(session)}
        assert chat.writers.announcer is None

    assert session.calls == ["close"]


def test_a_notifier_gives_the_writers_their_announcer() -> None:
    with open_chat_ports(RecordingFactory(), FakeNotifier()) as chat:
        assert chat.writers.announcer is not None


def test_the_session_is_closed_when_the_block_raises() -> None:
    factory = RecordingFactory()

    with pytest.raises(RuntimeError), open_chat_ports(factory):
        raise RuntimeError("boom")

    assert factory.sessions[0].calls == ["close"]
