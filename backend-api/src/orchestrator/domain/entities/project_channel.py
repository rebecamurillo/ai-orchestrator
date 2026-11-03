"""A Project's chat channel (AD-25): where its stops are posted and who may answer them.

No stored row means `off`. The bot token is Fernet ciphertext by the time it reaches this
module, and it is never a Project env var, so it can never reach `env_for(attempt)` (AD-5
amendment). The read model carries `token_set` and nothing of the token.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Literal
from urllib.parse import urlsplit
from uuid import UUID

from orchestrator.domain.ports.chat import ChatProvider, ChatUser

CHANNEL_OFF: Final = "off"

#: What a Project's channel setting reads as: a platform, or `off` when no row is stored.
ChannelSetting = Literal["off", "mattermost", "slack"]

BASE_URL_SCHEMES: Final = ("http", "https")


def _has_whitespace(value: str) -> bool:
    return any(character.isspace() for character in value)


def is_valid_base_url(url: str) -> bool:
    """`http(s)://host[:port][/path]`: no whitespace, userinfo, query or fragment."""
    if _has_whitespace(url) or "?" in url or "#" in url:
        return False
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 — a malformed port raises only when read
    except ValueError:
        return False
    return parts.scheme in BASE_URL_SCHEMES and bool(parts.hostname) and "@" not in parts.netloc


def is_valid_channel_id(value: str) -> bool:
    return bool(value) and not _has_whitespace(value)


def is_valid_user_id(value: str) -> bool:
    return bool(value) and not _has_whitespace(value)


def is_valid_handle(value: str) -> bool:
    """A handle as people type it, without the `@` each adapter adds in its own syntax."""
    return bool(value) and "@" not in value and not _has_whitespace(value)


@dataclass(frozen=True)
class ProjectChannelView:
    """The channel as an endpoint may return it."""

    provider: ChannelSetting
    base_url: str | None
    channel_id: str | None
    token_set: bool
    allowed_users: tuple[ChatUser, ...]
    metadata_only: bool

    @classmethod
    def off(cls) -> ProjectChannelView:
        return cls(
            provider=CHANNEL_OFF,
            base_url=None,
            channel_id=None,
            token_set=False,
            allowed_users=(),
            metadata_only=False,
        )


@dataclass(frozen=True)
class ProjectChannel:
    """One Project's stored channel."""

    project_id: UUID
    provider: ChatProvider
    base_url: str
    channel_id: str
    token_enc: str = field(repr=False)
    allowed_users: tuple[ChatUser, ...]
    metadata_only: bool
    created_at: datetime
    updated_at: datetime

    def view(self) -> ProjectChannelView:
        return ProjectChannelView(
            provider=self.provider,
            base_url=self.base_url,
            channel_id=self.channel_id,
            token_set=True,
            allowed_users=self.allowed_users,
            metadata_only=self.metadata_only,
        )
