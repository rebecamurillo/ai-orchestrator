"""Reading, saving and testing a Project's chat channel (AD-25, CAP-10).

The bot token is encrypted through `Crypto` on the way in and decrypted only by
`test_channel`, to open the channel. Nothing this module returns carries it. A `PUT`
without a token keeps the stored ciphertext only for the same provider, because a token
from another platform is never reused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from orchestrator.application.use_cases.projects import _refuse_builtin, _require
from orchestrator.domain.entities.project_channel import (
    CHANNEL_OFF,
    ChannelSetting,
    ProjectChannel,
    ProjectChannelView,
)
from orchestrator.domain.errors import Conflict, Invalid
from orchestrator.domain.ports.chat import ChatChannelFactory, ChatError, ChatProvider, ChatUser
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.crypto import Crypto
from orchestrator.domain.ports.repositories import ProjectChannelRepository, ProjectRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork

NO_CHANNEL_REASON = "no channel is set"
NO_STORED_TOKEN_REASON = "token: no stored token to keep"
OTHER_PROVIDER_TOKEN_REASON = "token: the stored token belongs to another provider"
NO_ALLOWED_USER_REASON = "allowed_users: at least one allowed user is needed"
REDACTED = "***"


@dataclass(frozen=True)
class ChannelPorts:
    """The unit of work is already open; leaving it without a `commit()` discards the work."""

    uow: UnitOfWork
    projects: ProjectRepository
    channels: ProjectChannelRepository
    crypto: Crypto
    clock: Clock
    factory: ChatChannelFactory


@dataclass(frozen=True)
class ChannelDraft:
    """What the Operator asked for. `token is None` means "keep the stored one"."""

    provider: ChannelSetting
    base_url: str | None = None
    channel_id: str | None = None
    token: str | None = field(default=None, repr=False)
    allowed_users: tuple[ChatUser, ...] = ()
    metadata_only: bool = False


@dataclass(frozen=True)
class ChannelTest:
    ok: bool
    detail: str


def get_channel(ports: ChannelPorts, project_id: UUID) -> ProjectChannelView:
    _require(ports.projects, project_id)
    stored = ports.channels.get(project_id)
    return ProjectChannelView.off() if stored is None else stored.view()


def put_channel(ports: ChannelPorts, project_id: UUID, draft: ChannelDraft) -> ProjectChannelView:
    """Store, replace or (for `off`) delete the channel. Nothing is written on a refusal."""
    _refuse_builtin(_require(ports.projects, project_id))
    if draft.provider == CHANNEL_OFF:
        ports.channels.delete(project_id)
        ports.uow.commit()
        return ProjectChannelView.off()
    provider: ChatProvider = draft.provider
    base_url = _required(draft.base_url, "base_url", provider)
    channel_id = _required(draft.channel_id, "channel_id", provider)
    if not draft.allowed_users:
        raise Invalid(NO_ALLOWED_USER_REASON)
    stored = ports.channels.get(project_id)
    now = ports.clock.now()
    channel = ProjectChannel(
        project_id=project_id,
        provider=provider,
        base_url=base_url,
        channel_id=channel_id,
        token_enc=_token_enc(stored, provider, draft.token, ports.crypto),
        allowed_users=draft.allowed_users,
        metadata_only=draft.metadata_only,
        created_at=now if stored is None else stored.created_at,
        updated_at=now,
    )
    ports.channels.put(channel)
    ports.uow.commit()
    return channel.view()


def test_channel(ports: ChannelPorts, project_id: UUID) -> ChannelTest:
    """Probe the saved channel once, with no retry (hard rule 7). A refusal is an answer."""
    _require(ports.projects, project_id)
    stored = ports.channels.get(project_id)
    if stored is None:
        raise Conflict(NO_CHANNEL_REASON)
    token = ports.crypto.decrypt(stored.token_enc)
    try:
        channel = ports.factory.open(stored.provider, stored.base_url, stored.channel_id, token)
        handle = channel.probe()
    except ChatError as error:
        # the adapter already redacts; this guards a factory that does not
        return ChannelTest(ok=False, detail=error.detail.replace(token, REDACTED))
    return ChannelTest(ok=True, detail=f"connected as @{handle}")


def _required(value: str | None, name: str, provider: ChatProvider) -> str:
    if value is None:
        raise Invalid(f"{name}: a {provider} channel needs one")
    return value


def _token_enc(
    stored: ProjectChannel | None, provider: ChatProvider, token: str | None, crypto: Crypto
) -> str:
    if token is not None:
        return crypto.encrypt(token)
    if stored is None:
        raise Invalid(NO_STORED_TOKEN_REASON)
    if stored.provider != provider:
        raise Invalid(OTHER_PROVIDER_TOKEN_REASON)
    return stored.token_enc
