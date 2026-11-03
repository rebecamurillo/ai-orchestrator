"""Ports for the Project chat-channel routes (story 3-4, AD-25).

The `ChatChannelFactory` is the one `main.py` builds and stores under `app.state.chat`; it
owns a pooled HTTP client, which `main()` closes at shutdown.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers_base import CRYPTO, SESSION_FACTORY, from_state
from orchestrator.application.use_cases.project_channel import ChannelPorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyProjectChannelRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyUnitOfWork,
)

#: The `app.state` attribute `create_app` stores the chat factory under.
CHAT = "chat"


def channel_ports(request: Request) -> Iterator[ChannelPorts]:
    """The ports a channel use case runs on, inside one transaction."""
    session_factory = from_state(request, SESSION_FACTORY)
    crypto = from_state(request, CRYPTO)
    factory = from_state(request, CHAT)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield ChannelPorts(
            uow=uow,
            projects=SQLAlchemyProjectRepository(uow.session),
            channels=SQLAlchemyProjectChannelRepository(uow.session),
            crypto=crypto(),
            clock=SystemClock(),
            factory=factory,
        )
