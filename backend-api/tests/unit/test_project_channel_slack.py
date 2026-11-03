"""A Project's channel on `slack`: schema, use case, factory and route (story 3-2).

The settings are 3-4's, unchanged but for the provider. `base_url` is required for Slack as for
Mattermost (the form pre-fills `https://slack.com/api`), so 3-4's host-change rule holds as is.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.project_channel import ChannelIn
from orchestrator.application.use_cases import project_channel as use_cases
from orchestrator.domain.errors import Invalid
from orchestrator.domain.ports.chat import ChatUser
from orchestrator.infrastructure.chat import ChatChannels, open_channel
from orchestrator.infrastructure.chat.slack import SlackChannel
from tests.unit.application.test_project_channel import World, a_draft, a_token
from tests.unit.test_project_channel_router import HTTP_OK, Harness

SLACK_API = "https://slack.com/api"
SLACK_CHANNEL = "C0123ABC"


def a_slack_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "provider": "slack",
        "base_url": SLACK_API,
        "channel_id": SLACK_CHANNEL,
        "token": "xoxb-1-2-abc",
        "allowed_users": [{"id": "U01ANA", "handle": "ana"}],
    }
    body.update(overrides)
    return body


def refused_at(body: dict[str, Any]) -> dict[tuple[object, ...], str]:
    with pytest.raises(ValidationError) as caught:
        ChannelIn.model_validate(body)
    return {tuple(error["loc"]): str(error["msg"]) for error in caught.value.errors()}


# ── schema ───────────────────────────────────────────────────────────────────


def test_a_full_slack_body_becomes_a_slack_draft() -> None:
    draft = ChannelIn.model_validate(a_slack_body()).as_draft()

    assert (draft.provider, draft.base_url, draft.channel_id) == (
        "slack",
        SLACK_API,
        SLACK_CHANNEL,
    )
    assert draft.allowed_users == (ChatUser(id="U01ANA", handle="ana"),)


@pytest.mark.parametrize("field", ["base_url", "channel_id"])
def test_a_slack_body_needs_its_base_url_and_channel(field: str) -> None:
    body = a_slack_body()
    del body[field]

    assert refused_at(body)[(field,)].endswith("required for a slack channel")


def test_a_slack_body_needs_an_allowed_user() -> None:
    assert ("allowed_users",) in refused_at(a_slack_body(allowed_users=[]))


def test_an_unknown_provider_is_still_refused_at_the_provider() -> None:
    assert ("provider",) in refused_at(a_slack_body(provider="teams"))


# ── use case, on the shared fakes ────────────────────────────────────────────


def test_a_slack_channel_is_stored_and_tested_through_the_factory() -> None:
    world, token = World(), a_token()
    draft = a_draft(token, provider="slack", base_url=SLACK_API, channel_id=SLACK_CHANNEL)

    view = use_cases.put_channel(world.ports, world.project.id, draft)
    result = use_cases.test_channel(world.ports, world.project.id)

    assert (view.provider, view.base_url, view.token_set) == ("slack", SLACK_API, True)
    assert world.factory.opened == [("slack", SLACK_API, SLACK_CHANNEL, token)]
    assert (result.ok, result.detail) == (True, "connected as @orchestrator-bot")


def test_a_kept_slack_token_follows_neither_a_host_nor_a_provider_change() -> None:
    world, token = World(), a_token()
    fields = {"provider": "slack", "base_url": SLACK_API, "channel_id": SLACK_CHANNEL}
    stored = world.store(token, **fields)

    kept = use_cases.put_channel(world.ports, world.project.id, a_draft(None, **fields))
    gov = {**fields, "base_url": "https://slack-gov.com/api"}
    with pytest.raises(Invalid, match=r"^token: enter the token again when the host changes$"):
        use_cases.put_channel(world.ports, world.project.id, a_draft(None, **gov))
    with pytest.raises(Invalid, match=r"^token: the stored token belongs to another provider$"):
        use_cases.put_channel(world.ports, world.project.id, a_draft(None))

    assert kept.token_set is True
    current = world.channels.get(world.project.id)
    assert current is not None
    assert current.token_enc == stored.token_enc


# ── factory ──────────────────────────────────────────────────────────────────


def test_slack_opens_the_slack_adapter_on_the_shared_client() -> None:
    factory = ChatChannels(transport=httpx.MockTransport(lambda _: httpx.Response(200)))

    channel = factory.open("slack", SLACK_API, SLACK_CHANNEL, "xoxb-1")

    assert isinstance(channel, SlackChannel)
    assert channel._client is factory._client
    assert channel._base == SLACK_API


def test_open_channel_hands_its_client_to_the_slack_adapter() -> None:
    client = httpx.Client()

    channel = open_channel("slack", SLACK_API + "/", SLACK_CHANNEL, "xoxb-1", client=client)

    assert isinstance(channel, SlackChannel)
    assert channel._client is client


def test_the_factory_sends_each_slack_bot_its_own_token() -> None:
    seen: list[tuple[str, str]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers["Authorization"]))
        if request.url.path.endswith("/auth.test"):
            # Story 3-2 review, 2026-11-02 (hard rule 1(b)): `auth.test` must name a `bot_id`.
            auth = {"ok": True, "user_id": "UB", "user": "bot", "bot_id": "B1"}
            return httpx.Response(200, json=auth)
        return httpx.Response(200, json={"ok": True, "channel": {"is_member": True}})

    factory = ChatChannels(transport=httpx.MockTransport(respond))
    for token in ("xoxb-a", "xoxb-b"):
        factory.open("slack", SLACK_API, SLACK_CHANNEL, token).probe()

    assert seen == [
        ("/api/auth.test", "Bearer xoxb-a"),
        ("/api/conversations.info", "Bearer xoxb-a"),
        ("/api/auth.test", "Bearer xoxb-b"),
        ("/api/conversations.info", "Bearer xoxb-b"),
    ]


# ── route ────────────────────────────────────────────────────────────────────


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


async def test_a_slack_channel_is_saved_read_and_tested_over_http(api: Harness) -> None:
    body = a_slack_body()

    async with api.client() as client:
        saved = await client.put(api.url(), json=body)
        read = await client.get(api.url())
        tested = await client.post(api.url(suffix="/test"))

    assert saved.status_code == read.status_code == tested.status_code == HTTP_OK
    assert read.json()["provider"] == "slack"
    assert read.json()["base_url"] == SLACK_API
    assert body["token"] not in saved.text + read.text + tested.text
    assert tested.json() == {"ok": True, "detail": "connected as @ops-bot"}
    assert api.factory.opened[0][0] == "slack"


async def test_the_contract_offers_slack(api: Harness) -> None:
    async with api.client() as client:
        schemas = (await client.get("/openapi.json")).json()["components"]["schemas"]

    assert "slack" in repr(schemas["ChannelIn"]["properties"]["provider"])
    assert "slack" in repr(schemas["ChannelOut"]["properties"]["provider"])
