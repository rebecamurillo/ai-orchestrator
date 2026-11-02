"""`open_channel` and `ChatChannels`: one decision point from a provider to an adapter (3-1)."""

from __future__ import annotations

import pytest

from orchestrator.domain.ports.chat import ChatChannelFactory, ChatError
from orchestrator.infrastructure.chat import ChatChannels, open_channel
from orchestrator.infrastructure.chat.mattermost import MattermostChannel


def test_mattermost_opens_the_mattermost_adapter() -> None:
    channel = open_channel("mattermost", "https://chat.example.test/", "ch1", "tok")

    assert isinstance(channel, MattermostChannel)


def test_slack_is_refused_until_its_adapter_lands() -> None:
    with pytest.raises(ChatError) as caught:
        open_channel("slack", "https://slack.com", "C1", "tok")

    assert caught.value.detail == "slack is not available yet"


def test_an_unknown_provider_is_refused_by_name() -> None:
    with pytest.raises(ChatError) as caught:
        open_channel("irc", "https://irc.example.test", "#ops", "tok")  # type: ignore[arg-type]

    assert caught.value.detail == "unknown chat provider 'irc'"


def test_the_factory_object_satisfies_the_port_and_opens_through_open_channel() -> None:
    factory = ChatChannels()

    assert isinstance(factory, ChatChannelFactory)
    assert isinstance(factory.open("mattermost", "https://c.test", "ch1", "tok"), MattermostChannel)
