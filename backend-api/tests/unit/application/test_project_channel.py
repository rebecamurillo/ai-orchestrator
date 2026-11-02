"""`application/use_cases/project_channel.py` — every row of story 3-4's matrix, on the fakes.

The bot token is the value under test throughout: encrypted on the way in, decrypted only by
`test_channel`, never part of a returned view, a draft's repr or a `ChatError` detail.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from orchestrator.application.use_cases import project_channel as use_cases
from orchestrator.application.use_cases.project_channel import (
    ChannelDraft,
    ChannelPorts,
)
from orchestrator.domain.entities.project import EncryptedEnvVar, Project
from orchestrator.domain.entities.project_channel import ProjectChannel, ProjectChannelView
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatError, ChatUser
from tests.unit.fakes.chat import FakeChatChannel, FakeChatChannelFactory
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.project_channel import FakeProjectChannelRepository
from tests.unit.fakes.projects import FakeProjectRepository

AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
LATER_SECONDS = 60
BASE_URL = "https://chat.example.com"
CHANNEL_ID = "c0ffee"
ALICE = ChatUser(id="u1", handle="alice")
BOB = ChatUser(id="u2", handle="bob")


def a_token() -> str:
    return f"tok-{uuid4()}"


def a_project(**overrides: object) -> Project:
    fields: dict[str, object] = {
        "id": new_id(),
        "slug": "acme",
        "name": "Acme",
        "context_text": "",
        "context_paths": (),
        "env_vars_enc": (EncryptedEnvVar(name="MY_VAR", value_enc="fake-enc:0:dg=="),),
        "log_prompt_content": False,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Project(**fields)  # type: ignore[arg-type]


class World:
    """One Project, the fakes, and an open unit of work."""

    def __init__(self, project: Project | None = None) -> None:
        self.project = project or a_project()
        self.projects = FakeProjectRepository([self.project])
        self.channels = FakeProjectChannelRepository()
        self.crypto = FakeCrypto()
        self.clock = FakeClock(AT)
        self.chat = FakeChatChannel(probe_handle="orchestrator-bot")
        self.factory = FakeChatChannelFactory(self.chat)
        self.uow = FakeUnitOfWork()
        self.uow.__enter__()

    @property
    def ports(self) -> ChannelPorts:
        return ChannelPorts(
            uow=self.uow,
            projects=self.projects,
            channels=self.channels,
            crypto=self.crypto,
            clock=self.clock,
            factory=self.factory,
        )

    def store(self, token: str, **overrides: object) -> ProjectChannel:
        fields: dict[str, object] = {
            "project_id": self.project.id,
            "provider": "mattermost",
            "base_url": BASE_URL,
            "channel_id": CHANNEL_ID,
            "token_enc": self.crypto.encrypt(token),
            "allowed_users": (ALICE,),
            "metadata_only": False,
            "created_at": AT,
            "updated_at": AT,
        }
        fields.update(overrides)
        channel = ProjectChannel(**fields)  # type: ignore[arg-type]
        self.channels.put(channel)
        return channel


def a_draft(token: str | None, **overrides: object) -> ChannelDraft:
    fields: dict[str, object] = {
        "provider": "mattermost",
        "base_url": BASE_URL,
        "channel_id": CHANNEL_ID,
        "token": token,
        "allowed_users": (ALICE, BOB),
        "metadata_only": True,
    }
    fields.update(overrides)
    return ChannelDraft(**fields)  # type: ignore[arg-type]


@pytest.fixture
def world() -> World:
    return World()


# ── read ─────────────────────────────────────────────────────────────────────


def test_a_project_without_a_row_reads_off(world: World) -> None:
    view = use_cases.get_channel(world.ports, world.project.id)

    assert view == ProjectChannelView(
        provider="off",
        base_url=None,
        channel_id=None,
        token_set=False,
        allowed_users=(),
        metadata_only=False,
    )


def test_a_stored_channel_reads_with_token_set_and_no_token(world: World) -> None:
    token = a_token()
    world.store(token)

    view = use_cases.get_channel(world.ports, world.project.id)

    assert view.provider == "mattermost"
    assert view.token_set is True
    assert view.allowed_users == (ALICE,)
    assert token not in repr(view)
    assert not hasattr(view, "token")
    assert not hasattr(view, "token_enc")
    assert world.crypto.decrypted == []


# ── save ─────────────────────────────────────────────────────────────────────


def test_a_save_stores_the_row_with_the_token_encrypted(world: World) -> None:
    token = a_token()

    view = use_cases.put_channel(world.ports, world.project.id, a_draft(token))

    stored = world.channels.get(world.project.id)
    assert stored is not None
    assert stored.token_enc != token
    assert token not in stored.token_enc
    assert world.crypto.decrypt(stored.token_enc) == token
    assert stored.allowed_users == (ALICE, BOB)
    assert stored.metadata_only is True
    assert (stored.created_at, stored.updated_at) == (AT, AT)
    assert view.token_set is True
    assert token not in repr(view)
    assert world.uow.committed


def test_a_save_over_a_stored_row_keeps_its_creation_time(world: World) -> None:
    world.store(a_token())
    later = world.clock.advance(LATER_SECONDS)

    use_cases.put_channel(world.ports, world.project.id, a_draft(a_token()))

    stored = world.channels.get(world.project.id)
    assert stored is not None
    assert (stored.created_at, stored.updated_at) == (AT, later)


def test_a_save_never_touches_the_projects_env_vars(world: World) -> None:
    before = world.projects.get(world.project.id)

    use_cases.put_channel(world.ports, world.project.id, a_draft(a_token()))

    after = world.projects.get(world.project.id)
    assert after is before
    assert after is not None
    assert after.env_vars_enc == world.project.env_vars_enc


# ── keep ─────────────────────────────────────────────────────────────────────


def test_a_save_without_a_token_keeps_the_stored_ciphertext(world: World) -> None:
    stored = world.store(a_token())
    encrypted_before = list(world.crypto.encrypted)

    view = use_cases.put_channel(
        world.ports, world.project.id, a_draft(None, channel_id="other-channel")
    )

    kept = world.channels.get(world.project.id)
    assert kept is not None
    assert kept.token_enc == stored.token_enc
    assert kept.channel_id == "other-channel"
    assert world.crypto.encrypted == encrypted_before
    assert world.crypto.decrypted == []
    assert view.token_set is True


def test_a_keep_with_no_stored_row_is_invalid_and_writes_nothing(world: World) -> None:
    with pytest.raises(Invalid, match=r"^token: no stored token to keep$"):
        use_cases.put_channel(world.ports, world.project.id, a_draft(None))

    assert world.channels.channels == {}
    assert not world.uow.committed


def test_a_token_from_another_provider_is_never_reused(world: World) -> None:
    stored = world.store(a_token(), provider="slack")

    with pytest.raises(Invalid, match=r"^token: "):
        use_cases.put_channel(world.ports, world.project.id, a_draft(None))

    assert world.channels.get(world.project.id) == stored
    assert not world.uow.committed


def test_a_new_token_may_replace_another_providers_token(world: World) -> None:
    world.store(a_token(), provider="slack")
    token = a_token()

    use_cases.put_channel(world.ports, world.project.id, a_draft(token))

    stored = world.channels.get(world.project.id)
    assert stored is not None
    assert stored.provider == "mattermost"
    assert world.crypto.decrypt(stored.token_enc) == token


# ── off ──────────────────────────────────────────────────────────────────────


def test_turning_off_deletes_the_row(world: World) -> None:
    world.store(a_token())

    view = use_cases.put_channel(world.ports, world.project.id, ChannelDraft(provider="off"))

    assert world.channels.get(world.project.id) is None
    assert view == ProjectChannelView.off()
    assert world.uow.committed


def test_turning_off_twice_is_idempotent(world: World) -> None:
    first = use_cases.put_channel(world.ports, world.project.id, ChannelDraft(provider="off"))
    second = use_cases.put_channel(world.ports, world.project.id, ChannelDraft(provider="off"))

    assert first == second == ProjectChannelView.off()
    assert world.channels.deleted == [world.project.id, world.project.id]


def test_turning_off_ignores_a_token_and_encrypts_nothing(world: World) -> None:
    use_cases.put_channel(
        world.ports, world.project.id, ChannelDraft(provider="off", token=a_token())
    )

    assert world.crypto.encrypted == []


# ── shape the schema cannot see ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"base_url": None}, "base_url"),
        ({"channel_id": None}, "channel_id"),
        ({"allowed_users": ()}, "allowed_users"),
    ],
)
def test_a_channel_missing_a_required_field_is_invalid_naming_it(
    world: World, overrides: dict[str, object], field: str
) -> None:
    with pytest.raises(Invalid, match=rf"^{field}: "):
        use_cases.put_channel(world.ports, world.project.id, a_draft(a_token(), **overrides))

    assert world.channels.channels == {}
    assert world.crypto.encrypted == []
    assert not world.uow.committed


# ── builtin and unknown ──────────────────────────────────────────────────────


@pytest.mark.parametrize("draft", [a_draft("tok-builtin"), ChannelDraft(provider="off")])
def test_a_write_to_the_builtin_project_is_refused(draft: ChannelDraft) -> None:
    world = World(a_project(slug="readiness", name="readiness", builtin=True))

    with pytest.raises(Conflict, match="built in"):
        use_cases.put_channel(world.ports, world.project.id, draft)

    assert world.channels.channels == {}
    assert world.channels.deleted == []
    assert world.crypto.encrypted == []
    assert not world.uow.committed


def test_an_unknown_project_is_not_found_on_every_operation(world: World) -> None:
    unknown = UUID("01a06887-79ab-759b-97a0-71c32ad939c2")

    with pytest.raises(NotFound):
        use_cases.get_channel(world.ports, unknown)
    with pytest.raises(NotFound):
        use_cases.put_channel(world.ports, unknown, a_draft(a_token()))
    with pytest.raises(NotFound):
        use_cases.put_channel(world.ports, unknown, ChannelDraft(provider="off"))
    with pytest.raises(NotFound):
        use_cases.test_channel(world.ports, unknown)

    assert world.channels.channels == {}
    assert world.channels.deleted == []
    assert world.factory.opened == []
    assert not world.uow.committed


# ── the connection test ──────────────────────────────────────────────────────


def test_a_probe_that_answers_reports_the_bots_handle(world: World) -> None:
    token = a_token()
    world.store(token)

    result = use_cases.test_channel(world.ports, world.project.id)

    assert (result.ok, result.detail) == (True, "connected as @orchestrator-bot")
    assert world.factory.opened == [("mattermost", BASE_URL, CHANNEL_ID, token)]
    assert world.chat.probes == 1
    assert not world.uow.committed


def test_a_refused_probe_answers_not_ok_with_the_platforms_text(world: World) -> None:
    world.store(a_token())
    world.chat.fail_next(ChatError("401 Invalid or expired session"))

    result = use_cases.test_channel(world.ports, world.project.id)

    assert (result.ok, result.detail) == (False, "401 Invalid or expired session")
    assert world.chat.probes == 0


def test_a_channel_that_cannot_be_opened_answers_not_ok(world: World) -> None:
    world.store(a_token())
    world.factory.error = ChatError("slack is not available yet")

    result = use_cases.test_channel(world.ports, world.project.id)

    assert (result.ok, result.detail) == (False, "slack is not available yet")


def test_a_detail_that_echoes_the_token_is_redacted(world: World) -> None:
    token = a_token()
    world.store(token)
    world.chat.fail_next(ChatError(f"401 bad token {token}"))

    result = use_cases.test_channel(world.ports, world.project.id)

    assert token not in result.detail
    assert result.detail == "401 bad token ***"


def test_a_test_with_no_channel_is_a_conflict_and_opens_nothing(world: World) -> None:
    with pytest.raises(Conflict, match=r"^no channel is set$"):
        use_cases.test_channel(world.ports, world.project.id)

    assert world.factory.opened == []
    assert world.crypto.decrypted == []


# ── the token stays out of every rendering ───────────────────────────────────


def test_a_drafts_repr_never_carries_the_token() -> None:
    token = a_token()

    assert token not in repr(a_draft(token))
    assert token not in str(a_draft(token))


def test_the_ports_hold_no_gate_record_and_no_logger() -> None:
    """Nothing a channel operation runs on can write a gate record or a log line."""
    names = {field.name for field in dataclasses.fields(ChannelPorts)}

    assert names == {"uow", "projects", "channels", "crypto", "clock", "factory"}
