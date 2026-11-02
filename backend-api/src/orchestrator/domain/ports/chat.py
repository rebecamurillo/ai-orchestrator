"""The `ChatChannel` port: one Project's chat channel, whichever platform holds it (AD-25).

Only the adapters in `infrastructure/chat/` call a chat platform. Everything this module names
is platform-neutral: a `Reply.body` already has the bot's mentions removed and a `cursor` is
opaque, so no caller ever parses a platform's syntax.

The shared fakes are `tests/unit/fakes/chat.py` (AD-18).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

ChatProvider = Literal["mattermost", "slack"]


@dataclass(frozen=True)
class ChatUser:
    """A person on the platform: its own `id`, and the `handle` people type."""

    id: str
    handle: str


@dataclass(frozen=True)
class ThreadRef:
    """The platform's id of a thread's root post."""

    id: str


@dataclass(frozen=True)
class Reply:
    """One person's post in a thread.

    `body` is `text` with every mention of the bot removed, by the match that sets
    `mentions_bot`. `cursor` is the adapter's position just after this reply, not an id, so a
    reply deleted later cannot strand a thread.
    """

    id: str
    author_id: str
    mentions_bot: bool
    text: str
    body: str
    cursor: str


class ChatError(Exception):
    """A platform call that failed. `detail` is the platform's own text, token redacted."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@runtime_checkable
class ChatChannel(Protocol):
    """Post, reply, read replies and check access in one channel. Every failure is `ChatError`."""

    def post(self, text: str, mentions: Sequence[ChatUser]) -> ThreadRef:
        """Start a thread naming `mentions`, each in the adapter's own syntax."""
        ...

    def reply(self, thread: ThreadRef, text: str) -> None:
        """Post `text` in `thread`."""
        ...

    def replies_since(self, thread: ThreadRef, cursor: str | None) -> list[Reply]:
        """Oldest first, every reply after `cursor` (`None` = from the start).

        The root, the bot's own posts, system posts and posts made through a webhook, a bot
        or a plugin are not replies.
        """
        ...

    def probe(self) -> str:
        """The bot's handle, without `@`, once the token and channel membership check out."""
        ...


@runtime_checkable
class ChatChannelFactory(Protocol):
    """Opens a `ChatChannel` from a Project's stored channel settings."""

    def open(
        self, provider: ChatProvider, base_url: str, channel_id: str, token: str
    ) -> ChatChannel: ...
