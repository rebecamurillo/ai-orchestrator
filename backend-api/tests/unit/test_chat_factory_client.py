"""`ChatChannels` owns one HTTP client for every channel it opens (3-1 review, 2026-11-02)."""

from __future__ import annotations

import httpx

from orchestrator.infrastructure.chat import ChatChannels, open_channel
from orchestrator.infrastructure.chat.mattermost import TIMEOUT_SECONDS, MattermostChannel


def test_every_channel_shares_the_factory_client() -> None:
    factory = ChatChannels()

    first = factory.open("mattermost", "https://a.test", "ch1", "tok-a")
    second = factory.open("mattermost", "https://b.test", "ch2", "tok-b")

    assert isinstance(first, MattermostChannel)
    assert isinstance(second, MattermostChannel)
    assert first._client is second._client is factory._client
    assert factory._client.timeout == httpx.Timeout(TIMEOUT_SECONDS)
    assert factory._client.follow_redirects is False


def test_close_closes_the_client() -> None:
    factory = ChatChannels()

    factory.close()

    assert factory._client.is_closed


def test_a_given_transport_is_used_and_closed_with_the_client() -> None:
    closed: list[bool] = []

    class Transport(httpx.MockTransport):
        def close(self) -> None:
            closed.append(True)

    factory = ChatChannels(transport=Transport(lambda _: httpx.Response(200, json={})))
    factory.close()

    assert closed == [True]


def test_open_channel_hands_its_client_to_the_adapter() -> None:
    client = httpx.Client()

    channel = open_channel("mattermost", "https://a.test", "ch1", "tok", client=client)

    assert isinstance(channel, MattermostChannel)
    assert channel._client is client


def test_two_bots_on_one_client_send_each_its_own_token_only() -> None:
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        assert "cookie" not in request.headers
        return httpx.Response(
            200, json={"id": "x", "username": "b"}, headers={"Set-Cookie": "MMAUTHTOKEN=s; Path=/"}
        )

    factory = ChatChannels(transport=httpx.MockTransport(respond))

    for token in ("tok-a", "tok-b"):
        channel = factory.open("mattermost", "https://chat.test", "ch1", token)
        channel.probe()

    assert seen == ["Bearer tok-a", "Bearer tok-a", "Bearer tok-b", "Bearer tok-b"]
