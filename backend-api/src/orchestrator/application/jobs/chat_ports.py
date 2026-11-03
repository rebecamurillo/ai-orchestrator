"""What `chat_poll` and its passes read and write through (story 3-3, AD-25).

`ChatPorts` is one session's worth of repositories (`infrastructure/db/chat.py::
open_chat_ports` builds it), so an answer and its thread's close can commit together (4-1).
Every read sits inside a `with chat.writers.uow:` block that closes before any `post` or
`reply`: no transaction is ever open across a platform call, and neither is the Run lock.

`ChatPollPorts` is one fire's: the factory that opens a Project's channel, the crypto that
opens its token, the clock every thread time comes from, and the process's own start, which
is what makes a `posting` row from an earlier process stale, and `signal`, on the same
writers, through which the read pass sends an answer (4-3). `chat_poll.py` re-exports it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from orchestrator.application.use_cases.signal_apply import SignalPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ports.chat import (
    ChatChannel,
    ChatChannelFactory,
    ChatRateLimited,
    ChatUser,
    Reply,
    ThreadRef,
)
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.crypto import Crypto
from orchestrator.domain.ports.repositories import (
    ChatNoticeRepository,
    ChatThreadRepository,
    ProjectChannelRepository,
    ProjectRepository,
    RepositoryRepository,
)

#: What a masked token reads as in a stored error.
MASK = "***"


@dataclass(frozen=True)
class ChatPorts:
    """The repositories one fire reads and writes, all on one session."""

    writers: WriterPorts
    threads: ChatThreadRepository
    channels: ProjectChannelRepository
    notices: ChatNoticeRepository
    projects: ProjectRepository
    repositories: RepositoryRepository


@dataclass(frozen=True)
class ChatPollPorts:
    """One fire of `chat_poll`."""

    chat: ChatPorts
    #: On `chat.writers`, with both mode callables, so an answer resumes the agent's session.
    signal: SignalPorts
    factory: ChatChannelFactory
    crypto: Callable[[], Crypto]
    clock: Clock
    #: `PUBLIC_BASE_URL`; blank leaves the Run link out.
    public_base_url: str
    reminder_hours: int
    #: When this backend process started, from the `Clock` (one backend process).
    started_at: datetime


@dataclass(frozen=True)
class OpenedChannel:
    """A Project's channel as this fire opened it: `chat` is `None`, and `error` says why,
    when its token could not be decrypted or the factory refused it."""

    channel: ProjectChannel
    chat: ChatChannel | None
    token: str = ""
    error: str | None = None


class RateLimitWatch:
    """A Project's opened channel for one fire, recording whether any call was refused for
    its rate (story 4-2 review, lead ruling 2026-11-03): once one was, no later pass for the
    Project calls the platform in that fire. Every call is passed through unchanged."""

    def __init__(self, chat: ChatChannel) -> None:
        self._chat = chat
        self.rate_limited = False

    def post(self, text: str, mentions: Sequence[ChatUser], trusted_suffix: str = "") -> ThreadRef:
        return self._watched(lambda: self._chat.post(text, mentions, trusted_suffix))

    def reply(
        self,
        thread: ThreadRef,
        text: str,
        mentions: Sequence[ChatUser] = (),
        trusted_suffix: str = "",
    ) -> None:
        self._watched(lambda: self._chat.reply(thread, text, mentions, trusted_suffix))

    def rendered_length(
        self, text: str, mentions: Sequence[ChatUser] = (), trusted_suffix: str = ""
    ) -> int:
        return self._chat.rendered_length(text, mentions, trusted_suffix)

    def replies_since(self, thread: ThreadRef, cursor: str | None) -> list[Reply]:
        return self._watched(lambda: self._chat.replies_since(thread, cursor))

    def follows(self, cursor: str, after: str | None) -> bool:
        return self._chat.follows(cursor, after)

    def probe(self) -> str:
        return self._watched(self._chat.probe)

    def _watched[T](self, call: Callable[[], T]) -> T:
        try:
            return call()
        except ChatRateLimited:
            self.rate_limited = True
            raise


def redacted(detail: str, token: str) -> str:
    """`detail` with the token masked: the adapters redact already, and this is the second
    guard, kept in the application where no infrastructure helper may be imported."""
    return detail.replace(token, MASK) if token else detail


def error_class(error: BaseException) -> str:
    return type(error).__name__
