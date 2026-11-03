"""`MattermostChannel` neutralises mentions and links in the text it sends (story 3-3, D1, D2).

`props.disable_group_highlight` does not suppress notifications, so the adapter breaks every
`@` that could open a mention with U+2060 and backslash-escapes `[` and `]`. The adapter's own
mention prefix is built apart, and a handle naming a group is refused. Replies name mentions
as posts do.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from orchestrator.domain.ports.chat import ChatError, ChatUser, ThreadRef
from orchestrator.infrastructure.chat.mattermost import MattermostChannel, neutralise

BASE = "https://chat.example.test"
TOKEN = "mm-token-31c9"
CHANNEL = "ch1"
JOINER = "\u2060"
ALICE = ChatUser(id="u1", handle="alice")


def a_channel() -> tuple[MattermostChannel, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"id": f"post-{len(seen)}"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return MattermostChannel(BASE, CHANNEL, TOKEN, client=client), seen


def sent(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)  # type: ignore[no-any-return]


# Revised: story 3-3 lead review of the build, 2026-11-02 — every `@` now gets U+2060, so an
# address is broken too (`ops@example.com` was left whole), and `\`, `&` are escaped.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("@channel", f"@{JOINER}channel"),
        ("ping @here and @all", f"ping @{JOINER}here and @{JOINER}all"),
        ("(@alice)", f"(@{JOINER}alice)"),
        ("mail ops@example.com", f"mail ops@{JOINER}example.com"),
        ("[click](https://evil.example)", "\\[click\\](https://evil.example)"),
        ("plain", "plain"),
    ],
)
def test_neutralise_breaks_mentions_and_escapes_link_brackets(text: str, expected: str) -> None:
    assert neutralise(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\\[x\\](https://evil.example)", "\\\\\\[x\\\\\\](https://evil.example)"),
        ("_@all_", f"_@{JOINER}all_"),
        ("*@here*", f"*@{JOINER}here*"),
        ("`@all`", f"`@{JOINER}all`"),
        ("&#64;channel", "\\&#64;channel"),
        ("&commat;here", "\\&commat;here"),
    ],
    ids=["escaped-link", "underscore", "emphasis", "code-span", "decimal-entity", "named-entity"],
)
def test_the_review_bypasses_are_closed(text: str, expected: str) -> None:
    """An escaped bracket, a word-character `@` and an entity each reopened a link or a
    mention under the first rule (story 3-3 lead review of the build, 2026-11-02)."""
    assert neutralise(text) == expected


def test_rendered_length_is_the_message_as_sent_with_its_prefix_and_suffix() -> None:
    channel, seen = a_channel()
    text, suffix = "@here & [x]", "\nRun: https://orch.example.com/workflows/r"

    length = channel.rendered_length(text, [ALICE], suffix)
    channel.post(text, [ALICE], suffix)

    assert length == len(sent(seen[0])["message"])
    assert channel.rendered_length("plain") == len("plain")


def test_the_trusted_suffix_is_sent_as_written_so_an_ipv6_link_stays_usable() -> None:
    """Escaping `[` would put a backslash inside the autolinked URL; the suffix is the
    system's own line, so it is left alone (story 3-3 review, item 4)."""
    channel, seen = a_channel()
    link = "\nRun: http://[fd00::1]:4321/workflows/r1"

    channel.post("Question: [x]", [], link)
    channel.reply(ThreadRef(id="root"), "Still waiting", [], link)

    for request in seen:
        assert sent(request)["message"].endswith("http://[fd00::1]:4321/workflows/r1")
    assert sent(seen[0])["message"] == f"Question: \\[x\\]{link}"


def test_a_post_neutralises_its_text_and_keeps_its_own_mentions() -> None:
    channel, seen = a_channel()

    channel.post("@channel see [x](y)", [ALICE])

    assert sent(seen[0])["message"] == f"@alice\n@{JOINER}channel see \\[x\\](y)"


@pytest.mark.parametrize("handle", ["channel", "here", "all"])
def test_a_mention_naming_a_group_is_refused_and_nothing_is_sent(handle: str) -> None:
    channel, seen = a_channel()

    with pytest.raises(ChatError):
        channel.post("text", [ChatUser(id="u9", handle=handle)])
    with pytest.raises(ChatError):
        channel.reply(ThreadRef(id="root"), "text", [ChatUser(id="u9", handle=handle)])

    assert seen == []


def test_a_reply_names_its_mentions_and_neutralises_its_text() -> None:
    channel, seen = a_channel()

    channel.reply(ThreadRef(id="root"), "Still waiting @here", [ALICE, ChatUser("u2", "bob")])

    assert sent(seen[0]) == {
        "channel_id": CHANNEL,
        "message": f"@alice @bob\nStill waiting @{JOINER}here",
        "root_id": "root",
    }


def test_a_reply_without_mentions_sends_the_text_alone() -> None:
    channel, seen = a_channel()

    channel.reply(ThreadRef(id="root"), "noted")

    assert sent(seen[0])["message"] == "noted"


def test_a_reply_mention_that_is_not_a_username_is_refused() -> None:
    channel, seen = a_channel()

    with pytest.raises(ChatError):
        channel.reply(ThreadRef(id="root"), "x", [ChatUser(id="u1", handle="Al ice")])

    assert seen == []
