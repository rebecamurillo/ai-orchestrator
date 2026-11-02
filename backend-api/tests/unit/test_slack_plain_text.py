"""A Slack reply's `text` and `body` are plain text (story 3-2, lead decision 2026-11-02).

Slack stores `<`, `>` and `&` as `&lt;`, `&gt;` and `&amp;`. The adapter decodes those three,
`&amp;` last, in both `text` and `body`, so `&amp;lt;` comes out as `&lt;`. Other people's
`<@U…>` stay as written, and the bot mention is matched on the raw markup.
"""

from __future__ import annotations

import httpx
import pytest

from orchestrator.domain.ports.chat import ThreadRef
from orchestrator.infrastructure.chat.slack import SlackChannel

BOT = "UBOT"
ROOT = ThreadRef(id="1700000000.000000")
AUTH = {"ok": True, "user_id": BOT, "user": "orchestrator"}


def read_one(text: str) -> tuple[str, str, bool]:
    message = {"type": "message", "ts": "1700000000.000001", "user": "U1", "text": text}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth.test"):
            return httpx.Response(200, json=AUTH)
        return httpx.Response(200, json={"ok": True, "messages": [message]})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    (reply,) = SlackChannel("https://slack.test/api", "C1", "xoxb-1", client=client).replies_since(
        ROOT, None
    )
    return reply.text, reply.body, reply.mentions_bot


@pytest.mark.parametrize(
    ("raw", "text", "body"),
    [
        (
            f"<@{BOT}> use a &lt; b &amp;&amp; c &gt; d",
            f"<@{BOT}> use a < b && c > d",
            " use a < b && c > d",
        ),
        (f"<@{BOT}> literally &amp;lt;", f"<@{BOT}> literally &lt;", " literally &lt;"),
        (f"<@{BOT}> &amp;gt; &amp;amp;", f"<@{BOT}> &gt; &amp;", " &gt; &amp;"),
        (f"<@{BOT}> ask <@U7> &amp; <@U8>", f"<@{BOT}> ask <@U7> & <@U8>", " ask <@U7> & <@U8>"),
        (f"<@{BOT}> &quot;x&quot; &#39;", f"<@{BOT}> &quot;x&quot; &#39;", " &quot;x&quot; &#39;"),
    ],
)
def test_text_and_body_decode_slacks_three_entities_amp_last(
    raw: str, text: str, body: str
) -> None:
    assert read_one(raw) == (text, body, True)


def test_a_decoded_mention_is_not_a_mention() -> None:
    text, body, mentions = read_one(f"&lt;@{BOT}&gt; quoted as text")

    assert mentions is False
    assert text == body == f"<@{BOT}> quoted as text"


def test_a_quote_is_matched_on_the_raw_markup_before_decoding() -> None:
    text, body, mentions = read_one(f"&gt; <@{BOT}> earlier\nthanks")

    assert mentions is False
    assert text == body == f"> <@{BOT}> earlier\nthanks"
