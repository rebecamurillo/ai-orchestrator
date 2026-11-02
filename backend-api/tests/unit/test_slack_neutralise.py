"""`SlackChannel` sends group mentions and links as plain text, names reply mentions, and
refuses a message Slack would split (story 3-3, D2, M6).

`&`, `<` and `>` are escaped, so `<!channel>`, `<!here>`, `<!everyone>`, `<!subteam^S1>` and
`<https://x|y>` arrive as text; neither `link_names` nor `parse` is sent. Past 4,000
characters after escaping, `chat.postMessage` may split `text` into several messages, which
would break the thread, so the adapter refuses instead.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from orchestrator.domain.ports.chat import ChatError, ChatUser, ThreadRef
from orchestrator.infrastructure.chat.slack import MAX_TEXT_CHARS, SlackChannel

BASE = "https://slack.example.test/api"
TOKEN = "xoxb-test-6f1c2e"
CHANNEL = "C0CHAN"
ROOT = ThreadRef(id="1700000000.000000")
ALICE = ChatUser(id="U1", handle="alice")


def a_channel() -> tuple[SlackChannel, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "ts": "1700000001.000000"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return SlackChannel(BASE, CHANNEL, TOKEN, client=client), seen


def sent(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("<!channel>", "&lt;!channel&gt;"),
        ("<!here>", "&lt;!here&gt;"),
        ("<!everyone>", "&lt;!everyone&gt;"),
        ("<!subteam^S1>", "&lt;!subteam^S1&gt;"),
        ("<https://x|y>", "&lt;https://x|y&gt;"),
    ],
)
@pytest.mark.parametrize("call", ["post", "reply"])
def test_group_mentions_and_links_arrive_escaped(call: str, text: str, escaped: str) -> None:
    channel, seen = a_channel()

    if call == "post":
        channel.post(text, [])
    else:
        channel.reply(ROOT, text)

    body = sent(seen[0])
    assert body["text"] == escaped
    assert "link_names" not in body
    assert "parse" not in body


def test_a_reply_names_its_mentions_on_the_first_line() -> None:
    channel, seen = a_channel()

    channel.reply(ROOT, "Still waiting", [ALICE, ChatUser(id="U2", handle="bob")])

    body = sent(seen[0])
    assert body["text"] == "<@U1> <@U2>\nStill waiting"
    assert body["thread_ts"] == ROOT.id


def test_a_reply_mention_that_is_not_a_user_id_is_refused() -> None:
    channel, seen = a_channel()

    with pytest.raises(ChatError):
        channel.reply(ROOT, "x", [ChatUser(id="U1><!channel", handle="x")])

    assert seen == []


def test_text_at_the_limit_after_escaping_is_sent() -> None:
    channel, seen = a_channel()

    channel.post("a" * (MAX_TEXT_CHARS - len("<@U1>\n")), [ALICE])

    assert len(sent(seen[0])["text"]) == MAX_TEXT_CHARS


@pytest.mark.parametrize("call", ["post", "reply"])
def test_text_past_the_limit_after_escaping_is_refused_and_not_sent(call: str) -> None:
    channel, seen = a_channel()
    text = "<" * 1000  # 1,000 characters, 4,000 once escaped
    expected = len("<@U1>\n") + 4000

    with pytest.raises(ChatError) as caught:
        if call == "post":
            channel.post(text, [ALICE])
        else:
            channel.reply(ROOT, text, [ALICE])

    assert caught.value.detail == f"text too long after escaping: {expected}"
    assert seen == []
