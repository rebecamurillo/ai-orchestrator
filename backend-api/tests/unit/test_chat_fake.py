"""The chat port's value types, `ChatError`, and the shared fake's fit to the port (story 3-1)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from orchestrator.domain.ports.chat import (
    ChatChannel,
    ChatChannelFactory,
    ChatError,
    ChatUser,
    Reply,
    ThreadRef,
)
from tests.unit.fakes.chat import BOT_HANDLE, FakeChatChannel, FakeChatChannelFactory

THREAD = ThreadRef(id="root")


def a_reply(n: int, *, mentions_bot: bool = True) -> Reply:
    return Reply(
        id=f"r{n}",
        author_id="u1",
        mentions_bot=mentions_bot,
        text=f"@bot answer {n}",
        body=f" answer {n}",
        cursor=f"c{n}",
    )


def test_the_value_types_are_frozen_and_carry_their_fields() -> None:
    user = ChatUser(id="u1", handle="ana")
    reply = a_reply(1)

    assert (user.id, user.handle) == ("u1", "ana")
    assert (THREAD.id, reply.body, reply.cursor) == ("root", " answer 1", "c1")
    with pytest.raises(FrozenInstanceError):
        reply.text = "changed"  # type: ignore[misc]


def test_a_chat_error_carries_its_detail_as_its_message() -> None:
    error = ChatError("401 Invalid or expired session")

    assert error.detail == "401 Invalid or expired session"
    assert str(error) == error.detail


def test_the_fakes_satisfy_the_ports() -> None:
    assert isinstance(FakeChatChannel(), ChatChannel)
    assert isinstance(FakeChatChannelFactory(), ChatChannelFactory)


def test_post_and_reply_are_recorded_and_each_post_is_a_new_thread() -> None:
    channel = FakeChatChannel()
    ana = ChatUser(id="u1", handle="ana")

    first = channel.post("Run needs you", [ana])
    second = channel.post("another", [])
    channel.reply(first, "noted")

    assert first != second
    assert channel.posts == [("Run needs you", (ana,)), ("another", ())]
    assert channel.replies == [(first, "noted")]
    assert channel.replies_since(first, None) == []


def test_replies_since_honours_the_cursor_and_sees_later_arrivals() -> None:
    channel = FakeChatChannel()
    channel.script_replies(THREAD, a_reply(1), a_reply(2))

    assert channel.replies_since(THREAD, None) == [a_reply(1), a_reply(2)]
    assert channel.replies_since(THREAD, "c1") == [a_reply(2)]
    assert channel.replies_since(THREAD, "c2") == []

    channel.script_replies(THREAD, a_reply(3))

    assert channel.replies_since(THREAD, "c2") == [a_reply(3)]
    assert channel.reads == [(THREAD, None), (THREAD, "c1"), (THREAD, "c2"), (THREAD, "c2")]


def test_an_unknown_cursor_is_refused() -> None:
    channel = FakeChatChannel()
    channel.script_replies(THREAD, a_reply(1))

    with pytest.raises(ChatError, match="unknown cursor"):
        channel.replies_since(THREAD, "elsewhere")


def test_an_unscripted_thread_has_no_replies() -> None:
    assert FakeChatChannel().replies_since(ThreadRef(id="nowhere"), None) == []


def test_probe_answers_the_scripted_handle() -> None:
    assert FakeChatChannel().probe() == BOT_HANDLE
    channel = FakeChatChannel(probe_handle="orchestrator")

    assert channel.probe() == "orchestrator"
    assert channel.probes == 1


@pytest.mark.parametrize("call", ["post", "reply", "replies_since", "probe"])
def test_a_scripted_error_fails_the_next_call_only(call: str) -> None:
    channel = FakeChatChannel()
    channel.fail_next(ChatError("503 down"))
    calls = {
        "post": lambda: channel.post("text", []),
        "reply": lambda: channel.reply(THREAD, "text"),
        "replies_since": lambda: channel.replies_since(THREAD, None),
        "probe": channel.probe,
    }

    with pytest.raises(ChatError, match="503 down"):
        calls[call]()

    assert (channel.posts, channel.replies, channel.reads, channel.probes) == ([], [], [], 0)
    calls[call]()


def test_the_factory_records_each_open_and_returns_its_channel() -> None:
    factory = FakeChatChannelFactory()

    channel = factory.open("mattermost", "https://chat.example.test", "ch1", "tok")

    assert channel is factory.channel
    assert factory.opened == [("mattermost", "https://chat.example.test", "ch1", "tok")]


def test_the_factory_can_be_given_a_channel_and_told_to_refuse() -> None:
    channel = FakeChatChannel()
    factory = FakeChatChannelFactory(channel)
    factory.error = ChatError("slack is not available yet")

    with pytest.raises(ChatError, match="not available"):
        factory.open("slack", "https://slack.com", "C1", "tok")

    assert factory.channel is channel
    assert factory.opened == []
