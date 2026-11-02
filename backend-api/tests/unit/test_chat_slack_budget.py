"""A `<`- and `&`-heavy stop posts on Slack (story 3-3 lead review of the build, 2026-11-02).

The post pass budgets against the adapter's `rendered_length`, so a question at its cap that
escapes to four or five times its length is cut until Slack's rendering fits, and the post
succeeds rather than being refused past 4,000 and failed for good. The pass runs over the
shared `World`, with a real `SlackChannel` on an `httpx.MockTransport`.
"""

from __future__ import annotations

import json

import httpx

from orchestrator.application.rules.chat_message import CUT_MARKER, MAX_POST_CHARS, QUESTION_CAP
from orchestrator.domain.ports.chat import ChatChannel, ChatProvider, ChatUser
from orchestrator.infrastructure.chat.slack import SlackChannel
from tests.unit.fakes.chat_world import BASE_URL, World

SLACK = "https://slack.example.test/api"


class SlackFactory:
    """Opens a real `SlackChannel` whose every `chat.postMessage` is recorded and accepted."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def open(
        self, provider: ChatProvider, base_url: str, channel_id: str, token: str
    ) -> ChatChannel:
        def respond(request: httpx.Request) -> httpx.Response:
            self.sent.append(json.loads(request.content)["text"])
            return httpx.Response(200, json={"ok": True, "ts": "1700000001.000000"})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        return SlackChannel(base_url, channel_id, token, client=client)


def test_an_escape_heavy_question_at_its_cap_posts_within_slacks_rendering() -> None:
    world = World()
    factory = SlackFactory()
    world.factory = factory  # type: ignore[assignment]
    world.add_channel(
        provider="slack",
        base_url=SLACK,
        channel_id="C1",
        allowed_users=(ChatUser(id="U1", handle="ana"),),
    )
    run = world.add_run(park_reason="<&" * (QUESTION_CAP // 2))

    world.poll()

    thread = world.only_thread()
    assert (thread.state, thread.error) == ("open", None)
    (text,) = factory.sent
    assert len(text) <= MAX_POST_CHARS
    assert text.startswith("<@U1>\n")
    assert CUT_MARKER in text
    assert text.endswith(f"\nRun: {BASE_URL}/workflows/{run.id}")
