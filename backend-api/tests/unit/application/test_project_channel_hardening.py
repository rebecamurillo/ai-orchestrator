"""Story 3-4 review fixes (2026-11-02), on the shared fakes.

A stored token the current key cannot open makes Test answer `ok: false`, not a 500. A kept
token never follows a host change.
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases import project_channel as use_cases
from orchestrator.domain.errors import Invalid
from tests.unit.application.test_project_channel import BASE_URL, World, a_draft, a_token


@pytest.fixture
def world() -> World:
    return World()


def test_a_token_the_current_key_cannot_open_answers_not_ok(world: World) -> None:
    world.store(a_token(), token_enc="fake-enc:99:issued-under-another-key")

    result = use_cases.test_channel(world.ports, world.project.id)

    assert result.ok is False
    assert result.detail == (
        "the stored token cannot be decrypted with the current key; save the token again"
    )
    assert world.factory.opened == []


def test_a_kept_token_does_not_follow_a_host_change(world: World) -> None:
    stored = world.store(a_token())

    with pytest.raises(Invalid, match=r"^token: enter the token again when the host changes$"):
        use_cases.put_channel(
            world.ports, world.project.id, a_draft(None, base_url="https://elsewhere.example")
        )

    assert world.channels.get(world.project.id) == stored
    assert not world.uow.committed


def test_a_kept_token_survives_a_trailing_slash(world: World) -> None:
    stored = world.store(a_token())

    use_cases.put_channel(world.ports, world.project.id, a_draft(None, base_url=f"{BASE_URL}/"))

    kept = world.channels.get(world.project.id)
    assert kept is not None
    assert kept.token_enc == stored.token_enc


def test_a_new_token_may_go_to_a_new_host(world: World) -> None:
    world.store(a_token())
    token = a_token()

    use_cases.put_channel(
        world.ports, world.project.id, a_draft(token, base_url="https://elsewhere.example")
    )

    stored = world.channels.get(world.project.id)
    assert stored is not None
    assert stored.base_url == "https://elsewhere.example"
    assert world.crypto.decrypt(stored.token_enc) == token
