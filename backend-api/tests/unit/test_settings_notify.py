"""The notification settings: blank is off, the format is an enum, the secret never prints."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.infrastructure.settings import Settings


def build(env: dict[str, str], monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    for name, value in {**env, **extra}.items():
        monkeypatch.setenv(name, value)
    return Settings()  # type: ignore[call-arg]


def test_the_contract_leaves_notifications_off(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build(env, monkeypatch)

    assert settings.notify_enabled is False
    assert settings.notify_webhook_format == "json"
    assert settings.public_base_url == ""


def test_a_url_turns_notifications_on_and_whitespace_does_not(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert build(env, monkeypatch, NOTIFY_WEBHOOK_URL="https://h.example.test/x").notify_enabled
    assert not build(env, monkeypatch, NOTIFY_WEBHOOK_URL="   ").notify_enabled


def test_an_unknown_format_is_refused(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        build(env, monkeypatch, NOTIFY_WEBHOOK_FORMAT="teams")


def test_the_secret_is_not_in_the_repr(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build(env, monkeypatch, NOTIFY_WEBHOOK_SECRET="hunter2-hook")

    assert "hunter2-hook" not in repr(settings)
