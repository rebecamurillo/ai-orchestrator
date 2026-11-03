"""The `ChatChannel` adapters, behind one decision point (AD-25).

`open_channel` picks the adapter for a provider. `ChatChannels` is the `ChatChannelFactory`
the composition root injects. It owns one HTTP client for every channel it opens, and
`close()` must be called at shutdown, or the client's pooled connections are left open.
"""

from __future__ import annotations

import httpx

from orchestrator.domain.ports.chat import ChatChannel, ChatError, ChatProvider
from orchestrator.infrastructure.chat.http import new_client
from orchestrator.infrastructure.chat.mattermost import MattermostChannel
from orchestrator.infrastructure.chat.slack import SlackChannel


def open_channel(
    provider: ChatProvider,
    base_url: str,
    channel_id: str,
    token: str,
    client: httpx.Client | None = None,
) -> ChatChannel:
    if provider == "mattermost":
        return MattermostChannel(base_url, channel_id, token, client=client)
    if provider == "slack":
        return SlackChannel(base_url, channel_id, token, client=client)
    raise ChatError(f"unknown chat provider {provider!r}")


class ChatChannels:
    """`ChatChannelFactory` over `open_channel`, sharing one client."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._client = new_client(transport)

    def open(
        self, provider: ChatProvider, base_url: str, channel_id: str, token: str
    ) -> ChatChannel:
        return open_channel(provider, base_url, channel_id, token, client=self._client)

    def close(self) -> None:
        self._client.close()


__all__ = ["ChatChannels", "MattermostChannel", "SlackChannel", "open_channel"]
