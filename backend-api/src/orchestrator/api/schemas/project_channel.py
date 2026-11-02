"""The HTTP shape of a Project's chat channel (story 3-4).

`token` is a `SecretStr` and leaves only as `token_set`. No validator message names a value,
so a refused token is never echoed in a problem body. Every shape rule fails at the field it
names, which is where the form puts its message. Every provider but `off` needs a base URL,
a channel and an allowed user; Slack's base URL is its Web API root (story 3-2).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, Field, SecretStr, ValidationInfo, field_validator

from orchestrator.api.schemas.common import StorableText
from orchestrator.application.use_cases.project_channel import ChannelDraft, ChannelTest
from orchestrator.domain.entities.project_channel import (
    ProjectChannelView,
    is_valid_base_url,
    is_valid_channel_id,
    is_valid_handle,
    is_valid_user_id,
)
from orchestrator.domain.ports.chat import ChatUser

ProviderIn = Literal["off", "mattermost", "slack"]
NEEDS_FIELDS: tuple[ProviderIn, ...] = ("mattermost", "slack")

BASE_URL_REASON = "a base URL is http(s)://host, with no whitespace"
CHANNEL_ID_REASON = "a channel id is non-empty, with no whitespace"
USER_ID_REASON = "a user id is non-empty, with no whitespace"
HANDLE_REASON = "a handle is non-empty, without @ and without whitespace"
TOKEN_REASON = "a token is printable ASCII with no whitespace"
NO_USER_REASON = "a channel needs at least one allowed user"
DUPLICATE_USER_REASON = "duplicate user id"
REQUIRED_REASON = "required for a {provider} channel"

_PRINTABLE_ASCII = range(0x21, 0x7F)


def _checked(rule: Callable[[str], bool], reason: str) -> AfterValidator:
    def check(value: str) -> str:
        if not rule(value):
            raise ValueError(reason)
        return value

    return AfterValidator(check)


def _valid_token(token: SecretStr) -> SecretStr:
    value = token.get_secret_value()
    if not value or any(ord(character) not in _PRINTABLE_ASCII for character in value):
        raise ValueError(TOKEN_REASON)
    return token


BaseUrl = Annotated[StorableText, _checked(is_valid_base_url, BASE_URL_REASON)]
ChannelId = Annotated[StorableText, _checked(is_valid_channel_id, CHANNEL_ID_REASON)]
UserId = Annotated[StorableText, _checked(is_valid_user_id, USER_ID_REASON)]
Handle = Annotated[StorableText, _checked(is_valid_handle, HANDLE_REASON)]
Token = Annotated[SecretStr, AfterValidator(_valid_token)]


class ChatUserIn(BaseModel):
    """A person allowed to answer: the platform's user id and the handle people type."""

    id: UserId
    handle: Handle


class ChatUserOut(BaseModel):
    id: str
    handle: str


class ChannelIn(BaseModel):
    """`PUT` body. Without `token`, the stored one is kept for the same provider; `off`
    needs no other field and deletes the channel."""

    provider: ProviderIn
    base_url: BaseUrl | None = Field(default=None, validate_default=True)
    channel_id: ChannelId | None = Field(default=None, validate_default=True)
    token: Token | None = None
    allowed_users: list[ChatUserIn] = Field(default_factory=list, validate_default=True)
    metadata_only: bool = False

    @field_validator("base_url", "channel_id")
    @classmethod
    def _present(cls, value: str | None, info: ValidationInfo) -> str | None:
        provider = info.data.get("provider")
        if value is None and provider in NEEDS_FIELDS:
            raise ValueError(REQUIRED_REASON.format(provider=provider))
        return value

    @field_validator("allowed_users")
    @classmethod
    def _users(cls, users: list[ChatUserIn], info: ValidationInfo) -> list[ChatUserIn]:
        if not users and info.data.get("provider") in NEEDS_FIELDS:
            raise ValueError(NO_USER_REASON)
        seen: set[str] = set()
        for user in users:
            if user.id in seen:
                raise ValueError(f"{DUPLICATE_USER_REASON}: {user.id}")
            seen.add(user.id)
        return users

    def as_draft(self) -> ChannelDraft:
        return ChannelDraft(
            provider=self.provider,
            base_url=self.base_url,
            channel_id=self.channel_id,
            token=None if self.token is None else self.token.get_secret_value(),
            allowed_users=tuple(
                ChatUser(id=user.id, handle=user.handle) for user in self.allowed_users
            ),
            metadata_only=self.metadata_only,
        )


class ChannelOut(BaseModel):
    """The channel as it leaves this API. The token is never returned, only `token_set`."""

    provider: ProviderIn
    base_url: str | None
    channel_id: str | None
    token_set: bool
    allowed_users: list[ChatUserOut]
    metadata_only: bool

    @classmethod
    def of(cls, view: ProjectChannelView) -> Self:
        return cls.model_validate(
            {
                "provider": view.provider,
                "base_url": view.base_url,
                "channel_id": view.channel_id,
                "token_set": view.token_set,
                "allowed_users": [
                    {"id": user.id, "handle": user.handle} for user in view.allowed_users
                ],
                "metadata_only": view.metadata_only,
            }
        )


class ChannelTestOut(BaseModel):
    """One probe of the saved channel: `ok`, and the platform's own words when it is not."""

    ok: bool
    detail: str

    @classmethod
    def of(cls, result: ChannelTest) -> Self:
        return cls(ok=result.ok, detail=result.detail)
