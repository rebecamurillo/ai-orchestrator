"""One session's worth of `ChatPorts` (AD-25, story 3-3).

Every repository, the writers' among them, is built on one session, so 4-1's answer and its
thread's close commit together. The session is `open_writer_ports`'s, handed over by a
factory that returns it, so the writers' own scope is reused unchanged and the session is
closed on every path.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from orchestrator.application.jobs.chat_ports import ChatPorts
from orchestrator.domain.ports.notifier import Notifier
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyChatNoticeRepository,
    SQLAlchemyChatThreadRepository,
    SQLAlchemyProjectChannelRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
)
from orchestrator.infrastructure.db.writers import SessionFactory, open_writer_ports


@contextmanager
def open_chat_ports(
    session_factory: SessionFactory, notifier: Notifier | None = None
) -> Iterator[ChatPorts]:
    session = session_factory()
    with open_writer_ports(lambda: session, notifier=notifier) as writers:
        yield ChatPorts(
            writers=writers,
            threads=SQLAlchemyChatThreadRepository(session),
            channels=SQLAlchemyProjectChannelRepository(session),
            notices=SQLAlchemyChatNoticeRepository(session),
            projects=SQLAlchemyProjectRepository(session),
            repositories=SQLAlchemyRepositoryRepository(session),
        )
