"""`open_channel` and `ChatChannels`: one decision point from a provider to an adapter (3-1)."""

from __future__ import annotations

import pytest

from orchestrator.domain.ports.chat import ChatChannelFactory, ChatError
from orchestrator.infrastructure.chat import ChatChannels, open_channel
from orchestrator.infrastructure.chat.mattermost import MattermostChannel
from orchestrator.infrastructure.chat.slack import SlackChannel


def test_mattermost_opens_the_mattermost_adapter() -> None:
    channel = open_channel("mattermost", "https://chat.example.test/", "ch1", "tok")

    assert isinstance(channel, MattermostChannel)


def test_slack_opens_the_slack_adapter() -> None:
    # Revised under hard rule 1(b) by story 3-2, 2026-11-02: `slack` was refused with
    # "slack is not available yet" until its adapter landed; it now opens `SlackChannel`.
    channel = open_channel("slack", "https://slack.com/api/", "C1", "tok")

    assert isinstance(channel, SlackChannel)
    assert not isinstance(channel, MattermostChannel)
    assert channel._base == "https://slack.com/api"
    assert channel._channel_id == "C1"


def test_an_unknown_provider_is_refused_by_name() -> None:
    with pytest.raises(ChatError) as caught:
        open_channel("irc", "https://irc.example.test", "#ops", "tok")  # type: ignore[arg-type]

    assert caught.value.detail == "unknown chat provider 'irc'"


def test_the_factory_object_satisfies_the_port_and_opens_through_open_channel() -> None:
    factory = ChatChannels()

    assert isinstance(factory, ChatChannelFactory)
    assert isinstance(factory.open("mattermost", "https://c.test", "ch1", "tok"), MattermostChannel)
