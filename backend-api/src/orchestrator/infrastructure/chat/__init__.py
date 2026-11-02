"""The `ChatChannel` adapters, behind one decision point (AD-25).

`open_channel` picks the adapter for a provider. `ChatChannels` is the same decision as the
`ChatChannelFactory` port's object, for the composition root to inject.
"""

from __future__ import annotations

from orchestrator.domain.ports.chat import ChatChannel, ChatError, ChatProvider
from orchestrator.infrastructure.chat.mattermost import MattermostChannel


def open_channel(provider: ChatProvider, base_url: str, channel_id: str, token: str) -> ChatChannel:
    if provider == "mattermost":
        return MattermostChannel(base_url, channel_id, token)
    if provider == "slack":
        raise ChatError("slack is not available yet")
    raise ChatError(f"unknown chat provider {provider!r}")


class ChatChannels:
    """`ChatChannelFactory` over `open_channel`."""

    def open(
        self, provider: ChatProvider, base_url: str, channel_id: str, token: str
    ) -> ChatChannel:
        return open_channel(provider, base_url, channel_id, token)


__all__ = ["ChatChannels", "MattermostChannel", "open_channel"]
