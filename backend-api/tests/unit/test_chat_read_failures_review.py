"""The adapters after the 4-3 review (2026-11-03): a Mattermost 404 off the thread read is a
plain `ChatError`, and a Slack 429 keeps `Retry-After` in its detail but not in `stable`,
the text the read pass stores, so a new wait is no new write."""

from __future__ import annotations

import httpx
import pytest

from orchestrator.domain.ports.chat import ChatError, ChatRateLimited, ThreadRef
from orchestrator.infrastructure.chat.mattermost import MattermostChannel
from orchestrator.infrastructure.chat.slack import SlackChannel

AUTH = {"ok": True, "user_id": "UBOT", "user": "orchestrator", "bot_id": "B1"}


def test_mattermost_a_404_outside_the_thread_read_is_exactly_a_chat_error() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "no such user"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    channel = MattermostChannel("https://chat.example.test", "ch1", "mm-token", client=client)

    with pytest.raises(ChatError) as caught:
        channel.replies_since(ThreadRef(id="root"), None)

    assert type(caught.value) is ChatError


@pytest.mark.parametrize("headers", [{"Retry-After": "30"}, {"Retry-After": "12"}, {}])
def test_slack_a_429s_stable_text_leaves_the_wait_out(headers: dict[str, str]) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth.test"):
            return httpx.Response(200, json=AUTH)
        return httpx.Response(429, headers=headers)

    client = httpx.Client(transport=httpx.MockTransport(respond))
    channel = SlackChannel("https://slack.example.test/api", "C0CHAN", "xoxb-t", client=client)

    with pytest.raises(ChatRateLimited) as caught:
        channel.replies_since(ThreadRef(id="1700000000.000000"), None)

    assert caught.value.stable == "conversations.replies: 429 rate limited"
    assert caught.value.detail.startswith("conversations.replies: 429 rate limited, ")


def test_a_rate_limit_without_a_stable_text_is_stable_as_its_detail() -> None:
    assert ChatRateLimited("429 slow down").stable == "429 slow down"
